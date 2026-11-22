"""Export everything the finished oraliq exam left in the database to CSV files.

Used by ``python manage.py export_oraliq_results`` (run it before the cleanup) and
by migration 0002, which runs the same export automatically right before it deletes
the old exam's tables and student accounts.

The models are taken from the *migration state* (``apps.get_model``), not imported,
so the export keeps working after the old app code has been removed — as long as
the tables still exist.
"""
import csv
import os
import re
from pathlib import Path

from django.conf import settings
from django.utils import timezone

STATUS = {'assigned': 'Boshlanmagan', 'running': 'Davom etmoqda', 'finished': 'Yakunlangan'}
REASON = {
    'submitted': 'Talaba oʻzi yakunladi',
    'time_up': 'Vaqt tugadi',
    'violations': 'Oynadan chiqish limiti tugadi',
    'teacher': 'Nazoratchi yakunladi',
}
LEVEL = {'info': 'Maʼlumot', 'warning': 'Ogohlantirish', 'danger': 'Qoidabuzarlik'}
ROLE = {'student': 'Talaba', 'teacher': 'Oʻqituvchi', 'moder': 'Moder', 'superadmin': 'SuperAdmin'}
LETTERS = 'ABCDEFGH'


def default_export_dir(now=None):
    base = Path(os.environ.get('ORALIQ_EXPORT_DIR') or settings.BASE_DIR)
    return base / f'oraliq_eksport_{(now or timezone.now()):%Y%m%d_%H%M%S}'


def _cell(value):
    text = '' if value is None else str(value)
    # Keep spreadsheet apps from treating text as a formula.
    return "'" + text if text[:1] in ('=', '+', '-', '@') else text


def _time(value):
    return value.strftime('%Y-%m-%d %H:%M:%S') if value else ''


def _natural(text):
    """student2 before student10."""
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r'(\d+)', text or '')]


def _name(user):
    return f'{user.first_name} {user.last_name}'.strip()


def _write(path, header, rows):
    with path.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        count = 0
        for row in rows:
            writer.writerow([_cell(v) for v in row])
            count += 1
    return count


def export_oraliq(apps, out_dir):
    """Write the CSV files to ``out_dir`` (created) and return {file name: rows}."""
    Exam = apps.get_model('oraliq_nazorat', 'Exam')
    Attempt = apps.get_model('oraliq_nazorat', 'Attempt')
    Answer = apps.get_model('oraliq_nazorat', 'Answer')
    Choice = apps.get_model('oraliq_nazorat', 'Choice')
    Question = apps.get_model('oraliq_nazorat', 'Question')
    Event = apps.get_model('oraliq_nazorat', 'Event')
    LoginAttempt = apps.get_model('oraliq_nazorat', 'LoginAttempt')
    UserProfile = apps.get_model('user', 'UserProfile')

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=False)
    exams = {e.pk: e.title for e in Exam.objects.all()}
    attempts = sorted(Attempt.objects.select_related('user', 'variant'),
                      key=lambda a: (a.exam_id, _natural(a.user.username)))
    roles = dict(UserProfile.objects.values_list('user_id', 'role'))
    counts = {}

    def used(a):
        if not (a.started_at and a.finished_at):
            return ''
        seconds = int((a.finished_at - a.started_at).total_seconds())
        return f'{seconds // 60}:{seconds % 60:02d}'

    answered = {}
    for attempt_id in Answer.objects.filter(choice__isnull=False).values_list('attempt_id', flat=True):
        answered[attempt_id] = answered.get(attempt_id, 0) + 1

    counts['natijalar.csv'] = _write(out_dir / 'natijalar.csv', [
        '№', 'Login', 'F.I.Sh', 'Imtihon', 'Variant', 'Holat', 'Boshlangan', 'Yakunlangan',
        'Sarflangan vaqt', 'Javob berilgan', 'Toʻgʻri', 'Savollar', 'Natija (%)', 'Oynadan chiqish',
        'Toʻliq ekrandan chiqish', 'Yakunlanish sababi', 'IP manzil', 'Brauzer',
    ], (
        [n, a.user.username, _name(a.user), exams.get(a.exam_id, ''), a.variant.number,
         STATUS.get(a.status, a.status), _time(a.started_at), _time(a.finished_at), used(a),
         answered.get(a.pk, 0), a.correct_count, a.question_count or '', a.score, a.leave_count,
         a.fullscreen_exits, REASON.get(a.finish_reason, a.finish_reason), a.ip_address, a.user_agent]
        for n, a in enumerate(attempts, start=1)
    ))

    def answer_rows():
        questions = {q.pk: q for q in Question.objects.all()}
        choices = {c.pk: c for c in Choice.objects.all()}
        for a in attempts:
            if not a.question_order:
                continue
            given = {ans.question_id: ans for ans in Answer.objects.filter(attempt_id=a.pk)}
            for index, qid in enumerate(a.question_order, start=1):
                q = questions.get(qid)
                order = (a.choice_order or {}).get(str(qid), [])

                def label(choice_id):
                    if choice_id not in choices:
                        return ''
                    letter = LETTERS[order.index(choice_id)] if choice_id in order else '?'
                    return f'{letter}) {choices[choice_id].text}'

                correct = next((cid for cid in order if cid in choices and choices[cid].is_correct), None)
                ans = given.get(qid)
                chosen = ans.choice_id if ans else None
                result = 'Javob yoʻq' if not chosen else ('Toʻgʻri' if chosen == correct else 'Notoʻgʻri')
                yield [a.user.username, _name(a.user), a.variant.number, index, q.ref if q else '',
                       q.text if q else '(savol topilmadi)', label(chosen) if chosen else '',
                       label(correct) if correct else '', result, ans.changes if ans else 0]

    counts['javoblar.csv'] = _write(out_dir / 'javoblar.csv', [
        'Login', 'F.I.Sh', 'Variant', 'Savol tartibi', 'Bank raqami', 'Savol', 'Talaba javobi',
        'Toʻgʻri javob', 'Natija', 'Oʻzgartirishlar',
    ], answer_rows())

    counts['hodisalar.csv'] = _write(out_dir / 'hodisalar.csv', [
        'Login', 'Vaqt', 'Hodisa', 'Daraja', 'Tavsif', 'IP manzil',
    ], (
        [e.user.username if e.user_id else '', _time(e.created_at), e.kind, LEVEL.get(e.level, e.level),
         e.message, e.ip_address]
        for e in Event.objects.select_related('user').order_by('created_at', 'id').iterator()
    ))

    users = sorted({a.user_id: a.user for a in attempts}.values(), key=lambda u: _natural(u.username))
    by_user = {a.user_id: a for a in attempts}
    counts['talabalar.csv'] = _write(out_dir / 'talabalar.csv', [
        'Login', 'Email', 'F.I.Sh', 'Rol', 'Roʻyxatdan oʻtgan', 'Oxirgi kirish', 'Variant', 'Holat',
    ], (
        [u.username, u.email, _name(u), ROLE.get(roles.get(u.pk), roles.get(u.pk, '')),
         _time(u.date_joined), _time(u.last_login), by_user[u.pk].variant.number,
         STATUS.get(by_user[u.pk].status, by_user[u.pk].status)]
        for u in users
    ))

    counts['kirish_urinishlari.csv'] = _write(out_dir / 'kirish_urinishlari.csv', [
        'Login (kiritilgan)', 'Muvaffaqiyatli', 'Vaqt', 'IP manzil',
    ], (
        [la.email, 'ha' if la.success else 'yoʻq', _time(la.created_at), la.ip_address]
        for la in LoginAttempt.objects.order_by('created_at').iterator()
    ))
    return counts


def migration_state_apps(connection):
    """Models as of the migrations applied to this database (works without the app code)."""
    from django.db.migrations.loader import MigrationLoader

    loader = MigrationLoader(connection, ignore_no_migrations=True)
    return loader.project_state(list(loader.applied_migrations)).apps


def old_tables_exist(connection):
    return 'oraliq_nazorat_attempt' in connection.introspection.table_names()
