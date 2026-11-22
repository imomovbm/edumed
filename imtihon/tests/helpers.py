"""Shared test data: accounts, exams built from test text, API calls."""
import json
from pathlib import Path

from django.contrib.auth.models import User
from django.test import override_settings
from django.urls import reverse

from user.models import UserProfile
from user.students import create_student

from .. import importers, services
from ..models import Choice, Exam

FIXTURES = Path(__file__).resolve().parent / 'fixtures'
SAMPLE = FIXTURES / 'q.txt'           # the teachers' sample file, unchanged
FAST_HASHER = override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
PASSWORD = '482916'


def make_teacher(username='ustoz', password='Ustoz-2026!', role='teacher'):
    user = User.objects.create_user(username, password=password, first_name='Ustoz')
    UserProfile.objects.create(user=user, role=role)
    return user


def make_student(login, group, password=PASSWORD, name=None):
    return create_student(login, password, name or f'Talaba {login}', group)


def question_text(n, options=4, correct=0):
    lines = [f'Savol {n}?']
    for i in range(options):
        lines += ['====', ('#' if i == correct else '') + f'Javob {n}.{i}']
    return '\n'.join(lines)


def make_text(count=10, options=4):
    return '\n++++\n'.join(question_text(n, options) for n in range(1, count + 1)) + '\n++++\n'


def make_exam(groups=(), students=(), count=10, status=Exam.PUBLISHED, title='Test imtihon', **fields):
    """An exam with ``count`` questions (option 0 correct in the file) assigned to groups/students."""
    result = importers.parse_text(make_text(count))
    assert result.ok, result.problems
    exam = services.create_exam_from_import(result, title, 'Fan', None)
    for name, value in fields.items():
        setattr(exam, name, value)
    exam.status = status
    exam.save()
    exam.groups.set(groups)
    exam.students.set(students)
    return exam


def api(client, exam, name, payload=None):
    return client.post(reverse(f'imtihon:api_{name}', args=[exam.pk]), json.dumps(payload or {}),
                       content_type='application/json')


def correct_position(attempt, q_index):
    """Where the correct option of the student's q_index-th question is shown."""
    qid = attempt.question_order[q_index]
    correct = Choice.objects.get(question_id=qid, is_correct=True).pk
    return attempt.choice_order[str(qid)].index(correct)
