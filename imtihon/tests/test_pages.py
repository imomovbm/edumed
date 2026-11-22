"""Teacher pages render in every state; exports are safe; the old exam's pages are gone."""
import csv
import io

from django.test import TestCase
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from user.models import StudentGroup

from .. import services
from ..models import Attempt, Exam
from .helpers import FAST_HASHER, api, make_exam, make_student, make_teacher


@FAST_HASHER
class TeacherPagesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.teacher = make_teacher()
        cls.group = StudentGroup.objects.create(name='101-guruh')
        cls.student = make_student('ali01', cls.group, name='=HYPERLINK("http://x")')

    def setUp(self):
        self.client.force_login(self.teacher)

    def test_every_page_renders_for_each_exam_state(self):
        for status in (Exam.DRAFT, Exam.PUBLISHED, Exam.FINISHED):
            exam = make_exam(groups=[self.group], status=status, title=f'Imtihon {status}')
            attempt = Attempt.objects.create(exam=exam, user=self.student, status=Attempt.FINISHED,
                                             started_at=timezone.now(), finished_at=timezone.now(),
                                             finish_reason=Attempt.REASON_SUBMITTED, correct_count=0, score=0.0)
            urls = [
                reverse('imtihon:manage'), reverse('imtihon:manage_import'),
                reverse('imtihon:manage_exam', args=[exam.pk]), reverse('imtihon:manage_exam_delete', args=[exam.pk]),
                reverse('imtihon:manage_dashboard', args=[exam.pk]), reverse('imtihon:manage_attempt', args=[attempt.pk]),
                reverse('imtihon:manage_students'), reverse('imtihon:manage_student', args=[self.student.pk]),
                reverse('imtihon:manage_student_delete', args=[self.student.pk]),
                reverse('imtihon:manage_groups'), reverse('imtihon:manage_group', args=[self.group.pk]),
                reverse('imtihon:manage_group_delete', args=[self.group.pk]),
            ]
            for url in urls:
                with self.subTest(status=status, url=url):
                    self.assertEqual(self.client.get(url).status_code, 200)

    def test_draft_page_explains_what_is_missing(self):
        exam = make_exam(status=Exam.DRAFT)
        page = self.client.get(reverse('imtihon:manage_exam', args=[exam.pk]))
        self.assertContains(page, 'Imtihon hech kimga biriktirilmagan')
        self.assertContains(page, 'Eʼlon qilish</button>')
        exam.groups.add(self.group)
        page = self.client.get(reverse('imtihon:manage_exam', args=[exam.pk]))
        self.assertContains(page, 'Imtihon tayyor')

    def test_settings_are_validated(self):
        exam = make_exam(status=Exam.DRAFT, count=3)
        response = self.client.post(reverse('imtihon:manage_exam', args=[exam.pk]), {
            'title': '', 'duration_minutes': '0', 'question_count': '5', 'max_leaves': '3',
            'starts_at': '2030-01-02T10:00', 'ends_at': '2030-01-02T09:00',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Imtihon nomini kiriting')
        self.assertContains(response, 'Imtihonda faqat 3 ta savol bor')
        self.assertContains(response, 'Tugash vaqti boshlanish vaqtidan keyin')
        exam.refresh_from_db()
        self.assertEqual(exam.title, 'Test imtihon')

    def test_question_selection_is_locked_after_students_started(self):
        exam = make_exam(groups=[self.group], count=6)
        client = self.client_class()
        client.force_login(self.student)
        api(client, exam, 'start', {'accept': True})
        self.client.post(reverse('imtihon:manage_exam', args=[exam.pk]), {
            'title': 'Yangi nom', 'duration_minutes': '30', 'question_count': '2', 'max_leaves': '3',
            'groups': [self.group.pk],
        })
        exam.refresh_from_db()
        self.assertEqual((exam.title, exam.duration_minutes, exam.question_count, exam.shuffle_questions),
                         ('Yangi nom', 30, None, True))

    def test_correct_answer_first_warning_when_options_are_not_shuffled(self):
        exam = make_exam(status=Exam.DRAFT, count=3, shuffle_options=False)
        page = self.client.get(reverse('imtihon:manage_exam', args=[exam.pk]))
        self.assertContains(page, '3 ta savolda toʻgʻri javob birinchi oʻrinda')

    def test_delete_exam_after_confirmation(self):
        exam = make_exam(groups=[self.group])
        Attempt.objects.create(exam=exam, user=self.student, status=Attempt.FINISHED)
        page = self.client.get(reverse('imtihon:manage_exam_delete', args=[exam.pk]))
        self.assertContains(page, '1 ta talabaning natijasi ham oʻchadi')
        self.assertContains(page, reverse('imtihon:manage_export', args=[exam.pk, 'xlsx']))
        self.client.post(reverse('imtihon:manage_exam_delete', args=[exam.pk]))
        self.assertFalse(Exam.objects.exists())
        self.assertFalse(Attempt.objects.exists())

    def test_exports_do_not_let_spreadsheets_run_formulas(self):
        exam = make_exam(groups=[self.group])
        response = self.client.get(reverse('imtihon:manage_export', args=[exam.pk, 'csv']))
        row = list(csv.reader(io.StringIO(response.content.decode('utf-8-sig'))))[1]
        self.assertEqual(row[2], '\'=HYPERLINK("http://x")')
        self.assertEqual(row[4], 'Boshlanmagan')

    def test_unknown_export_format_and_missing_exam(self):
        exam = make_exam()
        self.assertEqual(self.client.get(f'/imtihon/boshqaruv/{exam.pk}/natijalar.pdf').status_code, 404)
        self.assertEqual(self.client.get(reverse('imtihon:manage_exam', args=[9999])).status_code, 404)

    def test_teacher_landing_and_login_redirects(self):
        self.assertRedirects(self.client.get(reverse('imtihon:login')), reverse('imtihon:manage'),
                             fetch_redirect_response=False)
        self.assertRedirects(self.client.get(reverse('imtihon:my_exams')), reverse('imtihon:manage'),
                             fetch_redirect_response=False)

    def test_main_site_menu_links_to_the_exams(self):
        from django.template.loader import render_to_string
        html = render_to_string('courses/sidebar.html', {'can_grade': True, 'user': self.teacher})
        self.assertIn(reverse('imtihon:manage'), html)
        self.assertNotIn('oraliq', html.lower())


@FAST_HASHER
class LoginPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.group = StudentGroup.objects.create(name='G')
        cls.student = make_student('ali01', cls.group)

    def login(self, login, password):
        return self.client.post(reverse('imtihon:login'), {'login': login, 'password': password})

    def test_student_signs_in_with_login_and_password(self):
        self.assertRedirects(self.login(' Ali01 ', '482916'), reverse('imtihon:my_exams'),
                             fetch_redirect_response=False)

    def test_wrong_password_is_refused_and_logged_without_the_password(self):
        response = self.login('ali01', 'notogri-777')
        self.assertContains(response, 'Login yoki parol notoʻgʻri')
        self.assertFalse(response.wsgi_request.user.is_authenticated)
        from ..models import Event, LoginAttempt
        self.assertTrue(Event.objects.filter(kind='login_failed', user=self.student).exists())
        self.assertFalse(Event.objects.filter(message__contains='notogri-777').exists())
        self.assertFalse(LoginAttempt.objects.filter(login__contains='notogri-777').exists())

    def test_too_many_failures_lock_the_login(self):
        for _ in range(10):
            self.login('ali01', '000000')
        response = self.login('ali01', '482916')
        self.assertContains(response, 'Juda koʻp notoʻgʻri urinish')
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_login_page_is_generic(self):
        page = self.client.get(reverse('imtihon:login'))
        self.assertContains(page, 'Imtihon tizimi')
        self.assertNotContains(page, 'oraliq', status_code=200)
        self.assertNotContains(page, 'Oraliq')


class OldExamRemovedTests(TestCase):
    def test_old_pages_are_gone(self):
        self.assertEqual(self.client.get('/oraliq-nazorat/').status_code, 404)
        with self.assertRaises(NoReverseMatch):
            reverse('oraliq_nazorat:login')

    def test_services_module_has_no_exam_specific_constants(self):
        self.assertFalse(hasattr(services, 'EXAM_CODE'))
