"""Results of an exam: the live dashboard rows and the CSV / Excel exports."""
import csv
import io
import re

from django.db.models import Count, Q
from django.urls import reverse
from django.utils import timezone

from . import services
from .models import Answer, Attempt, Event, Question, option_letter

COLUMNS = [
    '№', 'Login', 'F.I.Sh', 'Guruh', 'Holat', 'Boshlangan', 'Yakunlangan', 'Sarflangan vaqt',
    'Javob berilgan', 'Toʻgʻri', 'Savollar', 'Natija (%)', 'Oynadan chiqish', 'Toʻliq ekrandan chiqish',
    'Ogohlantirishlar', 'Yakunlanish sababi',
]


def natural_key(text):
    """student2 before student10."""
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r'(\d+)', text or '')]


def _time(value, fmt='%H:%M:%S'):
    return value.strftime(fmt) if value else ''


def _duration(seconds):
    if seconds is None:
        return ''
    return f'{seconds // 60}:{seconds % 60:02d}'


def _group_name(user):
    profile = getattr(user, 'userprofile', None)
    return profile.group.name if profile and profile.group_id else ''


def exam_rows(exam, now=None):
    """One row per assigned student (or anyone who has an attempt), with live numbers."""
    now = now or timezone.now()
    services.finalize_expired(exam, now)
    attempts = {
        a.user_id: a for a in Attempt.objects.filter(exam=exam).select_related(
            'user', 'user__userprofile', 'user__userprofile__group', 'exam',
        ).annotate(
            answered=Count('answers', filter=Q(answers__choice__isnull=False), distinct=True),
            warnings=Count('events', filter=Q(events__level__in=[Event.WARNING, Event.DANGER]), distinct=True),
        )
    }
    users = {u.pk: u for u in services.eligible_students(exam)}
    for attempt in attempts.values():
        users.setdefault(attempt.user_id, attempt.user)
    question_total = exam.question_count or exam.questions.count()

    rows = []
    for user in users.values():
        a = attempts.get(user.pk)
        status = a.status if a else Attempt.ASSIGNED
        seen_ago = int((now - a.last_seen_at).total_seconds()) if a and a.last_seen_at else None
        rows.append({
            'id': a.pk if a else None,
            'login': user.username,
            'name': user.get_full_name(),
            'group': _group_name(user),
            'status': status,
            'status_label': a.get_status_display() if a else 'Boshlanmagan',
            'started': _time(a.started_at) if a else '',
            'finished': _time(a.finished_at) if a else '',
            'used': _duration(a.used_seconds) if a and a.finished_at else '',
            'remaining': a.remaining_seconds(now) if a and a.status == Attempt.RUNNING else None,
            'answered': a.answered if a else 0,
            'total': (a.question_count if a and a.question_count else question_total),
            'leaves': a.leave_count if a else 0,
            'fs_exits': a.fullscreen_exits if a else 0,
            'warnings': a.warnings if a else 0,
            'correct': a.correct_count if a else None,
            'score': a.score if a else None,
            'reason': a.get_finish_reason_display() if a and a.finish_reason else '',
            'seen_ago': seen_ago,
            'online': bool(a and a.status == Attempt.RUNNING and seen_ago is not None and seen_ago <= 25),
            'url': reverse('imtihon:manage_attempt', args=[a.pk]) if a else '',
        })
    rows.sort(key=lambda r: (natural_key(r['group']), natural_key(r['name'] or r['login']), natural_key(r['login'])))
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


def _table(exam):
    rows, _ = exam_rows(exam)
    for n, r in enumerate(rows, start=1):
        yield [
            n, r['login'], r['name'], r['group'], r['status_label'], r['started'], r['finished'], r['used'],
            r['answered'], r['correct'], r['total'], r['score'], r['leaves'], r['fs_exits'], r['warnings'],
            r['reason'],
        ]


def _safe(value):
    text = '' if value is None else str(value)
    # Keep spreadsheet apps from treating user text as a formula.
    return "'" + text if text[:1] in ('=', '+', '-', '@') else text


def export_filename(exam, ext):
    slug = re.sub(r'[^\w-]+', '_', exam.title, flags=re.UNICODE).strip('_')[:60] or 'imtihon'
    return f'natijalar_{slug}_{timezone.now():%Y%m%d_%H%M}.{ext}'


def results_csv(exam):
    out = io.StringIO()
    out.write('\ufeff')  # BOM: Excel reads the file as UTF-8
    writer = csv.writer(out)
    writer.writerow(COLUMNS)
    for row in _table(exam):
        writer.writerow([_safe(v) for v in row])
    return out.getvalue().encode('utf-8')


def _answer_rows(exam):
    questions = {q.pk: q for q in Question.objects.filter(exam=exam).prefetch_related('choices')}
    attempts = sorted(
        Attempt.objects.filter(exam=exam).exclude(question_order=[]).select_related('user'),
        key=lambda a: natural_key(a.user.username),
    )
    for a in attempts:
        given = {ans.question_id: ans.choice_id for ans in Answer.objects.filter(attempt=a)}
        for index, qid in enumerate(a.question_order, start=1):
            q = questions.get(qid)
            if q is None:
                continue
            by_id = {c.pk: c for c in q.choices.all()}
            order = (a.choice_order or {}).get(str(qid), [])

            def label(cid):
                if cid not in by_id:
                    return ''
                letter = option_letter(order.index(cid)) if cid in order else '?'
                return f'{letter}) {by_id[cid].text}'

            correct = next((cid for cid in order if cid in by_id and by_id[cid].is_correct), None)
            chosen = given.get(qid)
            result = 'Javob yoʻq' if not chosen else ('Toʻgʻri' if chosen == correct else 'Notoʻgʻri')
            yield [a.user.username, a.user.get_full_name(), index, q.order, q.text,
                   label(chosen) if chosen else '', label(correct) if correct else '', result]


def results_xlsx(exam):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    book = Workbook()
    sheets = [
        ('Natijalar', COLUMNS, list(_table(exam)), [5, 22, 28, 18, 14, 11, 11, 10, 9, 8, 9, 10, 9, 10, 10, 26]),
        ('Javoblar', ['Login', 'F.I.Sh', 'Savol (talabada)', 'Savol (faylda)', 'Savol matni', 'Talaba javobi',
                      'Toʻgʻri javob', 'Natija'], list(_answer_rows(exam)), [22, 28, 10, 10, 60, 40, 40, 12]),
    ]
    header_fill = PatternFill('solid', fgColor='E8EEFC')
    for index, (title, header, rows, widths) in enumerate(sheets):
        sheet = book.active if index == 0 else book.create_sheet()
        sheet.title = title
        sheet.append(header)
        for cell in sheet[1]:
            cell.font = Font(bold=True)
            cell.fill = header_fill
            cell.alignment = Alignment(vertical='center', wrap_text=True)
        for row in rows:
            sheet.append([_safe(v) if isinstance(v, str) else v for v in row])
        for col, width in enumerate(widths, start=1):
            sheet.column_dimensions[get_column_letter(col)].width = width
        sheet.freeze_panes = 'A2'
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()
