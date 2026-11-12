# EDUMED.UZ

Interactive learning platform for future nurses (Uzbek). Students read topics,
take timed quizzes with anti-cheat rules, discuss in forums and follow their
progress; administrators and teachers manage content and check written answers.

Built with Django 6 + SB Admin 2 (Bootstrap 4).

## Roles

| Role (`UserProfile.role`) | Can do |
|---|---|
| `student` (Talaba) | read topics, take quizzes, see own results, forums |
| `teacher` (O'qituvchi) | + check short/essay answers ("Javoblarni tekshirish"), see students' results |
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

## Oraliq nazorat (proctored midterm exam)

A separate app at **`/oraliq-nazorat/`** with its own login page, a waiting room
with the exam rules, and a 20-minute, 15-question test built from lectures 2–6 of
"Big Data tahlili" plus JSON and Python questions. Teachers watch it live at
**`/oraliq-nazorat/nazorat/`** (also linked from the main sidebar for teachers).

```bash
python manage.py migrate
python manage.py setup_oraliq_nazorat          # exam + 41 variants + student1..student40@mail.uz
```

The command prints every student's e-mail, numeric password and variant and saves
them to `oraliq_nazorat_parollar.csv` (git-ignored — keep it away from students).
Running it again changes nothing; useful options:

| Option | Effect |
|---|---|
| `--students 41` | create one more account (`student41@mail.uz`) |
| `--reset-passwords` | give every student a new password (new CSV) |
| `--closed` | create the exam closed; open it from the dashboard when the room is ready |
| `--duration 25`, `--max-leaves 3` | change the time limit / leave limit |
| `--rebuild` | rebuild questions and variants (refused once anyone started; `--force` deletes results) |

**Fairness.** The question bank (`oraliq_nazorat/bank/`, 296 questions) is tagged by
topic and difficulty; every variant takes one question from each of 15 topic/difficulty
slots, so all variants cover the same topics at the same difficulty. Questions that
would give each other away never share a variant, and any two variants share at most
one question. Every student gets a different variant; the 41st is kept as a spare for
a retake. Choice order is shuffled for every student, and the browser never receives
the correct answers or database ids.

**Anti-cheat.** Fullscreen is required (questions are hidden outside it); leaving the
exam window — another tab, window or app, an extension panel, closing the page —
is counted on the server, and the **3rd time finishes the test** with the answers
selected so far (every answer is saved the moment it is clicked). Copy/paste, right
click, DevTools/print/tab shortcuts are blocked, injected extension panels are removed,
and the attempt is bound to the browser that started it. The 20-minute deadline is
enforced by the server. Every action is written to the event log shown on the
dashboard. Proctor actions: extra time, finish, forgive one leave, allow another
computer, reopen, or reset (retake with the spare variant).

Serve the site over HTTPS if possible: Chrome then also captures Esc, Alt+Tab and
the Windows key while the test is fullscreen (Keyboard Lock API). A browser cannot
see a phone on the desk — keep proctoring the room as usual.

## Tests

```bash
DB_ENGINE=sqlite DJANGO_SECRET_KEY=test python manage.py test
```
