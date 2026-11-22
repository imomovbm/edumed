# EDUMED.UZ

Interactive learning platform for future nurses (Uzbek). Built with Django 6 +
SB Admin 2 (Bootstrap 4); the whole interface is in Uzbek.

What it has (sidebar sections):

- **Mavzular** — lecture topics with sections, progress per topic.
- **Simulyatsiya** — hands-on practice: choose the right injection site on a picture
  (venadan qon olish, gluteal, deltoid, insulin). See [Simulations](#simulations-simulyatsiya).
- **Mening progressim** — the student's own results; optional AI analysis.
- **Topshiriqlar** — timed quizzes with anti-cheat rules; teachers check written answers
  ("Javoblarni tekshirish").
- **Forumlar** — discussions.
- **Imtihonlar** — proctored exams imported from test files, with a students/groups panel.
  See [Exams](#exams-imtihon).
- **Admin panel** — topics, questions, quizzes, users and roles (administrators).

## Roles

| Role (`UserProfile.role`) | Can do |
|---|---|
| `student` (Talaba) | read topics, practise in simulations, take quizzes and assigned exams, see own results, forums |
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

## Simulations (`/simulyatsiya/`)

Every signed-in user with a profile (students, teachers, administrators) can open the
**Simulyatsiya** panel. Each card opens one exercise: the student taps (or clicks, or
selects with the keyboard) the area where the injection should go and gets an immediate
"To'g'ri / Noto'g'ri" explanation, a hint and a "Qayta urinish" button. Nothing is saved.

Each simulation runs in a sandboxed iframe (`sandbox="allow-scripts"`, no same-origin):
it cannot read the site's cookies or storage, cannot navigate the page, and its own
Content-Security-Policy blocks every network request — all code is inline, nothing is
loaded from a CDN.

**Adding a simulation** (no other changes needed):

1. Copy one of `simulyatsiya/templates/simulyatsiya/sims/*.html` to `<id>.html`. It extends
   `simulyatsiya/frame_base.html` and calls `Simulation.start({...})` with:
   `draw(ctx)` (paints the picture on a 420×320 canvas), `check(x, y)` (true inside the
   correct area), `zones` (the lettered areas, used for keyboard and screen readers) and
   the `right` / `wrong` explanations. The instruction and hint are template blocks.
2. Add an entry to `SIMULATIONS` in `simulyatsiya/registry.py`: `id` (the file name and
   the URL), `title`, `description`, `icon` (a Font Awesome icon) and optionally
   `enabled=False` to hide it.

## Tests

```bash
DB_ENGINE=sqlite DJANGO_SECRET_KEY=test python manage.py test           # everything
DB_ENGINE=sqlite DJANGO_SECRET_KEY=test python manage.py test imtihon   # the exam platform only
DB_ENGINE=sqlite DJANGO_SECRET_KEY=test python manage.py test simulyatsiya
```

The importer tests read the teachers' sample file `imtihon/tests/fixtures/q.txt`.
