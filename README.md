# EDUMED.UZ

Interactive learning platform for future nurses (Uzbek). Students read topics,
take timed quizzes with anti-cheat rules, discuss in forums and follow their
progress; administrators and teachers manage content and check written answers.

Built with Django 6 + SB Admin 2 (Bootstrap 4).

## Roles

| Role (`UserProfile.role`) | Can do |
|---|---|
| `student` (Talaba) | read topics, take quizzes, see own results, forums |
| `teacher` (O'qituvchi) | + check short/essay answers ("Javoblarni tekshirish"), see students' results, run exams ("Imtihonlar") |
| `moder` (Moder) | + delete any forum post / comment / topic comment |
| `superadmin` (SuperAdmin) | everything: topics, questions, quizzes, users, roles, password resets, CSV report |

A Django superuser (`createsuperuser`) is treated as `superadmin` automatically.
Roles are changed on a user's page (Admin panel → Foydalanuvchilar → user).

## Setup

```bash
python -m venv venv
source venv/bin/activate            # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Create `.env` next to `manage.py`:

```ini
DJANGO_SECRET_KEY=change-me
DEBUG=False
DB_NAME=edumed
DB_USER=edumed
DB_PASSWORD=secret
# DB_HOST=localhost
# DB_PORT=3306

# --- optional ---------------------------------------------------------
# DB_ENGINE=sqlite                  # quick local run without MySQL
# ALLOWED_HOSTS=edumed.uz,www.edumed.uz,127.0.0.1,localhost
# CSRF_TRUSTED_ORIGINS=https://edumed.uz,https://www.edumed.uz
# HTTPS hardening, enable once the site is served only over HTTPS:
# SECURE_SSL_REDIRECT=True
# SESSION_COOKIE_SECURE=True
# CSRF_COOKIE_SECURE=True
# SECURE_HSTS_SECONDS=31536000
# USE_X_FORWARDED_PROTO=True        # behind nginx that sets X-Forwarded-Proto
# Claude AI analysis on the profile page ("AI orqali baholash"):
# ANTHROPIC_API_KEY=sk-ant-...
# ANTHROPIC_MODEL=claude-opus-5-5
```

The `static/` folder (SB Admin 2 vendor files, `img/avatar.png`, `manifest.json`,
`service-worker.js`) is not in git — copy it to the server as before.

```bash
python manage.py migrate
python manage.py load_topics        # optional: the 6 nursing lecture topics
python manage.py createsuperuser
python manage.py runserver
```

## After updating an existing server

```bash
python manage.py migrate                          # adds quiz duration, violation count, teacher feedback, ...
python manage.py recalculate_scores --dry-run     # preview fixes for old results
python manage.py recalculate_scores               # apply them
python manage.py collectstatic                    # if you serve static files with collectstatic
```

`recalculate_scores` fixes results stored by the old grader (true/false answers
were always marked wrong) and recomputes every student's topic progress.

If you enable the AI analysis, the request can take 10–30 seconds: give the WSGI
server enough time (e.g. `gunicorn --timeout 90`).

## Exams (`/imtihon/`)

A proctored exam platform for any number of exams. Teachers and administrators open it
from the sidebar ("Imtihonlar", `/imtihon/boshqaruv/`); students sign in at `/imtihon/`
with the login and password their teacher gave them and see only the exams assigned to
their group (or to them personally).

1. **Talabalar** — add students quickly: login, password (at least 6 characters, digits
   only are fine), full name and group (a new group can be created on the spot; the form
   stays open for the next student). Passwords are stored only as hashes and are never
   shown again — reset one on the student's page. **Guruhlar** — create, rename, delete.
2. **Imtihonlar → Yangi imtihon** — upload the tests as a `.txt` file. Every problem is
   listed with its question and line number (no correct answer, more than one correct
   answer, fewer than 2 options, duplicate options, empty question, wrong file type, file
   too large, unreadable encoding); fix them in the editor on the same page, re-check and
   save. The exam is created as a draft.
3. On the exam page set the duration, an optional start/end time (a running test ends at
   the end time), how many questions each student gets (all, or a random N), shuffling of
   questions and options, the leave limit, and the groups/students; then **Eʼlon qilish**.
4. **Kuzatuv va natijalar** — live dashboard (who is writing, time left, leaves of the exam
   window, scores), each student's answers and event log, proctor actions (extra time,
   another computer, reopen, reset), and CSV / Excel export. **Imtihonni yakunlash** closes
   the exam and grades the tests still running.

Test file format (UTF-8 or Windows-1251 text; Uzbek Latin/Cyrillic, Russian and symbols are fine):

```text
Savol matni?
====
#Toʻgʻri javob
====
Notoʻgʻri javob
====
Notoʻgʻri javob
++++
Keyingi savol?
...
```

`++++` ends a question, `====` separates the options, `#` marks the one correct option
(`\#` for a text that really starts with `#`). Questions and options may span several lines.

For developers: file formats live in `imtihon/importers/` — a new format is a
`BaseParser` subclass (`extensions` + `parse_text`) added to `PARSERS`. Students are
created only through `user.students.create_student(login, password, full_name, group)`,
which a future Excel/CSV import of students can reuse.

## Retiring the old "oraliq" exam (one-time, on the server)

The one-off midterm exam has been removed. Only a small shell (`oraliq_nazorat/`)
is left so its data can be retired safely, in this order:

1. Back up the database:
   ```bash
   mysqldump -u edumed -p --single-transaction edumed > edumed_backup_$(date +%Y%m%d).sql
   ```
2. Export the old exam's results and student data (CSV files that open in Excel,
   saved to `oraliq_eksport_<date>/` next to `manage.py`; git-ignored):
   ```bash
   python manage.py export_oraliq_results
   ```
3. Migrate. `oraliq_nazorat.0002` runs the same export again automatically, then
   deletes the exam's student accounts (`student<N>@mail.uz`) and drops the old tables:
   ```bash
   python manage.py migrate
   ```

Set `ORALIQ_EXPORT_DIR=/some/folder` if the project folder is not writable. Once every
database is migrated, remove `'oraliq_nazorat'` from `INSTALLED_APPS` and delete the
folder. To undo: restore the backup (`mysql -u edumed -p edumed < edumed_backup_<date>.sql`)
and revert the removal commit.

## Tests

```bash
DB_ENGINE=sqlite DJANGO_SECRET_KEY=test python manage.py test           # everything
DB_ENGINE=sqlite DJANGO_SECRET_KEY=test python manage.py test imtihon   # the exam platform only
```

The importer tests read the teachers' sample file `imtihon/tests/fixtures/q.txt`.
