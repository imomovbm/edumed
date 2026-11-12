"""Exam rules enforced on the server.

The browser only reports what happened; the server decides. Answers are stored
the moment they are clicked, the deadline is computed from ``started_at`` and
leaving the exam window is counted here, so a student who tampers with the page
still cannot get extra time or avoid the leave limit.
"""
import hashlib
import hmac
import ipaddress
import math
import random
import secrets
from datetime import timedelta

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import Answer, Attempt, Choice, Event, Question, Variant, option_letter

ANSWER_GRACE_SECONDS = 15       # answers that left the browser just before the deadline
REOPEN_GRACE_SECONDS = 30       # page closed longer than this (not a quick reload) = a leave
CONNECTION_GAP_SECONDS = 45     # no heartbeat for this long is written to the log
MAX_EVENTS_PER_ATTEMPT = 3000
DEVICE_COOKIE = 'on_device'

INFO, WARNING, DANGER = Event.INFO, Event.WARNING, Event.DANGER

LEAVE_REASONS = {
    'hidden': "boshqa tab, oyna yoki dasturga oʻtdi",
    'blur': "boshqa oyna yoki dastur faollashdi",
    'fullscreen': "toʻliq ekran rejimidan chiqdi",
    'reopen': "sahifani yopib, keyin qayta ochdi",
}

# kind -> (level, message). Messages are built on the server, never taken from the browser.
EVENTS = {
    # sent by the browser
    'fullscreen_enter': (INFO, "Toʻliq ekran rejimiga oʻtdi"),
    'fullscreen_exit': (DANGER, "Toʻliq ekran rejimidan chiqdi — savollar yashirildi"),
    'leave': (DANGER, "Imtihon oynasini tark etdi ({n}/{max}): {reason}"),
    'return': (INFO, "Imtihon oynasiga qaytdi ({seconds} soniya tashqarida boʻldi)"),
    'copy': (WARNING, "Nusxa olishga urindi"),
    'cut': (WARNING, "Matnni kesib olishga urindi"),
    'paste': (WARNING, "Matn qoʻyishga urindi"),
    'contextmenu': (WARNING, "Sichqonchaning oʻng tugmasini bosdi"),
    'select': (INFO, "Matnni belgilashga urindi"),
    'key': (WARNING, "Taqiqlangan tugma bosildi: {combo}"),
    'print': (WARNING, "Sahifani chop etishga urindi"),
    'devtools': (DANGER, "Dasturchi vositalari (DevTools) ochilgan boʻlishi mumkin"),
    'extension': (DANGER, "Sahifaga begona element qoʻshildi ({tag}) — brauzer kengaytmasi (masalan, AI yordamchi) boʻlishi mumkin"),
    'back': (WARNING, "Brauzerda orqaga qaytishga urindi"),
    'unload': (WARNING, "Sahifani yopdi yoki yangiladi"),
    'offline': (WARNING, "Internet aloqasi uzildi"),
    'online': (INFO, "Internet aloqasi tiklandi"),
    'mouse_out': (INFO, "Sichqoncha imtihon oynasidan tashqarida boʻldi ({seconds} s)"),
    'screens': (WARNING, "Kompyuterga bir nechta monitor ulangan"),
    'navigate': (INFO, "{n}-savolga oʻtdi"),
    'finish_click': (INFO, "«Testni yakunlash» tugmasini bosdi"),
    'finish_cancel': (INFO, "Yakunlashdan voz kechdi"),
    # written by the server
    'login': (INFO, "Tizimga kirdi"),
    'login_failed': (WARNING, "Notoʻgʻri parol bilan kirishga urinish"),
    'logout': (INFO, "Tizimdan chiqdi"),
    'lobby': (INFO, "Kutish sahifasini ochdi"),
    'closed_start': (WARNING, "Imtihon hali ochilmagan paytda boshlashga urindi"),
    'start': (INFO, "Imtihonni boshladi ({variant}-variant)"),
    'resume': (INFO, "Imtihonni davom ettirdi"),
    'reload': (WARNING, "Sahifa qayta yuklandi ({seconds} soniya uzilish)"),
    'device_mismatch': (DANGER, "Boshqa qurilma yoki brauzerdan imtihonga kirishga urindi"),
    'device_bound': (INFO, "Imtihon yangi qurilmada davom ettirildi"),
    'answer': (INFO, "{n}-savol: {letter} javobni belgiladi"),
    'answer_change': (INFO, "{n}-savol: javobni {old} dan {letter} ga oʻzgartirdi"),
    'connection_gap': (WARNING, "Server bilan aloqa {seconds} soniya uzilib qoldi"),
    'finish': (INFO, "Imtihonni yakunladi"),
    'time_up': (WARNING, "Vaqt tugadi — test avtomatik yakunlandi"),
    'violations_finish': (DANGER, "Oynadan chiqish limiti tugadi — test avtomatik yakunlandi"),
    'teacher_finish': (WARNING, "Nazoratchi ({by}) testni yakunladi"),
    'teacher_reset': (WARNING, "Nazoratchi ({by}) urinishni bekor qildi, test qaytadan boshlanadi ({variant}-variant)"),
    'teacher_unlock': (INFO, "Nazoratchi ({by}) boshqa qurilmada davom etishga ruxsat berdi"),
    'teacher_extra': (INFO, "Nazoratchi ({by}) {minutes} daqiqa qoʻshimcha vaqt berdi"),
    'teacher_forgive': (INFO, "Nazoratchi ({by}) bitta chiqishni hisobdan chiqardi"),
    'teacher_reopen': (WARNING, "Nazoratchi ({by}) yakunlangan testni qayta ochdi"),
}

# Events the browser may send (everything else is ignored).
CLIENT_EVENTS = {
    'fullscreen_enter', 'fullscreen_exit', 'leave', 'return', 'copy', 'cut', 'paste',
    'contextmenu', 'select', 'key', 'print', 'devtools', 'extension', 'back', 'unload', 'offline', 'online',
    'mouse_out', 'screens', 'navigate', 'finish_click', 'finish_cancel',
}
# Always kept, even when an attempt has written a suspicious number of events.
IMPORTANT_EVENTS = {'leave', 'return', 'fullscreen_exit', 'unload', 'devtools', 'extension'}


class ExamError(Exception):
    """A request the exam rules do not allow; ``code`` is sent to the browser."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


# ── small helpers ─────────────────────────────────────────────────────────────

def client_ip(request):
    remote = request.META.get('REMOTE_ADDR', '')
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    candidates = [remote]
    try:
        behind_proxy = ipaddress.ip_address(remote).is_private or ipaddress.ip_address(remote).is_loopback
    except ValueError:
        behind_proxy = False
    if forwarded and behind_proxy:
        candidates.insert(0, forwarded.split(',')[0].strip())
    for value in candidates:
        try:
            return str(ipaddress.ip_address(value))
        except ValueError:
            continue
    return None


def user_agent(request):
    return (request.META.get('HTTP_USER_AGENT') or '')[:400]


def _clean_data(data):
    """Keep only short, simple values from the browser."""
    clean = {}
    if not isinstance(data, dict):
        return clean
    for key, value in list(data.items())[:12]:
        key = str(key)[:30]
        if isinstance(value, bool) or value is None:
            clean[key] = value
        elif isinstance(value, (int, float)):
            if isinstance(value, float) and not math.isfinite(value):
                continue
            clean[key] = max(-10**9, min(10**9, value))
        elif isinstance(value, str):
            clean[key] = value[:120]
    return clean


class _SafeDict(dict):
    def __missing__(self, key):
        return '?'


def describe(kind, data):
    level, template = EVENTS.get(kind, (INFO, kind))
    try:
        message = template.format_map(_SafeDict(data or {}))
    except (ValueError, IndexError):
        message = template
    return level, message[:300]


def log_event(kind, attempt=None, user=None, data=None, request=None, now=None):
    data = data or {}
    level, message = describe(kind, data)
    event = Event.objects.create(
        attempt=attempt,
        user=user or (attempt.user if attempt else None),
        kind=kind,
        level=level,
        message=message,
        data=data,
        ip_address=client_ip(request) if request is not None else None,
        created_at=now or timezone.now(),
    )
    if attempt is not None:
        Attempt.objects.filter(pk=attempt.pk).update(event_count=F('event_count') + 1)
        attempt.event_count += 1
    return event


def hash_token(token):
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def device_matches(attempt, request):
    """True when the request comes from the browser that started the attempt."""
    if not attempt.device_hash:
        return True  # nothing bound yet, or the teacher allowed another device
    token = request.COOKIES.get(DEVICE_COOKIE) or ''
    return bool(token) and hmac.compare_digest(hash_token(token), attempt.device_hash)


def bind_device(attempt):
    """Bind the attempt to a new browser; returns the cookie value to set."""
    token = secrets.token_urlsafe(32)
    attempt.device_hash = hash_token(token)
    return token


def current_attempt(user):
    """The attempt the exam pages work with: a running one first, then one of an
    open exam that has not started, then the newest one."""
    if not getattr(user, 'is_authenticated', False):
        return None
    attempts = list(
        Attempt.objects.filter(user=user)
        .select_related('exam', 'variant', 'user')
        .order_by('-exam__created_at', '-id')
    )
    for attempt in attempts:
        if attempt.status == Attempt.RUNNING:
            return attempt
    for attempt in attempts:
        if attempt.status == Attempt.ASSIGNED and attempt.exam.is_open:
            return attempt
    return attempts[0] if attempts else None


def lock(attempt):
    """Re-read the attempt with a row lock (use inside transaction.atomic)."""
    return (
        Attempt.objects.select_for_update()
        .select_related('exam', 'variant', 'user')
        .get(pk=attempt.pk)
    )


def answered_count(attempt):
    return Answer.objects.filter(attempt=attempt, choice__isnull=False).count()


# ── the exam itself ───────────────────────────────────────────────────────────

def start_attempt(attempt, request, now=None):
    """Start an assigned attempt (call with a locked attempt). Returns the device token."""
    now = now or timezone.now()
    if attempt.status != Attempt.ASSIGNED:
        raise ExamError('not_assigned', "Bu test allaqachon boshlangan yoki yakunlangan.")
    if not attempt.exam.is_open:
        log_event('closed_start', attempt, request=request, now=now)
        raise ExamError('closed', "Imtihon hali ochilmagan. Nazoratchi ruxsatini kuting.")

    question_ids = list(
        attempt.variant.items.order_by('order').values_list('question_id', flat=True)
    )
    if not question_ids:
        raise ExamError('empty', "Variantda savollar yoʻq. Nazoratchiga murojaat qiling.")
    shuffle = random.SystemRandom().shuffle
    choice_order = {}
    choices = Choice.objects.filter(question_id__in=question_ids).order_by('id')
    for choice in choices:
        choice_order.setdefault(str(choice.question_id), []).append(choice.pk)
    for ids in choice_order.values():
        shuffle(ids)

    attempt.question_order = question_ids
    attempt.choice_order = choice_order
    attempt.question_count = len(question_ids)
    attempt.status = Attempt.RUNNING
    attempt.started_at = now
    attempt.last_seen_at = now
    attempt.ip_address = client_ip(request)
    attempt.user_agent = user_agent(request)
    token = bind_device(attempt)
    attempt.save()
    log_event('start', attempt, data={'variant': attempt.variant.number}, request=request, now=now)
    return token


def is_due(attempt, now=None):
    """The deadline (plus a short grace for answers still on the way) has passed."""
    now = now or timezone.now()
    deadline = attempt.deadline
    return bool(
        attempt.status == Attempt.RUNNING and deadline
        and now >= deadline + timedelta(seconds=ANSWER_GRACE_SECONDS)
    )


def finalize(attempt, reason, now=None, data=None):
    """Grade and close a running attempt (call with a locked attempt)."""
    if attempt.status == Attempt.FINISHED:
        return attempt
    now = now or timezone.now()
    finished_at = now
    deadline = attempt.deadline
    if reason == Attempt.REASON_TIME_UP and deadline and deadline < now:
        finished_at = deadline
    attempt.status = Attempt.FINISHED
    attempt.finish_reason = reason
    attempt.finished_at = finished_at
    grade(attempt)
    attempt.save()
    kind = {
        Attempt.REASON_SUBMITTED: 'finish',
        Attempt.REASON_TIME_UP: 'time_up',
        Attempt.REASON_VIOLATIONS: 'violations_finish',
        Attempt.REASON_TEACHER: 'teacher_finish',
    }[reason]
    log_event(kind, attempt, data=data or {}, now=now)
    return attempt


def grade(attempt):
    """Fill correct_count / score from the stored answers (does not save)."""
    total = attempt.question_count or len(attempt.question_order or []) or attempt.variant.items.count()
    correct = Answer.objects.filter(attempt=attempt, choice__is_correct=True).count()
    attempt.question_count = total
    attempt.correct_count = correct
    attempt.score = round(correct / total * 100, 1) if total else 0.0
    return attempt


def regrade(attempt):
    """Recompute the result of a finished attempt (after a corrected answer key)."""
    if attempt.status == Attempt.FINISHED:
        grade(attempt)
        attempt.save(update_fields=['question_count', 'correct_count', 'score'])
    return attempt


def expire_if_due(attempt, now=None):
    """Finish the attempt when its time is over. Returns True if it is (now) finished."""
    now = now or timezone.now()
    if attempt.status == Attempt.FINISHED:
        return True
    if is_due(attempt, now):
        finalize(attempt, Attempt.REASON_TIME_UP, now)
        return True
    return False


def finalize_expired(exam, now=None):
    """Close every attempt of the exam whose time has run out (e.g. the student closed the browser)."""
    now = now or timezone.now()
    finished = 0
    for attempt in Attempt.objects.filter(exam=exam, status=Attempt.RUNNING).select_related('exam'):
        if is_due(attempt, now):
            with transaction.atomic():
                locked = lock(attempt)
                if expire_if_due(locked, now):
                    finished += 1
    return finished


def register_leave(attempt, reason, now=None, data=None):
    """Count one leave of the exam window; finishes the test at the limit."""
    now = now or timezone.now()
    attempt.leave_count += 1
    attempt.save(update_fields=['leave_count'])
    info = {
        'reason': LEAVE_REASONS.get(reason, reason),
        'code': reason,
        'n': attempt.leave_count,
        'max': attempt.exam.max_leaves,
    }
    info.update(data or {})
    log_event('leave', attempt, data=info, now=now)
    if attempt.leave_count >= attempt.exam.max_leaves:
        finalize(attempt, Attempt.REASON_VIOLATIONS, now)
    return attempt


def check_reopen(attempt, request, now=None):
    """Called when the exam page is opened again while the test is running.

    A quick reload is only logged; if the page was gone for longer than
    ``REOPEN_GRACE_SECONDS`` (closed, browser killed, …) it counts as a leave.
    """
    now = now or timezone.now()
    gap = int((now - attempt.last_seen_at).total_seconds()) if attempt.last_seen_at else 0
    attempt.last_seen_at = now
    attempt.save(update_fields=['last_seen_at'])
    if gap > REOPEN_GRACE_SECONDS:
        register_leave(attempt, 'reopen', now, data={'seconds': gap})
    else:
        log_event('reload', attempt, data={'seconds': gap}, request=request, now=now)
    return attempt


def touch(attempt, now=None, log_gap=True):
    """Remember that the page is alive; long silences go to the log."""
    now = now or timezone.now()
    if log_gap and attempt.last_seen_at:
        gap = int((now - attempt.last_seen_at).total_seconds())
        if gap > CONNECTION_GAP_SECONDS:
            log_event('connection_gap', attempt, data={'seconds': gap}, now=now)
    attempt.last_seen_at = now
    attempt.save(update_fields=['last_seen_at'])


def _resolve(attempt, q_index, o_index):
    order = attempt.question_order or []
    if not isinstance(q_index, int) or isinstance(q_index, bool) or not 0 <= q_index < len(order):
        raise ExamError('bad_request', "Savol topilmadi.")
    question_id = order[q_index]
    choices = (attempt.choice_order or {}).get(str(question_id)) or []
    if not isinstance(o_index, int) or isinstance(o_index, bool) or not 0 <= o_index < len(choices):
        raise ExamError('bad_request', "Javob varianti topilmadi.")
    return question_id, choices[o_index], choices


def save_answer(attempt, q_index, o_index, now=None, source='click'):
    """Store the student's choice for one question (call with a locked, running attempt)."""
    now = now or timezone.now()
    question_id, choice_id, choices = _resolve(attempt, q_index, o_index)
    answer = Answer.objects.filter(attempt=attempt, question_id=question_id).first()
    log = attempt.event_count < MAX_EVENTS_PER_ATTEMPT
    data = {'n': q_index + 1, 'letter': option_letter(o_index)}
    if source != 'click':
        data['source'] = source
    if answer is None:
        Answer.objects.create(attempt=attempt, question_id=question_id, choice_id=choice_id)
        if log:
            log_event('answer', attempt, data=data, now=now)
    elif answer.choice_id != choice_id:
        old = choices.index(answer.choice_id) if answer.choice_id in choices else -1
        data['old'] = option_letter(old)
        answer.choice_id = choice_id
        answer.changes += 1
        answer.save(update_fields=['choice', 'changes', 'updated_at'])
        if log:
            log_event('answer_change', attempt, data=data, now=now)
    return choice_id


def apply_snapshot(attempt, answers, now=None):
    """Store the answers the browser had selected (used on leave / finish)."""
    if not isinstance(answers, dict):
        return 0
    stored = 0
    for key, value in list(answers.items())[:200]:
        try:
            q_index, o_index = int(key), int(value)
        except (TypeError, ValueError, OverflowError):
            continue
        try:
            save_answer(attempt, q_index, o_index, now, source='snapshot')
            stored += 1
        except ExamError:
            continue
    return stored


def accepts_answers(attempt, now=None):
    now = now or timezone.now()
    deadline = attempt.deadline
    return (
        attempt.status == Attempt.RUNNING and deadline is not None
        and now < deadline + timedelta(seconds=ANSWER_GRACE_SECONDS)
    )


def exam_payload(attempt, now=None):
    """What the browser needs to show the test: questions in the student's order
    (no correct answers, no database ids), the stored answers and the clock."""
    now = now or timezone.now()
    order = attempt.question_order or []
    questions = {
        q.pk: q for q in Question.objects.filter(pk__in=order).prefetch_related('choices')
    }
    items = []
    for question_id in order:
        question = questions.get(question_id)
        if question is None:
            items.append({'text': "(savol oʻchirilgan)", 'code': '', 'options': []})
            continue
        by_id = {c.pk: c for c in question.choices.all()}
        ids = (attempt.choice_order or {}).get(str(question_id), [])
        items.append({
            'text': question.text,
            'code': question.code,
            'options': [by_id[cid].text for cid in ids if cid in by_id],
        })
    position = {qid: i for i, qid in enumerate(order)}
    answers = {}
    for answer in Answer.objects.filter(attempt=attempt, choice__isnull=False):
        index = position.get(answer.question_id)
        ids = (attempt.choice_order or {}).get(str(answer.question_id), [])
        if index is not None and answer.choice_id in ids:
            answers[str(index)] = ids.index(answer.choice_id)
    return {
        'questions': items,
        'answers': answers,
        'remaining': attempt.remaining_seconds(now),
        'leave_count': attempt.leave_count,
        'max_leaves': attempt.exam.max_leaves,
    }


# ── teacher actions ───────────────────────────────────────────────────────────

TEACHER_ACTIONS = ('finish', 'extra', 'unlock', 'forgive', 'reopen', 'reset')


def teacher_action(attempt, action, teacher, minutes=5, now=None):
    """Apply a proctor action (call with a locked attempt). Returns a message for the teacher."""
    now = now or timezone.now()
    by = teacher.get_full_name() or teacher.username
    exam = attempt.exam

    if action == 'finish':
        if attempt.status != Attempt.RUNNING:
            raise ExamError('state', "Test davom etmayapti.")
        finalize(attempt, Attempt.REASON_TEACHER, now, data={'by': by})
        return "Test yakunlandi."

    if action == 'extra':
        if attempt.status != Attempt.RUNNING:
            raise ExamError('state', "Qoʻshimcha vaqtni faqat davom etayotgan testga berish mumkin.")
        minutes = max(1, min(int(minutes or 5), 120))
        attempt.extra_minutes += minutes
        attempt.save(update_fields=['extra_minutes'])
        log_event('teacher_extra', attempt, data={'by': by, 'minutes': minutes}, now=now)
        return f"{minutes} daqiqa qoʻshildi."

    if action == 'unlock':
        attempt.device_hash = ''
        attempt.save(update_fields=['device_hash'])
        log_event('teacher_unlock', attempt, data={'by': by}, now=now)
        return "Talaba endi boshqa kompyuterda (qayta kirib) davom etishi mumkin."

    if action == 'forgive':
        if attempt.leave_count == 0:
            raise ExamError('state', "Hisobda chiqishlar yoʻq.")
        attempt.leave_count -= 1
        attempt.save(update_fields=['leave_count'])
        log_event('teacher_forgive', attempt, data={'by': by}, now=now)
        return "Bitta chiqish hisobdan chiqarildi."

    if action == 'reopen':
        if attempt.status != Attempt.FINISHED or not attempt.started_at:
            raise ExamError('state', "Faqat yakunlangan testni qayta ochish mumkin.")
        # Give back exactly the time the student still had when the test was closed.
        deadline = attempt.deadline
        left = max(0, int((deadline - attempt.finished_at).total_seconds())) if attempt.finished_at else 0
        left = max(left, 60)
        needed = int((now + timedelta(seconds=left) - deadline).total_seconds())
        if needed > 0:
            attempt.extra_minutes += -(-needed // 60)
        if attempt.leave_count >= exam.max_leaves:
            attempt.leave_count = exam.max_leaves - 1
        attempt.status = Attempt.RUNNING
        attempt.finish_reason = ''
        attempt.finished_at = None
        attempt.correct_count = None
        attempt.score = None
        attempt.last_seen_at = now
        attempt.save()
        log_event('teacher_reopen', attempt, data={'by': by}, now=now)
        return "Test qayta ochildi. Talaba qayta kirib davom etishi mumkin."

    if action == 'reset':
        used = Attempt.objects.filter(exam=exam).exclude(pk=attempt.pk).values_list('variant_id', flat=True)
        spare = (
            Variant.objects.filter(exam=exam).exclude(pk__in=list(used))
            .exclude(pk=attempt.variant_id).order_by('number').first()
        )
        if spare is not None:
            attempt.variant = spare
        Answer.objects.filter(attempt=attempt).delete()
        attempt.status = Attempt.ASSIGNED
        attempt.started_at = attempt.finished_at = attempt.last_seen_at = None
        attempt.finish_reason = ''
        attempt.extra_minutes = attempt.leave_count = attempt.fullscreen_exits = 0
        attempt.question_order, attempt.choice_order = [], {}
        attempt.question_count = 0
        attempt.correct_count = attempt.score = None
        attempt.device_hash = ''
        attempt.save()
        log_event('teacher_reset', attempt, data={'by': by, 'variant': attempt.variant.number}, now=now)
        return f"Urinish bekor qilindi. Talaba testni qaytadan boshlaydi ({attempt.variant.number}-variant)."

    raise ExamError('bad_action', "Nomaʼlum amal.")
