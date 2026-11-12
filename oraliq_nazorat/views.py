import csv
import json
import re
from datetime import timedelta
from functools import wraps

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.http.request import RawPostDataException
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from user.permissions import can_grade, safe_next_url

from . import services
from .blueprint import QUESTIONS_PER_VARIANT, TOPIC_LABELS
from .models import Answer, Attempt, Event, Exam, LoginAttempt, Question, option_letter
from .services import ExamError

LOGIN_FAIL_LIMIT = 10
LOGIN_FAIL_WINDOW = timedelta(minutes=10)
DEVICE_COOKIE_AGE = 12 * 3600
HEARTBEAT_SECONDS = 10


# ── helpers ───────────────────────────────────────────────────────────────────

def _is_proctor(user):
    return getattr(user, 'is_authenticated', False) and can_grade(user)


def exam_login_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('oraliq_nazorat:login')
        return view(request, *args, **kwargs)
    return wrapper


def proctor_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(reverse('oraliq_nazorat:login') + '?next=' + request.path)
        if not can_grade(request.user):
            messages.error(request, "Nazorat paneli faqat oʻqituvchi va administratorlar uchun.")
            return redirect('oraliq_nazorat:login')
        return view(request, *args, **kwargs)
    return wrapper


def _json_body(request):
    """The JSON payload of an API call. ``navigator.sendBeacon`` (used while the page
    is closing) cannot set headers, so it posts a form with the CSRF token and the
    JSON in a ``payload`` field instead."""
    if request.content_type in ('application/x-www-form-urlencoded', 'multipart/form-data'):
        raw = request.POST.get('payload') or '{}'
    else:
        try:
            raw = request.body or b'{}'
        except RawPostDataException:
            raw = request.POST.get('payload') or '{}'
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError, TypeError):
        data = None
    return data if isinstance(data, dict) else {}


def _error(code, message, status=400, **extra):
    return JsonResponse({'ok': False, 'error': code, 'message': message, **extra}, status=status)


def _finished_response(attempt):
    return _error(
        'finished', "Test yakunlangan.", status=409,
        redirect=reverse('oraliq_nazorat:result'), status_code=attempt.status,
    )


def api_view(methods=('POST',)):
    """JSON endpoint of a logged-in student; ExamError becomes a JSON error."""
    def decorator(view):
        @wraps(view)
        @never_cache
        def wrapper(request, *args, **kwargs):
            if request.method not in methods:
                return _error('method', "Notoʻgʻri soʻrov.", status=405)
            if not request.user.is_authenticated:
                return _error('auth', "Sessiya tugagan. Qayta kiring.", status=401,
                              redirect=reverse('oraliq_nazorat:login'))
            try:
                return view(request, *args, **kwargs)
            except ExamError as exc:
                return _error(exc.code, exc.message, status=403)
        return wrapper
    return decorator


DEVICE_MESSAGE = "Bu test boshqa kompyuter yoki brauzerda boshlangan. Nazoratchiga murojaat qiling."


def _running_attempt(request, now):
    """Lock the student's attempt (call inside transaction.atomic).

    Returns ``(attempt, error_response)``; when the error response is set the view
    returns it as is — returning (not raising) keeps the logged event committed.
    """
    attempt = services.current_attempt(request.user)
    if attempt is None:
        return None, _error('no_attempt', "Siz bu imtihon ishtirokchilari roʻyxatida yoʻqsiz.", status=403)
    attempt = services.lock(attempt)
    if attempt.status == Attempt.RUNNING and services.expire_if_due(attempt, now):
        return attempt, None
    if attempt.status == Attempt.RUNNING and not services.device_matches(attempt, request):
        services.log_event('device_mismatch', attempt, request=request, now=now)
        return attempt, _error('device', DEVICE_MESSAGE, status=403)
    return attempt, None


def _set_device_cookie(response, request, token):
    response.set_cookie(
        services.DEVICE_COOKIE, token, max_age=DEVICE_COOKIE_AGE, httponly=True,
        samesite='Lax', secure=request.is_secure(), path=reverse('oraliq_nazorat:login'),
    )


def _status_payload(attempt, now):
    return {
        'ok': True,
        'status': attempt.status,
        'remaining': attempt.remaining_seconds(now),
        'leave_count': attempt.leave_count,
        'max_leaves': attempt.exam.max_leaves,
        'answered': services.answered_count(attempt),
        'finished': attempt.status == Attempt.FINISHED,
        'redirect': reverse('oraliq_nazorat:result') if attempt.status == Attempt.FINISHED else None,
    }


# ── sign in / out ─────────────────────────────────────────────────────────────

@never_cache
def login_view(request):
    user = request.user
    if user.is_authenticated:
        if _is_proctor(user):
            return redirect('oraliq_nazorat:dashboard')
        if services.current_attempt(user):
            return redirect('oraliq_nazorat:exam')

    context = {'email': ''}
    if request.method == 'POST':
        email = (request.POST.get('email') or '').strip().lower()[:254]
        password = request.POST.get('password') or ''
        context['email'] = email
        now = timezone.now()
        failures = LoginAttempt.objects.filter(
            email=email, success=False, created_at__gte=now - LOGIN_FAIL_WINDOW,
        ).count()
        if not email or not password:
            context['error'] = "Email va parolni kiriting."
        elif failures >= LOGIN_FAIL_LIMIT:
            context['error'] = ("Juda koʻp notoʻgʻri urinish. 10 daqiqadan soʻng qayta urinib koʻring "
                                "yoki nazoratchiga murojaat qiling.")
        else:
            account = (User.objects.filter(username__iexact=email).first()
                       or User.objects.filter(email__iexact=email).order_by('id').first())
            authed = authenticate(request, username=account.username, password=password) if account else None
            LoginAttempt.objects.create(
                email=email, success=authed is not None, ip_address=services.client_ip(request),
                user_agent=services.user_agent(request), created_at=now,
            )
            attempt = services.current_attempt(authed) if authed else None
            if authed is None:
                context['error'] = "Email yoki parol notoʻgʻri."
                if account is not None:
                    victim = services.current_attempt(account)
                    if victim is not None:
                        services.log_event('login_failed', victim, request=request, now=now)
            elif attempt is None and not can_grade(authed):
                context['error'] = "Siz ushbu imtihon ishtirokchilari roʻyxatida yoʻqsiz."
            else:
                login(request, authed)
                if can_grade(authed):
                    return redirect(safe_next_url(request) or 'oraliq_nazorat:dashboard')
                request.session.set_expiry(0)  # shared lab computers: forget on browser close
                services.log_event('login', attempt, request=request, now=now)
                return redirect('oraliq_nazorat:exam')
    elif user.is_authenticated:
        context['foreign_user'] = user
    context['next'] = request.GET.get('next', '')
    return render(request, 'oraliq_nazorat/login.html', context)


@require_POST
def logout_view(request):
    if request.user.is_authenticated and not _is_proctor(request.user):
        attempt = services.current_attempt(request.user)
        if attempt is not None:
            services.log_event('logout', attempt, request=request)
    logout(request)
    return redirect('oraliq_nazorat:login')


# ── the exam page ─────────────────────────────────────────────────────────────

@exam_login_required
@never_cache
def exam_view(request):
    attempt = services.current_attempt(request.user)
    if attempt is None:
        if _is_proctor(request.user):
            return redirect('oraliq_nazorat:dashboard')
        messages.error(request, "Siz ushbu imtihon ishtirokchilari roʻyxatida yoʻqsiz.")
        logout(request)
        return redirect('oraliq_nazorat:login')

    now = timezone.now()
    state = 'lobby'
    with transaction.atomic():
        attempt = services.lock(attempt)
        if attempt.status == Attempt.RUNNING:
            if services.expire_if_due(attempt, now):
                return redirect('oraliq_nazorat:result')
            if not services.device_matches(attempt, request):
                services.log_event('device_mismatch', attempt, request=request, now=now)
                state = 'device'
            else:
                services.check_reopen(attempt, request, now)
                if attempt.status == Attempt.FINISHED:
                    return redirect('oraliq_nazorat:result')
                state = 'resume'
        elif attempt.status == Attempt.FINISHED:
            return redirect('oraliq_nazorat:result')
        else:
            services.log_event('lobby', attempt, request=request, now=now)

    exam = attempt.exam
    config = {
        'state': state,
        'open': exam.is_open,
        'watermark': f"{request.user.get_full_name() or request.user.username} · "
                     f"{request.user.email or request.user.username} · {attempt.variant.number}-variant",
        'duration': exam.duration_minutes,
        'maxLeaves': exam.max_leaves,
        'leaveCount': attempt.leave_count,
        'countFullscreen': exam.count_fullscreen_exit,
        'questionCount': attempt.question_count or attempt.variant.items.count(),
        'heartbeat': HEARTBEAT_SECONDS,
        'remaining': attempt.remaining_seconds(now),
        'urls': {
            'status': reverse('oraliq_nazorat:api_status'),
            'start': reverse('oraliq_nazorat:api_start'),
            'resume': reverse('oraliq_nazorat:api_resume'),
            'answer': reverse('oraliq_nazorat:api_answer'),
            'event': reverse('oraliq_nazorat:api_event'),
            'ping': reverse('oraliq_nazorat:api_ping'),
            'finish': reverse('oraliq_nazorat:api_finish'),
            'result': reverse('oraliq_nazorat:result'),
            'login': reverse('oraliq_nazorat:login'),
        },
    }
    return render(request, 'oraliq_nazorat/exam.html', {
        'exam': exam,
        'attempt': attempt,
        'state': state,
        'config': config,
        'student_name': request.user.get_full_name() or request.user.username,
    })


@api_view(methods=('GET',))
def api_status(request):
    """Polled by the waiting room: is the exam open yet?"""
    attempt = services.current_attempt(request.user)
    if attempt is None:
        return _error('no_attempt', "Siz bu imtihon ishtirokchilari roʻyxatida yoʻqsiz.", status=403)
    return JsonResponse({'ok': True, 'open': attempt.exam.is_open, 'status': attempt.status})


@api_view()
def api_start(request):
    data = _json_body(request)
    if data.get('accept') is not True:
        return _error('rules', "Avval imtihon qoidalariga rozilik bildiring.")
    now = timezone.now()
    attempt = services.current_attempt(request.user)
    if attempt is None:
        return _error('no_attempt', "Siz bu imtihon ishtirokchilari roʻyxatida yoʻqsiz.", status=403)
    with transaction.atomic():
        attempt = services.lock(attempt)
        if attempt.status == Attempt.FINISHED:
            return _finished_response(attempt)
        token = None
        if attempt.status == Attempt.RUNNING:
            # Double click / second tab: continue only in the same browser.
            if not services.device_matches(attempt, request):
                services.log_event('device_mismatch', attempt, request=request, now=now)
                return _error('device', DEVICE_MESSAGE, status=403)
        else:
            try:
                token = services.start_attempt(attempt, request, now)
            except ExamError as exc:  # returned, not raised: the log entry is kept
                return _error(exc.code, exc.message, status=403)
        payload = services.exam_payload(attempt, now)
    response = JsonResponse({'ok': True, **payload})
    if token:
        _set_device_cookie(response, request, token)
    return response


@api_view()
def api_resume(request):
    """The page was reloaded while the test is running: send the questions again."""
    now = timezone.now()
    with transaction.atomic():
        attempt, error = _running_attempt(request, now)
        if error:
            return error
        if attempt.status != Attempt.RUNNING:
            return _finished_response(attempt) if attempt.status == Attempt.FINISHED else \
                _error('not_started', "Test hali boshlanmagan.", status=409)
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
def api_answer(request):
    data = _json_body(request)
    now = timezone.now()
    with transaction.atomic():
        attempt, error = _running_attempt(request, now)
        if error:
            return error
        if attempt.status != Attempt.RUNNING:
            return _finished_response(attempt)
        if not services.accepts_answers(attempt, now):
            services.finalize(attempt, Attempt.REASON_TIME_UP, now)
            return _finished_response(attempt)
        services.save_answer(attempt, data.get('q'), data.get('o'), now)
        services.touch(attempt, now, log_gap=False)
        return JsonResponse({'ok': True, 'answered': services.answered_count(attempt),
                             'remaining': attempt.remaining_seconds(now)})


@api_view()
def api_event(request):
    data = _json_body(request)
    events = data.get('events')
    if not isinstance(events, list):
        events = []
    now = timezone.now()
    with transaction.atomic():
        attempt, error = _running_attempt(request, now)
        if error:
            return error
        if attempt.status != Attempt.RUNNING:
            return _finished_response(attempt)
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
            details = services._clean_data(item.get('data'))
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
def api_ping(request):
    now = timezone.now()
    with transaction.atomic():
        attempt, error = _running_attempt(request, now)
        if error:
            return error
        if attempt.status == Attempt.RUNNING:
            services.touch(attempt, now)
        return JsonResponse(_status_payload(attempt, now))


@api_view()
def api_finish(request):
    data = _json_body(request)
    now = timezone.now()
    with transaction.atomic():
        attempt, error = _running_attempt(request, now)
        if error:
            return error
        if attempt.status == Attempt.FINISHED:
            return JsonResponse({'ok': True, 'redirect': reverse('oraliq_nazorat:result')})
        if attempt.status != Attempt.RUNNING:
            return _error('not_started', "Test hali boshlanmagan.", status=409)
        if isinstance(data.get('answers'), dict) and services.accepts_answers(attempt, now):
            services.apply_snapshot(attempt, data['answers'], now)
        deadline = attempt.deadline
        reason = (Attempt.REASON_TIME_UP if deadline and now >= deadline - timedelta(seconds=2)
                  else Attempt.REASON_SUBMITTED)
        services.finalize(attempt, reason, now)
    return JsonResponse({'ok': True, 'redirect': reverse('oraliq_nazorat:result')})


@exam_login_required
@never_cache
def result_view(request):
    attempt = services.current_attempt(request.user)
    if attempt is None:
        return redirect('oraliq_nazorat:login')
    if attempt.status != Attempt.FINISHED:
        with transaction.atomic():
            attempt = services.lock(attempt)
            services.expire_if_due(attempt)
        if attempt.status != Attempt.FINISHED:
            return redirect('oraliq_nazorat:exam')
    return render(request, 'oraliq_nazorat/result.html', {
        'attempt': attempt,
        'exam': attempt.exam,
        'student_name': request.user.get_full_name() or request.user.username,
        'answered': services.answered_count(attempt),
    })


# ── proctor dashboard ─────────────────────────────────────────────────────────

def _dashboard_exam(request):
    exams = list(Exam.objects.order_by('-created_at'))
    selected = None
    wanted = request.GET.get('exam')
    if wanted and wanted.isdigit():
        selected = next((e for e in exams if e.pk == int(wanted)), None)
    if selected is None and exams:
        selected = next((e for e in exams if e.is_open), exams[0])
    return exams, selected


def _natural_key(text):
    """student2 before student10."""
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r'(\d+)', text or '')]


def _fmt_time(value):
    return value.strftime('%H:%M:%S') if value else ''


def dashboard_rows(exam, now=None):
    now = now or timezone.now()
    services.finalize_expired(exam, now)
    attempts = (
        Attempt.objects.filter(exam=exam)
        .select_related('user', 'variant', 'exam')
        .annotate(
            answered=Count('answers', filter=Q(answers__choice__isnull=False), distinct=True),
            warnings=Count('events', filter=Q(events__level__in=[Event.WARNING, Event.DANGER]), distinct=True),
        )
        .order_by('user__username')
    )
    rows = []
    for a in attempts:
        seen_ago = int((now - a.last_seen_at).total_seconds()) if a.last_seen_at else None
        rows.append({
            'id': a.pk,
            'email': a.user.email or a.user.username,
            'name': a.user.get_full_name(),
            'variant': a.variant.number,
            'status': a.status,
            'status_label': a.get_status_display(),
            'started': _fmt_time(a.started_at),
            'finished': _fmt_time(a.finished_at),
            'remaining': a.remaining_seconds(now) if a.status == Attempt.RUNNING else None,
            'answered': a.answered,
            'total': a.question_count or len(a.question_order or []) or QUESTIONS_PER_VARIANT,
            'leaves': a.leave_count,
            'fs_exits': a.fullscreen_exits,
            'warnings': a.warnings,
            'correct': a.correct_count,
            'score': a.score,
            'reason': a.get_finish_reason_display() if a.finish_reason else '',
            'seen_ago': seen_ago,
            'online': a.status == Attempt.RUNNING and seen_ago is not None and seen_ago <= 25,
            'url': reverse('oraliq_nazorat:attempt_detail', args=[a.pk]),
        })
    rows.sort(key=lambda r: _natural_key(r['email']))
    finished = [r for r in rows if r['status'] == Attempt.FINISHED and r['score'] is not None]
    stats = {
        'total': len(rows),
        'assigned': sum(r['status'] == Attempt.ASSIGNED for r in rows),
        'running': sum(r['status'] == Attempt.RUNNING for r in rows),
        'finished': len(finished),
        'average': round(sum(r['score'] for r in finished) / len(finished), 1) if finished else None,
        'flagged': sum(1 for r in rows if r['leaves'] or r['fs_exits']),
    }
    return rows, stats


@proctor_required
@never_cache
def dashboard_view(request):
    exams, exam = _dashboard_exam(request)
    rows, stats = dashboard_rows(exam) if exam else ([], {})
    return render(request, 'oraliq_nazorat/dashboard.html', {
        'exams': exams,
        'exam': exam,
        'initial': {'rows': rows, 'stats': stats, 'open': exam.is_open if exam else False},
        'data_url': (reverse('oraliq_nazorat:dashboard_data') + f'?exam={exam.pk}') if exam else '',
    })


@proctor_required
@require_GET
@never_cache
def dashboard_data(request):
    _, exam = _dashboard_exam(request)
    if exam is None:
        return JsonResponse({'rows': [], 'stats': {}, 'open': False})
    rows, stats = dashboard_rows(exam)
    return JsonResponse({'rows': rows, 'stats': stats, 'open': exam.is_open,
                         'time': timezone.now().strftime('%H:%M:%S')})


@proctor_required
@require_POST
def exam_toggle_view(request, exam_id):
    exam = get_object_or_404(Exam, pk=exam_id)
    exam.is_open = request.POST.get('open') == '1'
    exam.save(update_fields=['is_open'])
    messages.success(request, "Imtihon ochildi — talabalar boshlashi mumkin." if exam.is_open
                     else "Imtihon yopildi — yangi talabalar boshlay olmaydi.")
    return redirect(reverse('oraliq_nazorat:dashboard') + f'?exam={exam.pk}')


@proctor_required
@never_cache
def attempt_detail_view(request, pk):
    attempt = get_object_or_404(Attempt.objects.select_related('user', 'exam', 'variant'), pk=pk)
    if attempt.status == Attempt.RUNNING:
        with transaction.atomic():
            attempt = services.lock(attempt)
            services.expire_if_due(attempt)
    questions = {}
    order = attempt.question_order or list(
        attempt.variant.items.order_by('order').values_list('question_id', flat=True)
    )
    for q in Question.objects.filter(pk__in=order).prefetch_related('choices'):
        questions[q.pk] = q
    answers = {a.question_id: a for a in Answer.objects.filter(attempt=attempt).select_related('choice')}
    rows = []
    for index, qid in enumerate(order):
        q = questions.get(qid)
        if q is None:
            continue
        ids = (attempt.choice_order or {}).get(str(qid)) or [c.pk for c in q.choices.all()]
        by_id = {c.pk: c for c in q.choices.all()}
        options = [
            {'letter': option_letter(i), 'text': by_id[cid].text, 'correct': by_id[cid].is_correct}
            for i, cid in enumerate(ids) if cid in by_id
        ]
        answer = answers.get(qid)
        chosen = None
        if answer and answer.choice_id in ids:
            chosen = option_letter(ids.index(answer.choice_id))
        rows.append({
            'n': index + 1,
            'question': q,
            'topic': TOPIC_LABELS.get(q.topic, q.topic),
            'options': options,
            'chosen': chosen,
            'is_correct': bool(answer and answer.choice and answer.choice.is_correct),
            'changes': answer.changes if answer else 0,
        })
    events = list(attempt.events.order_by('created_at', 'id'))
    return render(request, 'oraliq_nazorat/attempt_detail.html', {
        'attempt': attempt,
        'exam': attempt.exam,
        'rows': rows,
        'events': events,
        'danger_count': sum(1 for e in events if e.level == Event.DANGER),
        'warning_count': sum(1 for e in events if e.level == Event.WARNING),
        'actions': services.TEACHER_ACTIONS,
    })


@proctor_required
@require_POST
def attempt_action_view(request, pk):
    attempt = get_object_or_404(Attempt, pk=pk)
    action = request.POST.get('action')
    try:
        minutes = int(request.POST.get('minutes') or 5)
    except ValueError:
        minutes = 5
    try:
        with transaction.atomic():
            locked = services.lock(attempt)
            message = services.teacher_action(locked, action, request.user, minutes=minutes)
        messages.success(request, message)
    except ExamError as exc:
        messages.error(request, exc.message)
    target = request.POST.get('next')
    if target == 'dashboard':
        return redirect(reverse('oraliq_nazorat:dashboard') + f'?exam={attempt.exam_id}')
    return redirect('oraliq_nazorat:attempt_detail', pk=attempt.pk)


@proctor_required
@require_GET
def export_csv_view(request):
    _, exam = _dashboard_exam(request)
    if exam is None:
        return redirect('oraliq_nazorat:dashboard')
    rows, _ = dashboard_rows(exam)

    def cell(value):
        text = '' if value is None else str(value)
        return "'" + text if text[:1] in ('=', '+', '-', '@') else text

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="oraliq_nazorat_{exam.code}_{timezone.now():%Y%m%d_%H%M}.csv"'
    response.write('﻿')
    writer = csv.writer(response)
    writer.writerow([
        '№', 'Email', 'F.I.Sh', 'Variant', 'Holat', 'Boshlangan', 'Yakunlangan', 'Javob berilgan',
        'Toʻgʻri', 'Savollar', 'Natija (%)', 'Oynadan chiqish', 'Toʻliq ekrandan chiqish',
        'Ogohlantirishlar', 'Yakunlanish sababi',
    ])
    for n, r in enumerate(rows, start=1):
        writer.writerow([cell(v) for v in (
            n, r['email'], r['name'], r['variant'], r['status_label'], r['started'], r['finished'],
            r['answered'], r['correct'], r['total'], r['score'], r['leaves'], r['fs_exits'],
            r['warnings'], r['reason'],
        )])
    return response
