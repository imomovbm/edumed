import contextlib
import csv
import io
import json
import tempfile
from datetime import timedelta
from pathlib import Path

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from user.models import UserProfile

from . import services
from .bank import conflicts, load_bank, validate_bank
from .blueprint import QUESTIONS_PER_VARIANT, SLOTS
from .models import Answer, Attempt, Choice, Event, Exam, LoginAttempt, Question, Variant, VariantQuestion
from .variants import build_variants

FAST_HASHER = override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
PASSWORD = '482916'


def make_exam(students=2, variants=3, questions=QUESTIONS_PER_VARIANT, **exam_fields):
    """A small exam: `questions` questions (choice 0 correct) shared by every variant."""
    exam = Exam.objects.create(code=exam_fields.pop('code', 'test-exam'), title='Test imtihon', **exam_fields)
    qs = []
    for n in range(questions):
        q = Question.objects.create(exam=exam, ref=f'T-{n:02d}', topic='python', difficulty=2, text=f'Savol {n}?')
        for i in range(4):
            Choice.objects.create(question=q, text=f'Javob {n}.{i}', is_correct=(i == 0))
        qs.append(q)
    variant_objs = []
    for v in range(1, variants + 1):
        variant = Variant.objects.create(exam=exam, number=v)
        for order, q in enumerate(qs, start=1):
            VariantQuestion.objects.create(variant=variant, question=q, order=order)
        variant_objs.append(variant)
    users = []
    for n in range(1, students + 1):
        user = User.objects.create_user(f'student{n}@mail.uz', f'student{n}@mail.uz', PASSWORD,
                                        first_name='Talaba', last_name=str(n))
        UserProfile.objects.create(user=user, role='student')
        Attempt.objects.create(exam=exam, user=user, variant=variant_objs[n - 1])
        users.append(user)
    return exam, users


def post_json(client, name, payload=None):
    return client.post(reverse(f'oraliq_nazorat:{name}'), json.dumps(payload or {}), content_type='application/json')


class QuestionBankTests(TestCase):
    def setUp(self):
        self.bank = load_bank()

    def test_bank_is_valid_for_41_variants(self):
        self.assertEqual(validate_bank(self.bank, 41), [])

    def test_every_slot_has_enough_questions(self):
        for slot in SLOTS:
            count = sum(1 for q in self.bank if (q.topic, q.difficulty) == slot)
            self.assertGreaterEqual(count, 14, slot)

    def test_refs_are_unique_and_one_correct_answer_each(self):
        refs = [q.ref for q in self.bank]
        self.assertEqual(len(refs), len(set(refs)))
        for q in self.bank:
            self.assertEqual(len(q.options), 4, q.ref)
            self.assertEqual(q.options.count(q.correct), 1, q.ref)

    def test_code_questions_print_the_keyed_answer(self):
        """Every runnable Python/JSON question really prints its correct option."""
        checked = 0
        for q in self.bank:
            if q.topic not in ('python', 'json', 'mapreduce') or 'print(' not in q.code:
                continue
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                exec(compile(q.code, q.ref, 'exec'), {})  # noqa: S102 - our own bank
            printed = out.getvalue().strip()
            self.assertEqual(printed, q.correct, q.ref)
            self.assertNotIn(printed, q.wrong, q.ref)
            checked += 1
        self.assertGreaterEqual(checked, 30)


class VariantBuilderTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bank = load_bank()
        cls.report = build_variants(cls.bank, count=41, seed=2026)

    def test_shape_and_blueprint(self):
        self.assertEqual(len(self.report.variants), 41)
        for variant in self.report.variants:
            self.assertEqual([(q.topic, q.difficulty) for q in variant], SLOTS)
            self.assertEqual(len({q.ref for q in variant}), QUESTIONS_PER_VARIANT)

    def test_variants_are_different_and_fair(self):
        self.assertEqual(len({tuple(q.ref for q in v) for v in self.report.variants}), 41)
        self.assertLessEqual(self.report.max_overlap, 2)
        self.assertLessEqual(self.report.max_usage, 3)

    def test_no_question_gives_away_another_in_the_same_variant(self):
        self.assertEqual(self.report.conflicts, 0)
        for variant in self.report.variants:
            for i, a in enumerate(variant):
                for b in variant[i + 1:]:
                    self.assertFalse(conflicts(a, b), (a.ref, b.ref))

    def test_same_seed_same_variants(self):
        again = build_variants(self.bank, count=41, seed=2026)
        self.assertEqual([[q.ref for q in v] for v in again.variants],
                         [[q.ref for q in v] for v in self.report.variants])


@FAST_HASHER
class SetupCommandTests(TestCase):
    def run_command(self, *args):
        out = io.StringIO()
        call_command('setup_oraliq_nazorat', *args, stdout=out)
        return out.getvalue()

    def read_csv(self, path):
        with open(path, encoding='utf-8-sig') as handle:
            return list(csv.DictReader(handle))

    def test_creates_exam_variants_and_40_students(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'parollar.csv'
            output = self.run_command('--output', str(path))
            rows = self.read_csv(path)

        exam = Exam.objects.get(code='big-data-oraliq')
        self.assertEqual(exam.duration_minutes, 20)
        self.assertEqual(exam.max_leaves, 3)
        self.assertEqual(exam.variants.count(), 41)
        self.assertEqual(VariantQuestion.objects.filter(variant__exam=exam).count(), 41 * 15)
        self.assertEqual(Question.objects.filter(exam=exam).count(), len(load_bank()))

        self.assertEqual(len(rows), 40)
        self.assertEqual([r['Email (login)'] for r in rows], [f'student{n}@mail.uz' for n in range(1, 41)])
        passwords = [r['Parol'] for r in rows]
        self.assertTrue(all(p.isdigit() and len(p) == 6 for p in passwords))
        self.assertEqual(len(set(passwords)), 40)
        user = User.objects.get(username='student7@mail.uz')
        self.assertTrue(user.check_password(rows[6]['Parol']))
        self.assertEqual(user.userprofile.role, 'student')

        attempts = Attempt.objects.filter(exam=exam)
        self.assertEqual(attempts.count(), 40)
        self.assertEqual(len(set(attempts.values_list('variant_id', flat=True))), 40)  # all different
        self.assertIn('Zaxira variant', output)

    def test_second_run_keeps_passwords_and_variants(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'p.csv'
            self.run_command('--students', '3', '--output', str(path))
            first = self.read_csv(path)
            before = dict(Attempt.objects.values_list('user__username', 'variant__number'))
            self.run_command('--students', '3', '--output', str(path))
            self.assertEqual(self.read_csv(path), first)  # file kept
        self.assertEqual(dict(Attempt.objects.values_list('user__username', 'variant__number')), before)
        self.assertTrue(User.objects.get(username='student1@mail.uz').check_password(first[0]['Parol']))

    def test_reset_passwords(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'p.csv'
            self.run_command('--students', '2', '--output', str(path))
            old = self.read_csv(path)[0]['Parol']
            self.run_command('--students', '2', '--reset-passwords', '--output', str(path))
            new = self.read_csv(path)[0]['Parol']
        user = User.objects.get(username='student1@mail.uz')
        self.assertTrue(user.check_password(new))
        if new != old:
            self.assertFalse(user.check_password(old))

    def test_rebuild_is_refused_after_a_student_started(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'p.csv'
            self.run_command('--students', '2', '--output', str(path))
            Attempt.objects.filter(user__username='student1@mail.uz').update(
                status=Attempt.RUNNING, started_at=timezone.now())
            with self.assertRaises(CommandError):
                self.run_command('--students', '2', '--rebuild', '--output', str(path))


@FAST_HASHER
class LoginTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.exam, (cls.student, _) = make_exam()
        cls.outsider = User.objects.create_user('boshqa@mail.uz', 'boshqa@mail.uz', PASSWORD)
        cls.teacher = User.objects.create_user('ustoz@mail.uz', 'ustoz@mail.uz', 'Ustoz-2026!')
        UserProfile.objects.create(user=cls.teacher, role='teacher')

    def login(self, email, password):
        return self.client.post(reverse('oraliq_nazorat:login'), {'email': email, 'password': password})

    def test_student_signs_in_and_lands_on_the_exam(self):
        response = self.login('Student1@Mail.uz', PASSWORD)
        self.assertRedirects(response, reverse('oraliq_nazorat:exam'))
        self.assertTrue(LoginAttempt.objects.filter(email='student1@mail.uz', success=True).exists())
        self.assertTrue(Event.objects.filter(kind='login', user=self.student).exists())

    def test_wrong_password_is_refused_and_logged(self):
        response = self.login('student1@mail.uz', '000000')
        self.assertContains(response, 'Email yoki parol notoʻgʻri')
        self.assertFalse(response.wsgi_request.user.is_authenticated)
        self.assertTrue(Event.objects.filter(kind='login_failed', user=self.student).exists())

    def test_too_many_failures_lock_the_email(self):
        for _ in range(10):
            self.login('student1@mail.uz', '000000')
        response = self.login('student1@mail.uz', PASSWORD)
        self.assertContains(response, 'Juda koʻp notoʻgʻri urinish')
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_non_participants_cannot_sign_in(self):
        response = self.login('boshqa@mail.uz', PASSWORD)
        self.assertContains(response, 'ishtirokchilari roʻyxatida yoʻqsiz')
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_teacher_goes_to_the_dashboard(self):
        self.assertRedirects(self.login('ustoz@mail.uz', 'Ustoz-2026!'), reverse('oraliq_nazorat:dashboard'))


@FAST_HASHER
class ExamFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.exam, (cls.student, cls.other) = make_exam()

    def setUp(self):
        self.client.force_login(self.student)

    def attempt(self):
        return Attempt.objects.get(user=self.student)

    def start(self):
        response = post_json(self.client, 'api_start', {'accept': True})
        self.assertEqual(response.status_code, 200, response.content)
        return response

    def test_lobby_shows_rules_and_does_not_contain_questions(self):
        response = self.client.get(reverse('oraliq_nazorat:exam'))
        self.assertContains(response, 'Testni boshlash')
        self.assertContains(response, 'Imtihon qoidalari')
        self.assertNotContains(response, 'Savol 0?')
        self.assertTrue(Event.objects.filter(kind='lobby', user=self.student).exists())

    def test_start_needs_the_rules_accepted(self):
        response = post_json(self.client, 'api_start', {})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.attempt().status, Attempt.ASSIGNED)

    def test_closed_exam_cannot_be_started(self):
        Exam.objects.filter(pk=self.exam.pk).update(is_open=False)
        response = post_json(self.client, 'api_start', {'accept': True})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['error'], 'closed')
        self.assertEqual(self.attempt().status, Attempt.ASSIGNED)
        self.assertTrue(Event.objects.filter(kind='closed_start').exists())

    def test_start_sends_questions_without_answers_and_binds_the_browser(self):
        response = self.start()
        data = response.json()
        self.assertEqual(len(data['questions']), 15)
        self.assertEqual(data['remaining'], 20 * 60)
        self.assertEqual(sorted(data['questions'][0]['options']), [f'Javob 0.{i}' for i in range(4)])
        self.assertNotIn('correct', response.content.decode())
        self.assertIn(services.DEVICE_COOKIE, response.cookies)
        attempt = self.attempt()
        self.assertEqual(attempt.status, Attempt.RUNNING)
        self.assertEqual(len(attempt.question_order), 15)
        self.assertTrue(attempt.device_hash)

    def test_answers_are_saved_changed_and_logged(self):
        self.start()
        self.assertTrue(post_json(self.client, 'api_answer', {'q': 0, 'o': 1}).json()['ok'])
        self.assertTrue(post_json(self.client, 'api_answer', {'q': 0, 'o': 3}).json()['ok'])
        answer = Answer.objects.get(attempt=self.attempt())
        attempt = self.attempt()
        self.assertEqual(answer.choice_id, attempt.choice_order[str(answer.question_id)][3])
        self.assertEqual(answer.changes, 1)
        self.assertTrue(Event.objects.filter(kind='answer_change').exists())
        self.assertEqual(post_json(self.client, 'api_answer', {'q': 15, 'o': 0}).status_code, 403)
        self.assertEqual(post_json(self.client, 'api_answer', {'q': 0, 'o': 4}).status_code, 403)

    def correct_index(self, attempt, q_index):
        qid = attempt.question_order[q_index]
        correct = Choice.objects.get(question_id=qid, is_correct=True).pk
        return attempt.choice_order[str(qid)].index(correct)

    def test_finish_grades_the_answers(self):
        self.start()
        attempt = self.attempt()
        for q in range(5):
            post_json(self.client, 'api_answer', {'q': q, 'o': self.correct_index(attempt, q)})
        wrong = (self.correct_index(attempt, 5) + 1) % 4
        post_json(self.client, 'api_answer', {'q': 5, 'o': wrong})
        # The final snapshot may carry an answer that never reached the server.
        snapshot = {'6': self.correct_index(attempt, 6)}
        response = post_json(self.client, 'api_finish', {'answers': snapshot})
        self.assertEqual(response.json()['redirect'], reverse('oraliq_nazorat:result'))
        attempt = self.attempt()
        self.assertEqual(attempt.status, Attempt.FINISHED)
        self.assertEqual(attempt.finish_reason, Attempt.REASON_SUBMITTED)
        self.assertEqual(attempt.correct_count, 6)
        self.assertEqual(attempt.score, 40.0)
        result = self.client.get(reverse('oraliq_nazorat:result'))
        self.assertContains(result, 'Imtihon yakunlandi')
        self.assertEqual(post_json(self.client, 'api_answer', {'q': 7, 'o': 0}).status_code, 409)

    def test_third_leave_finishes_the_test_with_the_current_answers(self):
        self.start()
        attempt = self.attempt()
        post_json(self.client, 'api_answer', {'q': 0, 'o': self.correct_index(attempt, 0)})

        def leave(event_id, answers=None):
            return post_json(self.client, 'api_event', {
                'events': [{'kind': 'leave', 'data': {'reason': 'hidden'}, 'id': event_id}],
                'answers': answers or {},
            }).json()

        self.assertEqual(leave('a1')['leave_count'], 1)
        self.assertEqual(leave('a1')['leave_count'], 1)            # same event retried: not counted twice
        self.assertEqual(leave('a2')['leave_count'], 2)
        data = leave('a3', {'1': self.correct_index(attempt, 1)})
        self.assertTrue(data['finished'])
        attempt = self.attempt()
        self.assertEqual(attempt.status, Attempt.FINISHED)
        self.assertEqual(attempt.finish_reason, Attempt.REASON_VIOLATIONS)
        self.assertEqual(attempt.correct_count, 2)                  # the snapshot answer was saved first
        self.assertEqual(Event.objects.filter(attempt=attempt, kind='leave').count(), 3)

    def test_fullscreen_exit_is_logged_but_only_counted_when_configured(self):
        self.start()
        post_json(self.client, 'api_event', {'events': [
            {'kind': 'fullscreen_exit', 'data': {}},
            {'kind': 'leave', 'data': {'reason': 'fullscreen'}, 'id': 'f1'},
        ]})
        attempt = self.attempt()
        self.assertEqual((attempt.leave_count, attempt.fullscreen_exits), (0, 1))
        Exam.objects.filter(pk=self.exam.pk).update(count_fullscreen_exit=True)
        post_json(self.client, 'api_event', {'events': [{'kind': 'leave', 'data': {'reason': 'fullscreen'}, 'id': 'f2'}]})
        self.assertEqual(self.attempt().leave_count, 1)

    def test_unknown_events_are_ignored_and_messages_are_built_on_the_server(self):
        self.start()
        post_json(self.client, 'api_event', {'events': [
            {'kind': 'hack', 'data': {}},
            {'kind': 'key', 'data': {'combo': 'F12', 'x' * 50: 'y' * 500}},
        ]})
        self.assertFalse(Event.objects.filter(kind='hack').exists())
        event = Event.objects.get(kind='key')
        self.assertEqual(event.message, 'Taqiqlangan tugma bosildi: F12')
        self.assertEqual(event.level, Event.WARNING)

    def test_hostile_payloads_are_rejected_without_errors(self):
        self.start()
        raw = '{"events": [{"kind": "mouse_out", "data": {"seconds": NaN}}], "answers": {"1": Infinity, "x": 2}}'
        response = self.client.post(reverse('oraliq_nazorat:api_event'), raw, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Answer.objects.filter(attempt=self.attempt()).count(), 0)
        self.assertEqual(Event.objects.get(kind='mouse_out').data, {})
        for payload in ('not json', '[]', '{"q": true, "o": 0}', '{"q": "1", "o": 0}'):
            response = self.client.post(reverse('oraliq_nazorat:api_answer'), payload, content_type='application/json')
            self.assertIn(response.status_code, (400, 403))

    def test_beacon_form_payload_is_accepted(self):
        self.start()
        payload = json.dumps({'events': [{'kind': 'unload', 'data': {}}], 'answers': {'2': 1}})
        response = self.client.post(reverse('oraliq_nazorat:api_event'), {'payload': payload})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Event.objects.filter(kind='unload').exists())
        self.assertEqual(Answer.objects.filter(attempt=self.attempt()).count(), 1)

    def test_deadline_is_enforced_on_the_server(self):
        self.start()
        post_json(self.client, 'api_answer', {'q': 0, 'o': 0})
        Attempt.objects.filter(pk=self.attempt().pk).update(started_at=timezone.now() - timedelta(minutes=21))
        response = post_json(self.client, 'api_answer', {'q': 1, 'o': 0})
        self.assertEqual(response.status_code, 409)
        attempt = self.attempt()
        self.assertEqual(attempt.status, Attempt.FINISHED)
        self.assertEqual(attempt.finish_reason, Attempt.REASON_TIME_UP)
        self.assertEqual(Answer.objects.filter(attempt=attempt).count(), 1)
        self.assertEqual(attempt.finished_at, attempt.deadline)

    def test_another_browser_cannot_continue(self):
        self.start()
        other = self.client_class()
        other.force_login(self.student)          # same account, no device cookie
        response = post_json(other, 'api_resume')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['error'], 'device')
        self.assertTrue(Event.objects.filter(kind='device_mismatch').exists())
        page = other.get(reverse('oraliq_nazorat:exam'))
        self.assertEqual(page.context['state'], 'device')

    def test_quick_reload_is_logged_long_absence_counts_as_a_leave(self):
        self.start()
        page = self.client.get(reverse('oraliq_nazorat:exam'))
        self.assertEqual(page.context['state'], 'resume')
        self.assertTrue(Event.objects.filter(kind='reload').exists())
        self.assertEqual(self.attempt().leave_count, 0)

        Attempt.objects.filter(pk=self.attempt().pk).update(last_seen_at=timezone.now() - timedelta(seconds=90))
        self.client.get(reverse('oraliq_nazorat:exam'))
        self.assertEqual(self.attempt().leave_count, 1)
        data = post_json(self.client, 'api_resume').json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['leave_count'], 1)

    def test_students_cannot_open_the_dashboard(self):
        response = self.client.get(reverse('oraliq_nazorat:dashboard'))
        self.assertRedirects(response, reverse('oraliq_nazorat:login'), fetch_redirect_response=False)
        self.assertEqual(self.client.get(reverse('oraliq_nazorat:dashboard_data')).status_code, 302)


@FAST_HASHER
class ProctorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.exam, (cls.student, cls.other) = make_exam(variants=3)
        cls.teacher = User.objects.create_user('ustoz@mail.uz', 'ustoz@mail.uz', 'x')
        UserProfile.objects.create(user=cls.teacher, role='teacher')

    def setUp(self):
        self.student_client = self.client_class()
        self.student_client.force_login(self.student)
        post_json(self.student_client, 'api_start', {'accept': True})
        self.client.force_login(self.teacher)

    def attempt(self):
        return Attempt.objects.get(user=self.student)

    def act(self, action, **extra):
        return self.client.post(reverse('oraliq_nazorat:attempt_action', args=[self.attempt().pk]),
                                {'action': action, **extra})

    def test_dashboard_and_live_data(self):
        self.assertContains(self.client.get(reverse('oraliq_nazorat:dashboard')), 'Nazorat paneli')
        data = self.client.get(reverse('oraliq_nazorat:dashboard_data') + f'?exam={self.exam.pk}').json()
        self.assertEqual(data['stats']['running'], 1)
        self.assertEqual(data['stats']['assigned'], 1)
        self.assertEqual([r['email'] for r in data['rows']], ['student1@mail.uz', 'student2@mail.uz'])

    def test_dashboard_closes_attempts_whose_time_is_over(self):
        Attempt.objects.filter(pk=self.attempt().pk).update(started_at=timezone.now() - timedelta(hours=1))
        self.client.get(reverse('oraliq_nazorat:dashboard_data'))
        self.assertEqual(self.attempt().finish_reason, Attempt.REASON_TIME_UP)

    def test_detail_page_shows_answers_and_events(self):
        post_json(self.student_client, 'api_answer', {'q': 0, 'o': 2})
        response = self.client.get(reverse('oraliq_nazorat:attempt_detail', args=[self.attempt().pk]))
        self.assertContains(response, 'Hodisalar jurnali')
        self.assertContains(response, 'Imtihonni boshladi')
        self.assertContains(response, 'talaba javobi')

    def test_extra_time_forgive_unlock(self):
        self.act('extra', minutes='7')
        self.assertEqual(self.attempt().extra_minutes, 7)
        self.assertGreater(self.attempt().remaining_seconds(), 26 * 60)   # 20 + 7 minutes
        Attempt.objects.filter(pk=self.attempt().pk).update(leave_count=2)
        self.act('forgive')
        self.assertEqual(self.attempt().leave_count, 1)
        self.act('unlock')
        self.assertEqual(self.attempt().device_hash, '')
        other = self.client_class()
        other.force_login(self.student)
        response = post_json(other, 'api_resume')
        self.assertEqual(response.status_code, 200)
        self.assertIn(services.DEVICE_COOKIE, response.cookies)   # bound to the new browser
        self.assertTrue(Event.objects.filter(kind='teacher_unlock').exists())

    def test_finish_and_reopen(self):
        self.act('finish')
        attempt = self.attempt()
        self.assertEqual(attempt.finish_reason, Attempt.REASON_TEACHER)
        self.act('reopen')
        attempt = self.attempt()
        self.assertEqual(attempt.status, Attempt.RUNNING)
        self.assertGreaterEqual(attempt.remaining_seconds(), 60)

    def test_reset_gives_a_spare_variant(self):
        old_variant = self.attempt().variant_id
        post_json(self.student_client, 'api_answer', {'q': 0, 'o': 0})
        self.act('reset')
        attempt = self.attempt()
        self.assertEqual(attempt.status, Attempt.ASSIGNED)
        self.assertEqual(Answer.objects.filter(attempt=attempt).count(), 0)
        used = set(Attempt.objects.exclude(pk=attempt.pk).values_list('variant_id', flat=True))
        self.assertNotEqual(attempt.variant_id, old_variant)
        self.assertNotIn(attempt.variant_id, used)
        self.assertTrue(Event.objects.filter(kind='teacher_reset').exists())  # history is kept

    def test_toggle_exam_and_export_csv(self):
        self.client.post(reverse('oraliq_nazorat:exam_toggle', args=[self.exam.pk]), {'open': '0'})
        self.exam.refresh_from_db()
        self.assertFalse(self.exam.is_open)
        response = self.client.get(reverse('oraliq_nazorat:export_csv') + f'?exam={self.exam.pk}')
        self.assertEqual(response['Content-Type'], 'text/csv; charset=utf-8')
        content = response.content.decode('utf-8-sig')
        self.assertIn('student1@mail.uz', content)
        self.assertIn('Oynadan chiqish', content)
