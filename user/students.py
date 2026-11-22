"""Creating and managing exam students and their groups.

Everything that creates or changes a student goes through these functions, so the
quick-add form now and an Excel/CSV import later share the same rules:

    create_student(login, password, full_name, group)

* the login is unique (case-insensitive, also against other users' e-mails);
* the password has at least ``MIN_PASSWORD_LENGTH`` characters and is stored only
  as a hash (``User.set_password``) — it is never kept, shown or logged;
* names are trimmed, and ``group`` may be a StudentGroup or a group name (a new
  group is created when the name does not exist yet).

Problems raise :class:`StudentError` with one message per form field.
"""
from django.contrib.auth.models import User
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Q

from .models import StudentGroup, UserProfile

MIN_PASSWORD_LENGTH = 6
MAX_PASSWORD_LENGTH = 128
MAX_LOGIN_LENGTH = 150
MAX_NAME_LENGTH = 150
MAX_GROUP_LENGTH = 100

MESSAGES = {
    'login_required': "Loginni kiriting.",
    'login_long': f"Login {MAX_LOGIN_LENGTH} belgidan oshmasligi kerak.",
    'login_chars': "Login faqat harf, raqam va . @ + - _ belgilaridan iborat boʻlishi mumkin (boʻsh joysiz).",
    'login_taken': "«{login}» logini band — boshqasini tanlang.",
    'password_short': f"Parol kamida {MIN_PASSWORD_LENGTH} ta belgidan iborat boʻlishi kerak.",
    'password_long': f"Parol {MAX_PASSWORD_LENGTH} belgidan oshmasligi kerak.",
    'password_spaces': "Parolning boshida yoki oxirida boʻsh joy boʻlmasligi kerak.",
    'name_required': "Ism-familiyani kiriting.",
    'name_long': f"Ism-familiya {MAX_NAME_LENGTH} belgidan oshmasligi kerak.",
    'group_required': "Guruhni tanlang yoki yangi guruh nomini yozing.",
    'group_long': f"Guruh nomi {MAX_GROUP_LENGTH} belgidan oshmasligi kerak.",
    'group_taken': "«{name}» nomli guruh allaqachon bor.",
}


class StudentError(ValueError):
    """Validation problems as {field: message}."""

    def __init__(self, errors):
        self.errors = dict(errors)
        super().__init__('; '.join(self.errors.values()))


def _spaces(text):
    return ' '.join(str(text or '').split())


def clean_login(login, exclude=None):
    login = str(login or '').strip()
    if not login:
        raise StudentError({'login': MESSAGES['login_required']})
    if len(login) > MAX_LOGIN_LENGTH:
        raise StudentError({'login': MESSAGES['login_long']})
    try:
        UnicodeUsernameValidator()(login)
    except ValidationError:
        raise StudentError({'login': MESSAGES['login_chars']}) from None
    taken = User.objects.filter(Q(username__iexact=login) | Q(email__iexact=login))
    if exclude is not None:
        taken = taken.exclude(pk=exclude.pk)
    if taken.exists():
        raise StudentError({'login': MESSAGES['login_taken'].format(login=login)})
    return login


def clean_password(password):
    password = '' if password is None else str(password)
    if len(password) < MIN_PASSWORD_LENGTH:
        raise StudentError({'password': MESSAGES['password_short']})
    if len(password) > MAX_PASSWORD_LENGTH:
        raise StudentError({'password': MESSAGES['password_long']})
    if password != password.strip():
        raise StudentError({'password': MESSAGES['password_spaces']})
    return password


def clean_full_name(full_name):
    full_name = _spaces(full_name)
    if not full_name:
        raise StudentError({'full_name': MESSAGES['name_required']})
    if len(full_name) > MAX_NAME_LENGTH:
        raise StudentError({'full_name': MESSAGES['name_long']})
    return full_name


def clean_group_name(name):
    name = _spaces(name)
    if not name:
        raise StudentError({'group': MESSAGES['group_required']})
    if len(name) > MAX_GROUP_LENGTH:
        raise StudentError({'group': MESSAGES['group_long']})
    return name


def resolve_group(group):
    """A StudentGroup, or the group with this name (created when missing)."""
    if isinstance(group, StudentGroup):
        return group
    name = clean_group_name(group)
    existing = StudentGroup.objects.filter(name__iexact=name).first()
    return existing or StudentGroup.objects.create(name=name)


def _collect(*checks):
    """Run every check and raise one StudentError with all problems."""
    values, errors = [], {}
    for check in checks:
        try:
            values.append(check())
        except StudentError as exc:
            errors.update(exc.errors)
            values.append(None)
    if errors:
        raise StudentError(errors)
    return values


def _check_group(group):
    if isinstance(group, StudentGroup):
        return group
    return clean_group_name(group)


@transaction.atomic
def create_student(login, password, full_name, group):
    """Create a student account (role "student") in a group and return the User."""
    login, password, full_name, group = _collect(
        lambda: clean_login(login),
        lambda: clean_password(password),
        lambda: clean_full_name(full_name),
        lambda: _check_group(group),
    )
    group = resolve_group(group)
    user = User(username=login, first_name=full_name[:MAX_NAME_LENGTH], last_name='', email='')
    user.set_password(password)
    user.save()
    UserProfile.objects.create(user=user, role='student', group=group)
    return user


@transaction.atomic
def update_student(user, login, full_name, group):
    login, full_name, group = _collect(
        lambda: clean_login(login, exclude=user),
        lambda: clean_full_name(full_name),
        lambda: _check_group(group),
    )
    group = resolve_group(group)
    user.username = login
    user.first_name = full_name
    user.last_name = ''
    user.save(update_fields=['username', 'first_name', 'last_name'])
    profile, _ = UserProfile.objects.get_or_create(user=user, defaults={'role': 'student'})
    profile.group = group
    profile.save(update_fields=['group'])
    return user


def set_student_password(user, password):
    """Replace the password (stored as a hash). Other sessions of the user end."""
    (password,) = _collect(lambda: clean_password(password))
    user.set_password(password)
    user.save(update_fields=['password'])
    return user


def students():
    """Student accounts with their group, ordered by group and name."""
    return (
        User.objects.filter(userprofile__role='student')
        .select_related('userprofile', 'userprofile__group')
        .order_by('userprofile__group__name', 'first_name', 'username')
    )


@transaction.atomic
def create_group(name):
    (name,) = _collect(lambda: clean_group_name(name))
    if StudentGroup.objects.filter(name__iexact=name).exists():
        raise StudentError({'group': MESSAGES['group_taken'].format(name=name)})
    return StudentGroup.objects.create(name=name)


@transaction.atomic
def rename_group(group, name):
    (name,) = _collect(lambda: clean_group_name(name))
    if StudentGroup.objects.filter(name__iexact=name).exclude(pk=group.pk).exists():
        raise StudentError({'group': MESSAGES['group_taken'].format(name=name)})
    group.name = name
    group.save(update_fields=['name'])
    return group


def groups_with_counts():
    return StudentGroup.objects.annotate(student_count=Count('members')).order_by('name')
