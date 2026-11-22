"""Exam rules on the server: who may start, the clock, answers, leaving the window, proctors."""
import json
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from user.models import StudentGroup

from .. import services
from ..models import Answer, Attempt, Event, Exam
from .helpers import FAST_HASHER, api, correct_position, make_exam, make_student, make_teacher


@FAST_HASHER
class ExamFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.group = StudentGroup.objects.create(name='101-guruh')
        cls.student = make_student('ali01', cls.group)
        cls.other = make_student('vali02', cls.group)
        cls.exam = make_exam(groups=[cls.group], count=10, duration_minutes=20)

    def setUp(self):
        self.client.force_login(self.student)

    def attempt(self):
        return Attempt.objects.get(user=self.student, exam=self.exam)

    def start(self, client=None):
        response = api(client or self.client, self.exam, 'start', {'accept': True})
        self.assertEqual(response.status_code, 200, response.content)
        return response

    def page(self, client=None):
        return (client or self.client).get(reverse('imtihon:exam', args=[self.exam.pk]))

    def test_lobby_shows_rules_and_no_questions(self):
        response = self.page()
        self.assertEqual(response.context['state'], 'lobby')
        self.assertContains(response, 'Testni boshlash')
        self.assertContains(response, 'Imtihon qoidalari')
        self.assertNotContains(response, 'Savol 1?')
        self.assertTrue(Event.objects.filter(kind='lobby', user=self.student, exam=self.exam).exists())

    def test_start_needs_the_rules_accepted(self):
        self.assertEqual(api(self.client, self.exam, 'start', {}).status_code, 400)
        self.assertFalse(Attempt.objects.exists())

    def test_start_sends_questions_without_answers_and_binds_the_browser(self):
        response = self.start()
        data = response.json()
        self.assertEqual(len(data['questions']), 10)
        self.assertEqual(data['remaining'], 20 * 60)
        self.assertEqual(sorted(data['questions'][0]['options'])[0][:6], 'Javob ')
        self.assertEqual(set(data['questions'][0]), {'text', 'options'})
        self.assertNotIn('correct', response.content.decode())
        self.assertIn(services.DEVICE_COOKIE, response.cookies)
        attempt = self.attempt()
        self.assertEqual((attempt.status, attempt.question_count), (Attempt.RUNNING, 10))
        self.assertTrue(attempt.device_hash)
        self.assertEqual(self.start().json()['questions'], data['questions'])   # double click: same test

    def test_random_subset_per_student(self):
        Exam.objects.filter(pk=self.exam.pk).update(question_count=4)
        self.start()
        attempt = self.attempt()
        self.assertEqual(len(attempt.question_order), 4)
        self.assertEqual(len(set(attempt.question_order)), 4)
        self.assertTrue(set(attempt.question_order) <= set(self.exam.questions.values_list('pk', flat=True)))

    def test_no_shuffling_keeps_the_file_order(self):
        Exam.objects.filter(pk=self.exam.pk).update(shuffle_questions=False, shuffle_options=False, question_count=5)
        data = self.start().json()
        numbers = [int(q['text'].split()[1].rstrip('?')) for q in data['questions']]
        self.assertEqual(numbers, sorted(numbers))
        for q, n in zip(data['questions'], numbers):
            self.assertEqual(q['options'], [f'Javob {n}.{i}' for i in range(4)])

    def test_answers_are_saved_changed_and_logged(self):
        self.start()
        self.assertTrue(api(self.client, self.exam, 'answer', {'q': 0, 'o': 1}).json()['ok'])
        self.assertTrue(api(self.client, self.exam, 'answer', {'q': 0, 'o': 3}).json()['ok'])
        attempt = self.attempt()
        answer = Answer.objects.get(attempt=attempt)
        self.assertEqual(answer.choice_id, attempt.choice_order[str(answer.question_id)][3])
        self.assertEqual(answer.changes, 1)
        self.assertTrue(Event.objects.filter(kind='answer_change', attempt=attempt).exists())
        self.assertEqual(api(self.client, self.exam, 'answer', {'q': 10, 'o': 0}).status_code, 403)
        self.assertEqual(api(self.client, self.exam, 'answer', {'q': 0, 'o': 4}).status_code, 403)

    def test_finish_grades_the_answers(self):
        self.start()
        attempt = self.attempt()
        for q in range(5):
            api(self.client, self.exam, 'answer', {'q': q, 'o': correct_position(attempt, q)})
        api(self.client, self.exam, 'answer', {'q': 5, 'o': (correct_position(attempt, 5) + 1) % 4})
        # The final snapshot may carry an answer that never reached the server.
        response = api(self.client, self.exam, 'finish', {'answers': {'6': correct_position(attempt, 6)}})
        self.assertEqual(response.json()['redirect'], reverse('imtihon:result', args=[self.exam.pk]))
        attempt = self.attempt()
        self.assertEqual((attempt.status, attempt.finish_reason), (Attempt.FINISHED, Attempt.REASON_SUBMITTED))
        self.assertEqual((attempt.correct_count, attempt.score), (6, 60.0))
        result = self.client.get(reverse('imtihon:result', args=[self.exam.pk]))
        self.assertContains(result, 'Imtihon yakunlandi')
        self.assertContains(result, '60,0%')                      # Uzbek number format
        self.assertEqual(api(self.client, self.exam, 'answer', {'q': 7, 'o': 0}).status_code, 409)
        self.assertRedirects(self.page(), reverse('imtihon:result', args=[self.exam.pk]))

    def test_score_can_be_hidden_from_students(self):
        Exam.objects.filter(pk=self.exam.pk).update(show_score=False)
        self.start()
        api(self.client, self.exam, 'finish')
        result = self.client.get(reverse('imtihon:result', args=[self.exam.pk]))
        self.assertContains(result, 'Natijani oʻqituvchi eʼlon qiladi')
        self.assertNotContains(result, 'class="score"')

    def test_third_leave_finishes_the_test_with_the_current_answers(self):
        self.start()
        attempt = self.attempt()
        api(self.client, self.exam, 'answer', {'q': 0, 'o': correct_position(attempt, 0)})

        def leave(event_id, answers=None):
            return api(self.client, self.exam, 'event', {
                'events': [{'kind': 'leave', 'data': {'reason': 'hidden'}, 'id': event_id}],
                'answers': answers or {},
            }).json()

        self.assertEqual(leave('a1')['leave_count'], 1)
        self.assertEqual(leave('a1')['leave_count'], 1)            # the same event retried: counted once
        self.assertEqual(leave('a2')['leave_count'], 2)
        data = leave('a3', {'1': correct_position(attempt, 1)})
        self.assertTrue(data['finished'])
        attempt = self.attempt()
        self.assertEqual((attempt.status, attempt.finish_reason), (Attempt.FINISHED, Attempt.REASON_VIOLATIONS))
        self.assertEqual(attempt.correct_count, 2)                  # the snapshot answer was saved first
        self.assertEqual(Event.objects.filter(attempt=attempt, kind='leave').count(), 3)

    def test_leave_limit_is_configurable(self):
        Exam.objects.filter(pk=self.exam.pk).update(max_leaves=1)
        self.start()
        data = api(self.client, self.exam, 'event', {'events': [{'kind': 'leave', 'data': {'reason': 'blur'}, 'id': 'x'}]}).json()
        self.assertTrue(data['finished'])

    def test_fullscreen_exit_is_logged_but_only_counted_when_configured(self):
        self.start()
        api(self.client, self.exam, 'event', {'events': [
            {'kind': 'fullscreen_exit', 'data': {}},
            {'kind': 'leave', 'data': {'reason': 'fullscreen'}, 'id': 'f1'},
        ]})
        attempt = self.attempt()
        self.assertEqual((attempt.leave_count, attempt.fullscreen_exits), (0, 1))
        Exam.objects.filter(pk=self.exam.pk).update(count_fullscreen_exit=True)
        api(self.client, self.exam, 'event', {'events': [{'kind': 'leave', 'data': {'reason': 'fullscreen'}, 'id': 'f2'}]})
        self.assertEqual(self.attempt().leave_count, 1)

    def test_unknown_events_are_ignored_and_messages_are_built_on_the_server(self):
        self.start()
        api(self.client, self.exam, 'event', {'events': [
            {'kind': 'hack', 'data': {}},
            {'kind': 'key', 'data': {'combo': 'F12', 'x' * 50: 'y' * 500}},
        ]})
        self.assertFalse(Event.objects.filter(kind='hack').exists())
        event = Event.objects.get(kind='key')
        self.assertEqual((event.message, event.level), ('Taqiqlangan tugma bosildi: F12', Event.WARNING))

    def test_hostile_payloads_are_rejected_without_errors(self):
        self.start()
        url = reverse('imtihon:api_event', args=[self.exam.pk])
        raw = '{"events": [{"kind": "mouse_out", "data": {"seconds": NaN}}], "answers": {"1": Infinity, "x": 2}}'
        self.assertEqual(self.client.post(url, raw, content_type='application/json').status_code, 200)
        self.assertEqual(Answer.objects.filter(attempt=self.attempt()).count(), 0)
        self.assertEqual(Event.objects.get(kind='mouse_out').data, {})
        answer_url = reverse('imtihon:api_answer', args=[self.exam.pk])
        for payload in ('not json', '[]', '{"q": true, "o": 0}', '{"q": "1", "o": 0}', '{"q": 1e400, "o": 0}'):
            response = self.client.post(answer_url, payload, content_type='application/json')
            self.assertIn(response.status_code, (400, 403), payload)

    def test_beacon_form_payload_is_accepted(self):
        self.start()
        payload = json.dumps({'events': [{'kind': 'unload', 'data': {}}], 'answers': {'2': 1}})
        response = self.client.post(reverse('imtihon:api_event', args=[self.exam.pk]), {'payload': payload})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Event.objects.filter(kind='unload').exists())
        self.assertEqual(Answer.objects.filter(attempt=self.attempt()).count(), 1)

    def test_deadline_is_enforced_on_the_server(self):
        self.start()
        api(self.client, self.exam, 'answer', {'q': 0, 'o': 0})
        Attempt.objects.filter(pk=self.attempt().pk).update(started_at=timezone.now() - timedelta(minutes=21))
        self.assertEqual(api(self.client, self.exam, 'answer', {'q': 1, 'o': 0}).status_code, 409)
        attempt = self.attempt()
        self.assertEqual((attempt.status, attempt.finish_reason), (Attempt.FINISHED, Attempt.REASON_TIME_UP))
        self.assertEqual(Answer.objects.filter(attempt=attempt).count(), 1)
        self.assertEqual(attempt.finished_at, attempt.deadline)

    def test_window_end_cuts_the_running_test(self):
        ends = timezone.now() + timedelta(minutes=5)
        Exam.objects.filter(pk=self.exam.pk).update(ends_at=ends)
        data = self.start().json()
        self.assertLessEqual(data['remaining'], 5 * 60)
        attempt = self.attempt()
        self.assertEqual(attempt.deadline, ends)
        Exam.objects.filter(pk=self.exam.pk).update(ends_at=timezone.now() - timedelta(minutes=1))
        self.assertEqual(api(self.client, self.exam, 'answer', {'q': 0, 'o': 0}).status_code, 409)
        self.assertEqual(self.attempt().finish_reason, Attempt.REASON_TIME_UP)

    def test_upcoming_exam_waits_and_cannot_be_started(self):
        Exam.objects.filter(pk=self.exam.pk).update(starts_at=timezone.now() + timedelta(hours=1))
        page = self.page()
        self.assertEqual(page.context['state'], 'upcoming')
        self.assertGreater(page.context['config']['startsIn'], 3500)
        self.assertContains(page, 'da boshlanadi')
        response = api(self.client, self.exam, 'start', {'accept': True})
        self.assertEqual((response.status_code, response.json()['error']), (403, 'upcoming'))
        self.assertTrue(Event.objects.filter(kind='closed_start', user=self.student).exists())
        status = self.client.get(reverse('imtihon:api_status', args=[self.exam.pk])).json()
        self.assertEqual((status['open'], status['window']), (False, 'upcoming'))

    def test_closed_window_and_finished_exam(self):
        Exam.objects.filter(pk=self.exam.pk).update(ends_at=timezone.now() - timedelta(minutes=1))
        self.assertEqual(self.page().context['state'], 'closed')
        self.assertEqual(api(self.client, self.exam, 'start', {'accept': True}).json()['error'], 'closed')
        Exam.objects.filter(pk=self.exam.pk).update(ends_at=None, status=Exam.FINISHED)
        self.assertContains(self.page(), 'Bu imtihon yopilgan')
        self.assertEqual(api(self.client, self.exam, 'start', {'accept': True}).status_code, 403)
        self.assertFalse(Attempt.objects.exists())

    def test_another_browser_cannot_continue(self):
        self.start()
        other = self.client_class()
        other.force_login(self.student)          # same account, no device cookie
        response = api(other, self.exam, 'resume')
        self.assertEqual((response.status_code, response.json()['error']), (403, 'device'))
        self.assertTrue(Event.objects.filter(kind='device_mismatch').exists())
        self.assertEqual(self.page(other).context['state'], 'device')

    def test_quick_reload_is_logged_long_absence_counts_as_a_leave(self):
        self.start()
        self.assertEqual(self.page().context['state'], 'resume')
        self.assertTrue(Event.objects.filter(kind='reload').exists())
        self.assertEqual(self.attempt().leave_count, 0)
        Attempt.objects.filter(pk=self.attempt().pk).update(last_seen_at=timezone.now() - timedelta(seconds=90))
        self.page()
        self.assertEqual(self.attempt().leave_count, 1)
        data = api(self.client, self.exam, 'resume').json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['leave_count'], 1)


@FAST_HASHER
class VisibilityTests(TestCase):
    """Students only see (and can only start) exams assigned to them."""

    @classmethod
    def setUpTestData(cls):
        cls.group_a = StudentGroup.objects.create(name='A')
        cls.group_b = StudentGroup.objects.create(name='B')
        cls.alice = make_student('alice', cls.group_a)
        cls.bob = make_student('bob', cls.group_b)
        cls.exam = make_exam(groups=[cls.group_a], title='A guruh imtihoni')

    def test_assigned_group_sees_the_exam(self):
        self.client.force_login(self.alice)
        page = self.client.get(reverse('imtihon:my_exams'))
        self.assertContains(page, 'A guruh imtihoni')
        self.assertContains(page, 'Imtihonga kirish')

    def test_other_group_does_not_see_or_start_it(self):
        self.client.force_login(self.bob)
        self.assertNotContains(self.client.get(reverse('imtihon:my_exams')), 'A guruh imtihoni')
        self.assertEqual(self.client.get(reverse('imtihon:exam', args=[self.exam.pk])).status_code, 404)
        self.assertEqual(api(self.client, self.exam, 'start', {'accept': True}).status_code, 404)
        self.assertEqual(self.client.get(reverse('imtihon:result', args=[self.exam.pk])).status_code, 404)
        self.assertFalse(Attempt.objects.exists())

    def test_individual_assignment(self):
        self.exam.students.add(self.bob)
        self.client.force_login(self.bob)
        self.assertContains(self.client.get(reverse('imtihon:my_exams')), 'A guruh imtihoni')
        self.assertEqual(api(self.client, self.exam, 'start', {'accept': True}).status_code, 200)

    def test_drafts_are_hidden(self):
        Exam.objects.filter(pk=self.exam.pk).update(status=Exam.DRAFT)
        self.client.force_login(self.alice)
        self.assertNotContains(self.client.get(reverse('imtihon:my_exams')), 'A guruh imtihoni')
        self.assertEqual(self.client.get(reverse('imtihon:exam', args=[self.exam.pk])).status_code, 404)

    def test_finished_exam_stays_in_the_history_of_who_took_it(self):
        self.client.force_login(self.alice)
        api(self.client, self.exam, 'start', {'accept': True})
        api(self.client, self.exam, 'finish')
        services.finish_exam(self.exam)
        self.alice.userprofile.group = self.group_b       # moved to another group later
        self.alice.userprofile.save()
        page = self.client.get(reverse('imtihon:my_exams'))
        self.assertContains(page, 'A guruh imtihoni')
        self.assertContains(page, 'Natija')

    def test_anonymous_users_go_to_the_login_page(self):
        self.client.logout()
        for url in (reverse('imtihon:my_exams'), reverse('imtihon:exam', args=[self.exam.pk])):
            self.assertRedirects(self.client.get(url), reverse('imtihon:login'), fetch_redirect_response=False)
        self.assertEqual(api(self.client, self.exam, 'start', {'accept': True}).status_code, 401)


@FAST_HASHER
class ProctorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.group = StudentGroup.objects.create(name='101-guruh')
        cls.student = make_student('ali01', cls.group)
        cls.other = make_student('vali02', cls.group)
        cls.exam = make_exam(groups=[cls.group], count=6, question_count=4)
        cls.teacher = make_teacher()

    def setUp(self):
        self.student_client = self.client_class()
        self.student_client.force_login(self.student)
        api(self.student_client, self.exam, 'start', {'accept': True})
        self.client.force_login(self.teacher)

    def attempt(self):
        return Attempt.objects.get(user=self.student)

    def act(self, action, **extra):
        return self.client.post(reverse('imtihon:manage_attempt_action', args=[self.attempt().pk]),
                                {'action': action, **extra})

    def test_dashboard_lists_every_assigned_student(self):
        page = self.client.get(reverse('imtihon:manage_dashboard', args=[self.exam.pk]))
        self.assertEqual(page.status_code, 200)
        data = self.client.get(reverse('imtihon:manage_dashboard_data', args=[self.exam.pk])).json()
        self.assertEqual((data['stats']['running'], data['stats']['assigned']), (1, 1))
        self.assertEqual([r['login'] for r in data['rows']], ['ali01', 'vali02'])
        self.assertEqual(data['rows'][0]['group'], '101-guruh')
        self.assertEqual(data['rows'][0]['total'], 4)

    def test_dashboard_closes_attempts_whose_time_is_over(self):
        Attempt.objects.filter(pk=self.attempt().pk).update(started_at=timezone.now() - timedelta(hours=1))
        self.client.get(reverse('imtihon:manage_dashboard_data', args=[self.exam.pk]))
        self.assertEqual(self.attempt().finish_reason, Attempt.REASON_TIME_UP)

    def test_detail_page_shows_answers_and_events(self):
        api(self.student_client, self.exam, 'answer', {'q': 0, 'o': 2})
        response = self.client.get(reverse('imtihon:manage_attempt', args=[self.attempt().pk]))
        self.assertContains(response, 'Hodisalar jurnali')
        self.assertContains(response, 'Imtihonni boshladi (4 ta savol)')
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
        response = api(other, self.exam, 'resume')
        self.assertEqual(response.status_code, 200)
        self.assertIn(services.DEVICE_COOKIE, response.cookies)          # bound to the new browser
        self.assertTrue(Event.objects.filter(kind='teacher_unlock').exists())

    def test_finish_and_reopen(self):
        self.act('finish')
        self.assertEqual(self.attempt().finish_reason, Attempt.REASON_TEACHER)
        self.act('reopen')
        attempt = self.attempt()
        self.assertEqual(attempt.status, Attempt.RUNNING)
        self.assertGreaterEqual(attempt.remaining_seconds(), 60)

    def test_reset_lets_the_student_start_again(self):
        api(self.student_client, self.exam, 'answer', {'q': 0, 'o': 0})
        self.act('reset')
        attempt = self.attempt()
        self.assertEqual((attempt.status, attempt.question_order), (Attempt.ASSIGNED, []))
        self.assertEqual(Answer.objects.filter(attempt=attempt).count(), 0)
        self.assertTrue(Event.objects.filter(kind='teacher_reset').exists())  # history is kept
        response = api(self.student_client, self.exam, 'start', {'accept': True})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['questions']), 4)

    def test_finishing_the_exam_closes_running_tests(self):
        api(self.student_client, self.exam, 'answer', {'q': 0, 'o': correct_position(self.attempt(), 0)})
        response = self.client.post(reverse('imtihon:manage_exam_status', args=[self.exam.pk]), {'action': 'finish'})
        self.assertEqual(response.status_code, 302)
        self.exam.refresh_from_db()
        attempt = self.attempt()
        self.assertEqual(self.exam.status, Exam.FINISHED)
        self.assertEqual((attempt.status, attempt.finish_reason, attempt.correct_count),
                         (Attempt.FINISHED, Attempt.REASON_CLOSED, 1))
        late = self.client_class()
        late.force_login(self.other)
        self.assertEqual(api(late, self.exam, 'start', {'accept': True}).status_code, 403)
        self.act('reopen')
        self.assertEqual(self.attempt().status, Attempt.FINISHED)       # refused while the exam is finished
        self.client.post(reverse('imtihon:manage_exam_status', args=[self.exam.pk]), {'action': 'reopen'})
        self.exam.refresh_from_db()
        self.assertEqual(self.exam.status, Exam.PUBLISHED)
        self.assertEqual(api(late, self.exam, 'start', {'accept': True}).status_code, 200)

    def test_unpublish_is_refused_once_students_started(self):
        self.client.post(reverse('imtihon:manage_exam_status', args=[self.exam.pk]), {'action': 'unpublish'})
        self.exam.refresh_from_db()
        self.assertEqual(self.exam.status, Exam.PUBLISHED)
