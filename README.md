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

## Tests

```bash
DB_ENGINE=sqlite DJANGO_SECRET_KEY=test python manage.py test
```
