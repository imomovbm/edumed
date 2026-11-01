"""Small factories shared by the test suites (``python manage.py test``)."""
from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from courses.models import Question, QuestionChoice, Quiz, QuizQuestion, Topic
from user.models import UserProfile

PASSWORD = 'Hamshira-2026!'


def make_user(email, role='student', password=PASSWORD, **profile):
    user = User.objects.create_user(
        username=email, email=email, password=password,
        first_name=email.split('@')[0].title(), last_name='Testov',
    )
    if role is not None:
        UserProfile.objects.create(user=user, role=role, **profile)
    return user


def make_question(text, qtype, choices=(), correct=()):
    """choices: texts; correct: indexes of correct choices (TF uses correct=(0,) for 'true')."""
    question = Question.objects.create(question_text=text, type=qtype)
    if qtype == 'tf' and not choices:
        choices = ("To'g'ri", "Noto'g'ri")
    for i, choice_text in enumerate(choices):
        QuestionChoice.objects.create(question=question, choice_text=choice_text, is_correct=i in correct)
    return question


def make_quiz(title, questions, topic=None, qtype=None, duration=15):
    quiz = Quiz.objects.create(
        title=title, type=qtype or ('1' if topic else '2'), topic=topic, duration=duration,
    )
    for order, question in enumerate(questions, start=1):
        QuizQuestion.objects.create(quiz=quiz, question=question, order=order)
    return quiz


def make_topic(title='Hamshiralik tarixi', **kwargs):
    return Topic.objects.create(title=title, **kwargs)


def choice_id(question, text):
    return str(question.questionchoice_set.get(choice_text=text).pk)


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class EdumedTestCase(TestCase):
    """Creates an admin, a teacher, a moderator and two students."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = make_user('admin@edumed.uz', 'superadmin')
        cls.teacher = make_user('teacher@edumed.uz', 'teacher')
        cls.moder = make_user('moder@edumed.uz', 'moder')
        cls.student = make_user('student@edumed.uz', 'student')
        cls.other = make_user('other@edumed.uz', 'student')

    def login(self, user):
        self.client.force_login(user)
        return self.client

    def messages_of(self, response):
        return [str(m) for m in response.context['messages']] if response.context else []
