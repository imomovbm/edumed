"""Teacher pages: exams, importing tests, publishing, live proctoring, results."""
from pathlib import Path

from django.contrib import messages
from django.db import transaction
from django.db.models import Avg, Count, Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .. import importers, reports, services
from ..forms import ExamSettingsForm
from ..models import Answer, Attempt, Event, Exam, Question, option_letter
from ..services import ExamError
from .common import proctor_required

STATUS_ACTIONS = {
    'publish': (services.publish, "Imtihon eʼlon qilindi — biriktirilgan talabalar uni koʻra oladi."),
    'unpublish': (services.unpublish, "Imtihon qoralamaga qaytarildi."),
    'finish': (None, "Imtihon yakunlandi."),
    'reopen': (services.reopen_exam, "Imtihon qayta ochildi."),
}


@proctor_required
def exams_view(request):
    exams = Exam.objects.annotate(
        question_total=Count('questions', distinct=True),
        started=Count('attempts', filter=~Q(attempts__status=Attempt.ASSIGNED), distinct=True),
        finished=Count('attempts', filter=Q(attempts__status=Attempt.FINISHED), distinct=True),
        average=Avg('attempts__score', filter=Q(attempts__status=Attempt.FINISHED)),
    ).prefetch_related('groups').order_by('-created_at')
    return render(request, 'imtihon/manage/exams.html', {'exams': exams, 'nav': 'exams'})


# ── import ────────────────────────────────────────────────────────────────────

@proctor_required
def import_view(request, exam_id=None):
    """Upload a test file → preview with every problem → fix in the editor → save as a draft."""
    exam = get_object_or_404(Exam, pk=exam_id) if exam_id else None
    if exam and exam.attempts.exists():
        messages.error(request, "Talabalar imtihonni boshlagan — savollarni almashtirib boʻlmaydi.")
        return redirect('imtihon:manage_exam', exam_id=exam.pk)

    context = {
        'exam': exam,
        'nav': 'exams',
        'accept': ','.join(importers.accepted_extensions()),
        'accept_label': ', '.join(importers.accepted_extensions()),
        'max_mb': importers.MAX_FILE_BYTES // (1024 * 1024),
        'title': exam.title if exam else '',
        'subject': exam.subject if exam else '',
    }
    if request.method != 'POST':
        return render(request, 'imtihon/manage/import.html', context)

    upload = request.FILES.get('file')
    if upload:
        data = upload.read(importers.MAX_FILE_BYTES + 1)
        result = importers.parse_file(data, upload.name)
        source_name = upload.name
    elif 'text' in request.POST:
        result = importers.parse_text(request.POST.get('text', ''))
        source_name = request.POST.get('source_name', '')
    else:
        result = importers.parse_file(b'', '')
        source_name = ''
    title = ' '.join((request.POST.get('title') or '').split())
    subject = ' '.join((request.POST.get('subject') or '').split())
    if not title and not exam:
        title = Path(source_name).stem.replace('_', ' ').strip() if source_name else ''
    context.update(result=result, title=title or context['title'], subject=subject or context['subject'],
                   source_name=source_name[:255])

    if request.POST.get('action') == 'save':
        if not result.ok:
            context['save_error'] = "Xatolar tuzatilmaguncha saqlab boʻlmaydi."
        elif not title and not exam:
            context['save_error'] = "Imtihon nomini kiriting."
        elif exam:
            with transaction.atomic():
                count = services.save_imported_questions(exam, result.questions)
                exam.source_name = source_name[:255] or exam.source_name
                exam.save(update_fields=['source_name', 'updated_at'])
            messages.success(request, f"Savollar almashtirildi: {count} ta savol.")
            return redirect('imtihon:manage_exam', exam_id=exam.pk)
        else:
            exam = services.create_exam_from_import(result, title[:200], subject[:200], request.user, source_name)
            messages.success(request, f"Qoralama imtihon yaratildi: {exam.questions.count()} ta savol. "
                                      "Endi sozlamalarni va guruhlarni tanlab, eʼlon qiling.")
            return redirect('imtihon:manage_exam', exam_id=exam.pk)
    return render(request, 'imtihon/manage/import.html', context)


# ── one exam ──────────────────────────────────────────────────────────────────

def _questions_with_choices(exam):
    return list(exam.questions.prefetch_related('choices').order_by('order'))


@proctor_required
def exam_view(request, exam_id):
    exam = get_object_or_404(Exam, pk=exam_id)
    questions = _questions_with_choices(exam)
    has_attempts = exam.attempts.exists()
    form = ExamSettingsForm(request.POST or None, instance=exam, question_total=len(questions),
                            has_attempts=has_attempts)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            messages.success(request, "Sozlamalar saqlandi.")
            return redirect('imtihon:manage_exam', exam_id=exam.pk)
        messages.error(request, "Sozlamalarda xato bor — belgilangan maydonlarni tekshiring.")

    correct_first = sum(1 for q in questions if q.choices.all() and q.choices.all()[0].is_correct)
    return render(request, 'imtihon/manage/exam.html', {
        'exam': exam,
        'form': form,
        'questions': questions,
        'has_attempts': has_attempts,
        'publish_problems': services.publish_problems(exam) if exam.status == Exam.DRAFT else [],
        'correct_first': correct_first,
        'assigned_count': services.eligible_students(exam).count(),
        'attempt_counts': {
            'started': exam.attempts.exclude(status=Attempt.ASSIGNED).count(),
            'running': exam.attempts.filter(status=Attempt.RUNNING).count(),
            'finished': exam.attempts.filter(status=Attempt.FINISHED).count(),
        },
        'nav': 'exams',
    })


@proctor_required
@require_POST
def exam_status_view(request, exam_id):
    exam = get_object_or_404(Exam, pk=exam_id)
    action = request.POST.get('action')
    if action not in STATUS_ACTIONS:
        messages.error(request, "Nomaʼlum amal.")
        return redirect('imtihon:manage_exam', exam_id=exam.pk)
    function, success = STATUS_ACTIONS[action]
    try:
        if action == 'finish':
            closed = services.finish_exam(exam)
            if closed:
                success += f" Davom etayotgan {closed} ta test yakunlandi va baholandi."
        else:
            function(exam)
        messages.success(request, success)
    except ExamError as exc:
        messages.error(request, exc.message)
    return redirect(request.POST.get('next') or reverse('imtihon:manage_exam', args=[exam.pk]))


@proctor_required
def exam_delete_view(request, exam_id):
    exam = get_object_or_404(Exam, pk=exam_id)
    attempts = exam.attempts.exclude(status=Attempt.ASSIGNED).count()
    if request.method == 'POST':
        title = exam.title
        exam.delete()
        messages.success(request, f"«{title}» imtihoni oʻchirildi.")
        return redirect('imtihon:manage')
    return render(request, 'imtihon/manage/confirm_delete.html', {
        'nav': 'exams',
        'title': "Imtihonni oʻchirish",
        'object_name': exam.title,
        'warnings': ([f"{attempts} ta talabaning natijasi ham oʻchadi. Kerak boʻlsa, avval natijalarni "
                      f"yuklab oling."] if attempts else []) + [f"{exam.questions.count()} ta savol oʻchadi."],
        'cancel_url': reverse('imtihon:manage_exam', args=[exam.pk]),
        'export_url': reverse('imtihon:manage_export', args=[exam.pk, 'xlsx']) if attempts else '',
    })


# ── live proctoring ───────────────────────────────────────────────────────────

@proctor_required
def dashboard_view(request, exam_id):
    exam = get_object_or_404(Exam, pk=exam_id)
    rows, stats = reports.exam_rows(exam)
    return render(request, 'imtihon/manage/dashboard.html', {
        'exam': exam,
        'initial': {'rows': rows, 'stats': stats, 'time': timezone.now().strftime('%H:%M:%S')},
        'data_url': reverse('imtihon:manage_dashboard_data', args=[exam.pk]),
        'nav': 'exams',
    })


@proctor_required
@require_GET
def dashboard_data_view(request, exam_id):
    exam = get_object_or_404(Exam, pk=exam_id)
    rows, stats = reports.exam_rows(exam)
    return JsonResponse({'rows': rows, 'stats': stats, 'time': timezone.now().strftime('%H:%M:%S')})


@proctor_required
def attempt_view(request, pk):
    attempt = get_object_or_404(Attempt.objects.select_related('user', 'exam', 'user__userprofile__group'), pk=pk)
    if attempt.status == Attempt.RUNNING:
        with transaction.atomic():
            attempt = services.lock(attempt)
            services.expire_if_due(attempt)
    order = attempt.question_order or []
    questions = {q.pk: q for q in Question.objects.filter(pk__in=order).prefetch_related('choices')}
    answers = {a.question_id: a for a in Answer.objects.filter(attempt=attempt).select_related('choice')}
    rows = []
    for index, qid in enumerate(order):
        q = questions.get(qid)
        if q is None:
            continue
        by_id = {c.pk: c for c in q.choices.all()}
        ids = (attempt.choice_order or {}).get(str(qid)) or list(by_id)
        answer = answers.get(qid)
        chosen = option_letter(ids.index(answer.choice_id)) if answer and answer.choice_id in ids else None
        rows.append({
            'n': index + 1,
            'question': q,
            'options': [{'letter': option_letter(i), 'text': by_id[cid].text, 'correct': by_id[cid].is_correct}
                        for i, cid in enumerate(ids) if cid in by_id],
            'chosen': chosen,
            'is_correct': bool(answer and answer.choice and answer.choice.is_correct),
            'changes': answer.changes if answer else 0,
        })
    events = list(attempt.events.order_by('created_at', 'id'))
    if attempt.started_at:
        # Sign-ins around the attempt and opening the exam page before starting it.
        window_start = attempt.started_at - timezone.timedelta(hours=2)
        window_end = attempt.finished_at or timezone.now()
        extra = Event.objects.filter(user=attempt.user, attempt__isnull=True, created_at__range=(window_start, window_end))
        extra = extra.filter(Q(kind__in=services.LOGIN_EVENTS) | Q(exam=attempt.exam))
        events = sorted(events + list(extra), key=lambda e: (e.created_at, e.pk))
    return render(request, 'imtihon/manage/attempt.html', {
        'attempt': attempt,
        'exam': attempt.exam,
        'rows': rows,
        'events': events,
        'danger_count': sum(1 for e in events if e.level == Event.DANGER),
        'warning_count': sum(1 for e in events if e.level == Event.WARNING),
        'nav': 'exams',
    })


@proctor_required
@require_POST
def attempt_action_view(request, pk):
    attempt = get_object_or_404(Attempt, pk=pk)
    try:
        minutes = int(request.POST.get('minutes') or 5)
    except ValueError:
        minutes = 5
    try:
        with transaction.atomic():
            locked = services.lock(attempt)
            message = services.teacher_action(locked, request.POST.get('action'), request.user, minutes=minutes)
        messages.success(request, message)
    except ExamError as exc:
        messages.error(request, exc.message)
    return redirect('imtihon:manage_attempt', pk=attempt.pk)


@proctor_required
@require_GET
def export_view(request, exam_id, fmt):
    exam = get_object_or_404(Exam, pk=exam_id)
    if fmt == 'csv':
        response = HttpResponse(reports.results_csv(exam), content_type='text/csv; charset=utf-8')
    elif fmt == 'xlsx':
        response = HttpResponse(
            reports.results_xlsx(exam),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
    else:
        raise Http404("Bunday format yoʻq.")
    response['Content-Disposition'] = f'attachment; filename="{reports.export_filename(exam, fmt)}"'
    return response
