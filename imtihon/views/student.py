"""What students see: sign in, their exams, the exam page and its JSON API, the result."""
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Count
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_POST

from user.permissions import safe_next_url

from .. import services
from ..models import Attempt, Exam, LoginAttempt
from ..services import ExamError
from .common import DEVICE_MESSAGE, api_view, error, is_proctor, json_body, student_login_required

LOGIN_FAIL_LIMIT = 10
LOGIN_FAIL_WINDOW = timedelta(minutes=10)
DEVICE_COOKIE_AGE = 12 * 3600
HEARTBEAT_SECONDS = 10


# ── sign in / out ─────────────────────────────────────────────────────────────

@sensitive_post_parameters('password')
@never_cache
def login_view(request):
    if request.user.is_authenticated and request.method != 'POST':
        return redirect('imtihon:manage' if is_proctor(request.user) else 'imtihon:my_exams')

    context = {'login_value': '', 'next': safe_next_url(request) or ''}
    if request.method == 'POST':
        login_value = (request.POST.get('login') or '').strip()[:254]
        password = request.POST.get('password') or ''
        context['login_value'] = login_value
        now = timezone.now()
        failures = LoginAttempt.objects.filter(
            login__iexact=login_value, success=False, created_at__gte=now - LOGIN_FAIL_WINDOW,
        ).count()
        if not login_value or not password:
            context['error'] = "Login va parolni kiriting."
        elif failures >= LOGIN_FAIL_LIMIT:
            context['error'] = ("Juda koʻp notoʻgʻri urinish. 10 daqiqadan soʻng qayta urinib koʻring "
                                "yoki nazoratchiga murojaat qiling.")
        else:
            account = (User.objects.filter(username__iexact=login_value).first()
                       or User.objects.filter(email__iexact=login_value).order_by('id').first())
            authed = authenticate(request, username=account.username, password=password) if account else None
            LoginAttempt.objects.create(
                login=login_value, success=authed is not None, ip_address=services.client_ip(request),
                user_agent=services.user_agent(request), created_at=now,
            )
            if authed is None:
                context['error'] = "Login yoki parol notoʻgʻri."
                if account is not None:
                    services.log_event('login_failed', user=account, request=request, now=now)
            else:
                login(request, authed)
                services.log_event('login', user=authed, request=request, now=now)
                if is_proctor(authed):
                    return redirect(context['next'] or 'imtihon:manage')
                request.session.set_expiry(0)  # shared lab computers: forget on browser close
                return redirect('imtihon:my_exams')
    return render(request, 'imtihon/login.html', context)


@require_POST
def logout_view(request):
    if request.user.is_authenticated:
        services.log_event('logout', user=request.user, request=request)
    logout(request)
    return redirect('imtihon:login')


# ── the student's exams ───────────────────────────────────────────────────────

def _card(exam, attempt, now):
    """How an exam looks on the student's list."""
    state = 'available'
    if attempt and attempt.status == Attempt.RUNNING:
        state = 'finished' if services.is_due(attempt, now) else 'running'
    elif attempt and attempt.status == Attempt.FINISHED:
        state = 'finished'
    elif exam.status == Exam.FINISHED or exam.window_state(now) == 'closed':
        state = 'missed'
    elif exam.window_state(now) == 'upcoming':
        state = 'upcoming'
    return {
        'exam': exam,
        'attempt': attempt,
        'state': state,
        'question_count': exam.question_count or exam.question_total,
    }


@student_login_required
@never_cache
def my_exams_view(request):
    if is_proctor(request.user):
        return redirect('imtihon:manage')
    now = timezone.now()
    exams = services.visible_exams(request.user).annotate(question_total=Count('questions', distinct=True))
    attempts = {a.exam_id: a for a in Attempt.objects.filter(user=request.user).select_related('exam')}
    cards = [_card(exam, attempts.get(exam.pk), now) for exam in exams]
    return render(request, 'imtihon/my_exams.html', {
        'active': [c for c in cards if c['state'] in ('available', 'running')],
        'upcoming': [c for c in cards if c['state'] == 'upcoming'],
        'past': [c for c in cards if c['state'] in ('finished', 'missed')],
        'student_name': request.user.get_full_name() or request.user.username,
    })


def _visible_exam_or_404(request, exam_id):
    exam = get_object_or_404(Exam, pk=exam_id)
    if not services.can_view(request.user, exam):
        raise Http404("Imtihon topilmadi.")
    return exam


@student_login_required
@never_cache
def exam_view(request, exam_id):
    if is_proctor(request.user):
        return redirect('imtihon:manage_exam', exam_id=exam_id)
    exam = _visible_exam_or_404(request, exam_id)
    now = timezone.now()
    with transaction.atomic():
        attempt = services.attempt_for(request.user, exam)
        if attempt is not None:
            attempt = services.lock(attempt)
        if attempt is not None and attempt.status == Attempt.RUNNING:
            if services.expire_if_due(attempt, now):
                return redirect('imtihon:result', exam_id=exam.pk)
            if not services.device_matches(attempt, request):
                services.log_event('device_mismatch', attempt, request=request, now=now)
                state = 'device'
            else:
                services.check_reopen(attempt, request, now)
                if attempt.status == Attempt.FINISHED:
                    return redirect('imtihon:result', exam_id=exam.pk)
                state = 'resume'
        elif attempt is not None and attempt.status == Attempt.FINISHED:
            return redirect('imtihon:result', exam_id=exam.pk)
        else:
            window = exam.window_state(now)
            if exam.status != Exam.PUBLISHED or window == 'closed':
                state = 'closed'
            elif window == 'upcoming':
                state = 'upcoming'
            else:
                state = 'lobby'
            services.log_event('lobby', attempt, user=request.user, exam=exam, request=request, now=now)

    question_total = exam.questions.count()
    urls = {
        name: reverse(f'imtihon:api_{name}', args=[exam.pk])
        for name in ('status', 'start', 'resume', 'answer', 'event', 'ping', 'finish')
    }
    urls.update(result=reverse('imtihon:result', args=[exam.pk]), login=reverse('imtihon:login'),
                home=reverse('imtihon:my_exams'))
    config = {
        'state': state,
        'open': exam.accepts_starts(now),
        'startsIn': max(0, int((exam.starts_at - now).total_seconds())) if exam.starts_at and exam.starts_at > now else 0,
        'watermark': f"{request.user.get_full_name() or request.user.username} · {request.user.username}",
        'duration': exam.duration_minutes,
        'maxLeaves': exam.max_leaves,
        'leaveCount': attempt.leave_count if attempt else 0,
        'countFullscreen': exam.count_fullscreen_exit,
        'questionCount': (attempt.question_count if attempt and attempt.question_count
                          else min(exam.question_count or question_total, question_total)),
        'heartbeat': HEARTBEAT_SECONDS,
        'remaining': attempt.remaining_seconds(now) if attempt else exam.duration_minutes * 60,
        'urls': urls,
    }
    return render(request, 'imtihon/exam.html', {
        'exam': exam,
        'attempt': attempt,
        'state': state,
        'config': config,
        'student_name': request.user.get_full_name() or request.user.username,
    })


# ── exam page API ─────────────────────────────────────────────────────────────

def _set_device_cookie(response, request, token):
    # Scoped to the app: its root is the login page.
    response.set_cookie(
        services.DEVICE_COOKIE, token, max_age=DEVICE_COOKIE_AGE, httponly=True,
        samesite='Lax', secure=request.is_secure(), path=reverse('imtihon:login'),
    )


def _finished_response(exam_id):
    return error('finished', "Test yakunlangan.", status=409, redirect=reverse('imtihon:result', args=[exam_id]))


def _status_payload(attempt, now):
    finished = attempt.status == Attempt.FINISHED
    return {
        'ok': True,
        'status': attempt.status,
        'remaining': attempt.remaining_seconds(now),
        'leave_count': attempt.leave_count,
        'max_leaves': attempt.exam.max_leaves,
        'answered': services.answered_count(attempt),
        'finished': finished,
        'redirect': reverse('imtihon:result', args=[attempt.exam_id]) if finished else None,
    }


def _running_attempt(request, exam_id, now):
    """Lock the student's attempt (inside transaction.atomic) -> (attempt, error response).

    Errors are returned, not raised, so that a logged event stays committed.
    """
    attempt = Attempt.objects.filter(exam_id=exam_id, user=request.user).first()
    if attempt is None:
        return None, error('not_started', "Test hali boshlanmagan.", status=409)
    attempt = services.lock(attempt)
    if attempt.status == Attempt.RUNNING and services.expire_if_due(attempt, now):
        return attempt, None
    if attempt.status == Attempt.RUNNING and not services.device_matches(attempt, request):
        services.log_event('device_mismatch', attempt, request=request, now=now)
        return attempt, error('device', DEVICE_MESSAGE, status=403)
    if attempt.status == Attempt.ASSIGNED:
        return attempt, error('not_started', "Test hali boshlanmagan.", status=409)
    return attempt, None


@api_view(methods=('GET',))
def api_status(request, exam_id):
    """Polled by the waiting room: can the test be started now?"""
    exam = _visible_exam_or_404(request, exam_id)
    attempt = services.attempt_for(request.user, exam)
    now = timezone.now()
    return JsonResponse({
        'ok': True,
        'open': exam.accepts_starts(now),
        'window': exam.window_state(now),
        'exam_status': exam.status,
        'status': attempt.status if attempt else Attempt.ASSIGNED,
    })


@api_view()
def api_start(request, exam_id):
    data = json_body(request)
    if data.get('accept') is not True:
        return error('rules', "Avval imtihon qoidalariga rozilik bildiring.")
    exam = _visible_exam_or_404(request, exam_id)
    now = timezone.now()
    token = None
    with transaction.atomic():
        attempt = services.attempt_for(request.user, exam)
        if attempt is not None:
            attempt = services.lock(attempt)
        if attempt is not None and attempt.status == Attempt.FINISHED:
            return _finished_response(exam.pk)
        if attempt is not None and attempt.status == Attempt.RUNNING:
            # Double click / second tab: continue only in the same browser.
            if not services.device_matches(attempt, request):
                services.log_event('device_mismatch', attempt, request=request, now=now)
                return error('device', DEVICE_MESSAGE, status=403)
        else:
            try:
                attempt, token = services.start_attempt(exam, request.user, request, now)
            except ExamError as exc:  # returned, not raised: the log entry is kept
                return error(exc.code, exc.message, status=403)
        payload = services.exam_payload(attempt, now)
    response = JsonResponse({'ok': True, **payload})
    if token:
        _set_device_cookie(response, request, token)
    return response


@api_view()
def api_resume(request, exam_id):
    """The page was reloaded while the test is running: send the questions again."""
    now = timezone.now()
    with transaction.atomic():
        attempt, problem = _running_attempt(request, exam_id, now)
        if problem:
            return problem
        if attempt.status == Attempt.FINISHED:
            return _finished_response(exam_id)
        token = None
        if not attempt.device_hash:
            token = services.bind_device(attempt)
            attempt.save(update_fields=['device_hash'])
            services.log_event('device_bound', attempt, request=request, now=now)
        services.touch(attempt, now, log_gap=False)
        services.log_event('resume', attempt, request=request, now=now)
        payload = services.exam_payload(attempt, now)
    response = JsonResponse({'ok': True, **payload})
    if token:
        _set_device_cookie(response, request, token)
    return response


@api_view()
def api_answer(request, exam_id):
    data = json_body(request)
    now = timezone.now()
    with transaction.atomic():
        attempt, problem = _running_attempt(request, exam_id, now)
        if problem:
            return problem
        if attempt.status != Attempt.RUNNING:
            return _finished_response(exam_id)
        if not services.accepts_answers(attempt, now):
            services.finalize(attempt, Attempt.REASON_TIME_UP, now)
            return _finished_response(exam_id)
        services.save_answer(attempt, data.get('q'), data.get('o'), now)
        services.touch(attempt, now, log_gap=False)
        return JsonResponse({'ok': True, 'answered': services.answered_count(attempt),
                             'remaining': attempt.remaining_seconds(now)})


@api_view()
def api_event(request, exam_id):
    data = json_body(request)
    events = data.get('events') if isinstance(data.get('events'), list) else []
    now = timezone.now()
    with transaction.atomic():
        attempt, problem = _running_attempt(request, exam_id, now)
        if problem:
            return problem
        if attempt.status != Attempt.RUNNING:
            return _finished_response(exam_id)
        if isinstance(data.get('answers'), dict) and services.accepts_answers(attempt, now):
            services.apply_snapshot(attempt, data['answers'], now)
        for item in events[:30]:
            if not isinstance(item, dict) or attempt.status != Attempt.RUNNING:
                continue
            kind = item.get('kind')
            if kind not in services.CLIENT_EVENTS:
                continue
            if (attempt.event_count >= services.MAX_EVENTS_PER_ATTEMPT
                    and kind not in services.IMPORTANT_EVENTS):
                continue
            details = services.clean_client_data(item.get('data'))
            if kind == 'leave':
                reason = details.get('reason')
                if reason not in services.LEAVE_REASONS:
                    reason = 'blur'
                if reason == 'fullscreen' and not attempt.exam.count_fullscreen_exit:
                    continue
                # A retried request must not count the same leave twice.
                event_id = str(item.get('id') or '')[:24]
                if event_id and attempt.events.filter(kind='leave', data__eid=event_id).exists():
                    continue
                services.register_leave(attempt, reason, now, data={'eid': event_id} if event_id else None)
                continue
            if kind == 'fullscreen_exit':
                attempt.fullscreen_exits += 1
                attempt.save(update_fields=['fullscreen_exits'])
            services.log_event(kind, attempt, data=details, request=request, now=now)
        if attempt.status == Attempt.RUNNING:
            services.touch(attempt, now, log_gap=False)
        return JsonResponse(_status_payload(attempt, now))


@api_view()
def api_ping(request, exam_id):
    now = timezone.now()
    with transaction.atomic():
        attempt, problem = _running_attempt(request, exam_id, now)
        if problem:
            return problem
        if attempt.status == Attempt.RUNNING:
            services.touch(attempt, now)
        return JsonResponse(_status_payload(attempt, now))


@api_view()
def api_finish(request, exam_id):
    data = json_body(request)
    now = timezone.now()
    with transaction.atomic():
        attempt, problem = _running_attempt(request, exam_id, now)
        if problem:
            return problem
        if attempt.status == Attempt.FINISHED:
            return JsonResponse({'ok': True, 'redirect': reverse('imtihon:result', args=[exam_id])})
        if isinstance(data.get('answers'), dict) and services.accepts_answers(attempt, now):
            services.apply_snapshot(attempt, data['answers'], now)
        deadline = attempt.deadline
        reason = (Attempt.REASON_TIME_UP if deadline and now >= deadline - timedelta(seconds=2)
                  else Attempt.REASON_SUBMITTED)
        services.finalize(attempt, reason, now)
    return JsonResponse({'ok': True, 'redirect': reverse('imtihon:result', args=[exam_id])})


@student_login_required
@never_cache
def result_view(request, exam_id):
    exam = _visible_exam_or_404(request, exam_id)
    attempt = services.attempt_for(request.user, exam)
    if attempt is None:
        return redirect('imtihon:exam', exam_id=exam.pk)
    if attempt.status != Attempt.FINISHED:
        with transaction.atomic():
            attempt = services.lock(attempt)
            services.expire_if_due(attempt)
        if attempt.status != Attempt.FINISHED:
            if attempt.status == Attempt.ASSIGNED:
                messages.info(request, "Test hali boshlanmagan.")
            return redirect('imtihon:exam', exam_id=exam.pk)
    return render(request, 'imtihon/result.html', {
        'attempt': attempt,
        'exam': exam,
        'student_name': request.user.get_full_name() or request.user.username,
        'answered': services.answered_count(attempt),
    })
