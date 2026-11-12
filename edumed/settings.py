"""
Django settings for edumed project.

All environment-specific values are read from the `.env` file (python-decouple).
Every optional value below has a default that matches the previous behaviour,
so an existing `.env` keeps working without changes.

Docs: https://docs.djangoproject.com/en/stable/ref/settings/
"""
from pathlib import Path

import pymysql
from decouple import Csv, config

pymysql.install_as_MySQLdb()
# Django's MySQL backend checks the mysqlclient version; pretend to be a recent one.
pymysql.version_info = (2, 2, 1, "final", 0)

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config("DJANGO_SECRET_KEY")
# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = config('DEBUG', default=False, cast=bool)

ALLOWED_HOSTS = config(
    'ALLOWED_HOSTS',
    default='edumed.uz,www.edumed.uz,127.0.0.1,localhost',
    cast=Csv(),
)
# Needed for POST forms when the site is served over HTTPS (Django 4+ checks Origin).
CSRF_TRUSTED_ORIGINS = config(
    'CSRF_TRUSTED_ORIGINS',
    default='https://edumed.uz,https://www.edumed.uz',
    cast=Csv(),
)


# Application definition

INSTALLED_APPS = [
    'courses',
    'user',
    'oraliq_nazorat',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]


MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'edumed.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'user.context_processors.user_profile',
            ],
        },
    },
]

WSGI_APPLICATION = 'edumed.wsgi.application'


# Database
# DB_ENGINE=mysql (default, production) or DB_ENGINE=sqlite (quick local development / tests).

DB_ENGINE = config('DB_ENGINE', default='mysql').strip().lower()

if DB_ENGINE == 'sqlite':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
            # Concurrent writers (e.g. several students taking the exam) wait for
            # each other instead of failing with "database is locked".
            'OPTIONS': {'transaction_mode': 'IMMEDIATE', 'timeout': 20},
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": config("DB_NAME"),
            "USER": config("DB_USER"),
            "PASSWORD": config("DB_PASSWORD"),
            "HOST": config("DB_HOST", default="localhost"),
            "PORT": config("DB_PORT", default="3306"),
            "OPTIONS": {
                "charset": "utf8mb4",
                "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
            },
        }
    }

# Password validation
# https://docs.djangoproject.com/en/stable/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

LOGIN_URL = 'user:login'


# Internationalization
# https://docs.djangoproject.com/en/stable/topics/i18n/

LANGUAGE_CODE = 'uz-uz'

USE_I18N = True
# Kept off on purpose: month-based statistics use __year/__month lookups, which on
# MySQL need the timezone tables when USE_TZ is on.
USE_TZ = False


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/stable/howto/static-files/

STATIC_URL = 'static/'

STATICFILES_DIRS = [
    BASE_DIR / "static",
]
STATIC_ROOT = BASE_DIR / "staticfiles"  # For collectstatic

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# HTTPS hardening (all opt-in, enable in .env once the site is served over HTTPS)
SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=False, cast=bool)
SESSION_COOKIE_SECURE = config('SESSION_COOKIE_SECURE', default=False, cast=bool)
CSRF_COOKIE_SECURE = config('CSRF_COOKIE_SECURE', default=False, cast=bool)
SECURE_HSTS_SECONDS = config('SECURE_HSTS_SECONDS', default=0, cast=int)
if config('USE_X_FORWARDED_PROTO', default=False, cast=bool):
    # Behind nginx/another proxy that terminates TLS and sets X-Forwarded-Proto.
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')


# Optional: Claude AI analysis on the profile page ("AI orqali baholash").
# Leave ANTHROPIC_API_KEY empty to keep the feature switched off.
ANTHROPIC_API_KEY = config('ANTHROPIC_API_KEY', default='')
ANTHROPIC_MODEL = config('ANTHROPIC_MODEL', default='claude-opus-5-5')
