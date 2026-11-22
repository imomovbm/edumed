"""The teachers' student panel: quick add, edit, password reset, delete, groups."""
from django.contrib.auth.hashers import identify_hasher
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from user import students as service
from user.models import StudentGroup, UserProfile
from user.students import StudentError

from ..forms import NEW_GROUP
from ..models import Attempt, Event, LoginAttempt
from .helpers import FAST_HASHER, make_exam, make_student, make_teacher


class StudentServiceTests(TestCase):
    def test_create_student_stores_only_a_hash(self):
        user = service.create_student('  ali01 ', '123456', '  Aliyev   Ali  ', 'Hamshiralik 1-kurs')
        user.refresh_from_db()
        self.assertEqual(user.username, 'ali01')
        self.assertEqual(user.get_full_name(), 'Aliyev Ali')
        self.assertNotEqual(user.password, '123456')
        self.assertNotIn('123456', user.password)
        identify_hasher(user.password)                    # a real Django hash (project hashers)
        self.assertTrue(user.check_password('123456'))
        self.assertEqual(user.userprofile.role, 'student')
        self.assertEqual(user.userprofile.group.name, 'Hamshiralik 1-kurs')

    def test_existing_group_is_reused_by_name(self):
        group = StudentGroup.objects.create(name='101-guruh')
        user = service.create_student('vali', '654321', 'Vali', ' 101-GURUH ')
        self.assertEqual(user.userprofile.group, group)
        self.assertEqual(StudentGroup.objects.count(), 1)

    def test_duplicate_login_is_rejected_case_insensitively(self):
        service.create_student('Ali', '123456', 'Ali', 'G1')
        User.objects.create_user('other', email='bobur@mail.uz', password='x')
        for login in ('ali', 'ALI', 'bobur@mail.uz'):
            with self.subTest(login=login), self.assertRaises(StudentError) as caught:
                service.create_student(login, '123456', 'Ikkinchi', 'G1')
            self.assertIn('band', caught.exception.errors['login'])
        self.assertEqual(User.objects.filter(username__iexact='ali').count(), 1)

    def test_all_problems_are_reported_together(self):
        with self.assertRaises(StudentError) as caught:
            service.create_student('ali vali', '12345', '   ', '')
        self.assertEqual(set(caught.exception.errors), {'login', 'password', 'full_name', 'group'})
        self.assertIn('6 ta belgi', caught.exception.errors['password'])
        self.assertFalse(User.objects.exists())
        self.assertFalse(StudentGroup.objects.exists())

    def test_password_rules(self):
        self.assertEqual(service.clean_password('000000'), '000000')            # digits only are fine
        for bad in ('', '12345', ' 123456', '123456 ', 'x' * 129):
            with self.subTest(password=bad), self.assertRaises(StudentError):
                service.clean_password(bad)

    def test_update_and_password_reset(self):
        user = service.create_student('ali', '123456', 'Ali', 'G1')
        service.update_student(user, 'ali2', 'Ali  Valiyev', 'G2')
        user.refresh_from_db()
        self.assertEqual((user.username, user.first_name, user.userprofile.group.name), ('ali2', 'Ali Valiyev', 'G2'))
        service.set_student_password(user, '999999')
        user.refresh_from_db()
        self.assertTrue(user.check_password('999999'))
        self.assertFalse(user.check_password('123456'))

    def test_groups(self):
        group = service.create_group('  A-1  ')
        self.assertEqual(group.name, 'A-1')
        with self.assertRaises(StudentError):
            service.create_group('a-1')
        other = service.create_group('B-2')
        with self.assertRaises(StudentError):
            service.rename_group(other, 'A-1')
        service.rename_group(group, 'A-1 (yangi)')
        self.assertEqual(StudentGroup.objects.get(pk=group.pk).name, 'A-1 (yangi)')


@FAST_HASHER
class StudentPanelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.teacher = make_teacher()
        cls.group = StudentGroup.objects.create(name='101-guruh')

    def setUp(self):
        self.client.force_login(self.teacher)

    def add(self, **data):
        payload = {'login': 'ali01', 'password': 'Maxfiy-2468', 'full_name': 'Aliyev Ali', 'group': str(self.group.pk)}
        payload.update(data)
        return self.client.post(reverse('imtihon:manage_students'), payload)

    def test_page_has_quick_add_and_a_disabled_import_button(self):
        response = self.client.get(reverse('imtihon:manage_students'))
        self.assertContains(response, 'Talaba qoʻshish')
        self.assertContains(response, 'Excel/CSV dan import (tez kunda)')
        self.assertContains(response, 'disabled aria-disabled="true"')
        self.assertContains(response, '+ Yangi guruh…')

    def test_quick_add_keeps_the_form_open_with_the_same_group(self):
        response = self.add()
        target = reverse('imtihon:manage_students') + f'?guruh={self.group.pk}#qoshish'
        self.assertRedirects(response, target, fetch_redirect_response=False)
        user = User.objects.get(username='ali01')
        self.assertEqual(user.userprofile.group, self.group)
        self.assertTrue(user.check_password('Maxfiy-2468'))

        page = self.client.get(target)
        self.assertContains(page, 'Talaba qoʻshildi: Aliyev Ali (ali01) — 101-guruh')
        self.assertContains(page, f'<option value="{self.group.pk}" selected>101-guruh</option>', html=True)
        self.assertNotContains(page, 'Maxfiy-2468')          # the typed password is never shown again
        self.assertNotContains(page, user.password)

    def test_new_group_on_the_spot(self):
        self.add(group=NEW_GROUP, new_group='  Yangi   guruh ')
        user = User.objects.get(username='ali01')
        self.assertEqual(user.userprofile.group.name, 'Yangi guruh')

    def test_duplicate_login_and_validation_errors_are_shown(self):
        make_student('ali01', self.group)
        response = self.add(login='ALI01')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '«ALI01» logini band')
        response = self.add(login='ali 02', password='123', full_name='', group='')
        self.assertContains(response, 'Login faqat harf')
        self.assertContains(response, 'Parol kamida 6 ta belgidan')
        self.assertContains(response, 'Ism-familiyani kiriting')
        self.assertContains(response, 'Guruhni tanlang')
        self.assertEqual(User.objects.filter(userprofile__role='student').count(), 1)

    def test_search_and_group_filter(self):
        other = StudentGroup.objects.create(name='102-guruh')
        make_student('ali01', self.group, name='Aliyev Ali')
        make_student('vali02', other, name='Valiyev Vali')
        page = self.client.get(reverse('imtihon:manage_students'), {'q': 'valiyev'})
        self.assertContains(page, 'vali02')
        self.assertNotContains(page, 'ali01<')
        page = self.client.get(reverse('imtihon:manage_students'), {'guruh': self.group.pk})
        self.assertContains(page, 'ali01')
        self.assertNotContains(page, 'vali02')

    def test_edit(self):
        user = make_student('ali01', self.group)
        make_student('band', self.group)
        url = reverse('imtihon:manage_student', args=[user.pk])
        response = self.client.post(url, {'login': 'band', 'full_name': 'X', 'group': self.group.pk})
        self.assertContains(response, '«band» logini band')
        response = self.client.post(url, {'login': 'ali02', 'full_name': ' Ali  Aliyev ', 'group': NEW_GROUP,
                                          'new_group': '103-guruh'})
        self.assertRedirects(response, reverse('imtihon:manage_students'), fetch_redirect_response=False)
        user.refresh_from_db()
        self.assertEqual((user.username, user.get_full_name(), user.userprofile.group.name),
                         ('ali02', 'Ali Aliyev', '103-guruh'))

    def test_reset_password(self):
        user = make_student('ali01', self.group)
        url = reverse('imtihon:manage_student', args=[user.pk])
        page = self.client.get(url)
        self.assertContains(page, 'Joriy parol koʻrsatilmaydi')
        self.assertNotContains(page, user.password)
        response = self.client.post(url, {'action': 'password', 'password': '12'})
        self.assertContains(response, 'Parol kamida 6 ta belgidan')
        response = self.client.post(url, {'action': 'password', 'password': '777888'})
        self.assertRedirects(response, url, fetch_redirect_response=False)
        user.refresh_from_db()
        self.assertTrue(user.check_password('777888'))
        self.assertNotIn('777888', user.password)
        self.assertFalse(Event.objects.filter(message__contains='777888').exists())
        self.assertFalse(LoginAttempt.objects.filter(login__contains='777888').exists())

    def test_delete_asks_first_and_warns_about_results(self):
        user = make_student('ali01', self.group)
        exam = make_exam(groups=[self.group])
        Attempt.objects.create(exam=exam, user=user, status=Attempt.FINISHED)
        url = reverse('imtihon:manage_student_delete', args=[user.pk])
        page = self.client.get(url)
        self.assertContains(page, 'Rostdan ham')
        self.assertContains(page, '1 ta imtihon natijasi ham oʻchadi')
        self.assertTrue(User.objects.filter(pk=user.pk).exists())
        self.assertRedirects(self.client.post(url), reverse('imtihon:manage_students'), fetch_redirect_response=False)
        self.assertFalse(User.objects.filter(pk=user.pk).exists())
        self.assertFalse(Attempt.objects.exists())

    def test_password_fields_are_hidden_from_error_reports(self):
        from django.views.debug import SafeExceptionReporterFilter
        response = self.add(password='Maxfiy-2468')
        request = response.wsgi_request
        self.assertEqual(tuple(request.sensitive_post_parameters), ('password',))
        cleaned = SafeExceptionReporterFilter().get_post_parameters(request)
        self.assertNotEqual(cleaned['password'], 'Maxfiy-2468')
        self.assertEqual(cleaned['login'], 'ali01')

    def test_teachers_and_admins_are_not_managed_here(self):
        other_teacher = make_teacher('ustoz2')
        for name in ('imtihon:manage_student', 'imtihon:manage_student_delete'):
            self.assertEqual(self.client.get(reverse(name, args=[other_teacher.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('imtihon:manage_student_delete', args=[other_teacher.pk])).status_code, 404)
        self.assertTrue(User.objects.filter(pk=other_teacher.pk).exists())

    def test_groups_create_rename_delete(self):
        response = self.client.post(reverse('imtihon:manage_groups'), {'name': '  201-guruh '})
        self.assertRedirects(response, reverse('imtihon:manage_groups'), fetch_redirect_response=False)
        group = StudentGroup.objects.get(name='201-guruh')
        response = self.client.post(reverse('imtihon:manage_groups'), {'name': '201-GURUH'})
        self.assertContains(response, 'allaqachon bor')
        response = self.client.post(reverse('imtihon:manage_groups'), {'name': ''})
        self.assertContains(response, 'Guruhni tanlang yoki yangi guruh nomini yozing')

        self.client.post(reverse('imtihon:manage_group', args=[group.pk]), {'name': '202-guruh'})
        group.refresh_from_db()
        self.assertEqual(group.name, '202-guruh')

        member = make_student('ali01', group)
        make_exam(groups=[group])
        url = reverse('imtihon:manage_group_delete', args=[group.pk])
        page = self.client.get(url)
        self.assertContains(page, 'Guruhda 1 ta talaba bor')
        self.assertContains(page, '1 ta imtihonga biriktirilgan')
        self.client.post(url)
        self.assertFalse(StudentGroup.objects.filter(pk=group.pk).exists())
        member.refresh_from_db()
        self.assertTrue(User.objects.filter(pk=member.pk).exists())       # students are kept
        self.assertIsNone(UserProfile.objects.get(user=member).group)


@FAST_HASHER
class PermissionTests(TestCase):
    """Teacher pages are protected on the server, not only hidden in the menu."""

    @classmethod
    def setUpTestData(cls):
        cls.group = StudentGroup.objects.create(name='101-guruh')
        cls.student = make_student('ali01', cls.group)
        cls.exam = make_exam(groups=[cls.group])
        cls.attempt = Attempt.objects.create(exam=cls.exam, user=cls.student)

    def urls(self):
        exam, student, group = self.exam.pk, self.student.pk, self.group.pk
        return [
            reverse('imtihon:manage'), reverse('imtihon:manage_import'),
            reverse('imtihon:manage_exam', args=[exam]), reverse('imtihon:manage_reimport', args=[exam]),
            reverse('imtihon:manage_exam_status', args=[exam]), reverse('imtihon:manage_exam_delete', args=[exam]),
            reverse('imtihon:manage_dashboard', args=[exam]), reverse('imtihon:manage_dashboard_data', args=[exam]),
            reverse('imtihon:manage_export', args=[exam, 'csv']), reverse('imtihon:manage_export', args=[exam, 'xlsx']),
            reverse('imtihon:manage_attempt', args=[self.attempt.pk]),
            reverse('imtihon:manage_attempt_action', args=[self.attempt.pk]),
            reverse('imtihon:manage_students'), reverse('imtihon:manage_student', args=[student]),
            reverse('imtihon:manage_student_delete', args=[student]),
            reverse('imtihon:manage_groups'), reverse('imtihon:manage_group', args=[group]),
            reverse('imtihon:manage_group_delete', args=[group]),
        ]

    def test_students_get_403_everywhere(self):
        self.client.force_login(self.student)
        for url in self.urls():
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)
                self.assertEqual(self.client.post(url, {'login': 'x', 'password': '123456', 'name': 'x',
                                                        'action': 'publish'}).status_code, 403)
        self.assertTrue(User.objects.filter(pk=self.student.pk).exists())
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(self.exam.status, 'published')

    def test_other_roles_get_403(self):
        for role in ('student', 'moder'):
            user = User.objects.create_user(f'u-{role}', password='x')
            UserProfile.objects.create(user=user, role=role)
            self.client.force_login(user)
            self.assertEqual(self.client.get(reverse('imtihon:manage_students')).status_code, 403)

    def test_anonymous_users_are_sent_to_the_login_page(self):
        for url in self.urls():
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response['Location'].startswith(reverse('imtihon:login') + '?next='))

    def test_teachers_admins_and_superusers_are_allowed(self):
        superuser = User.objects.create_superuser('root', password='x')
        for user in (make_teacher('t1'), make_teacher('a1', role='superadmin'), superuser):
            self.client.force_login(user)
            self.assertEqual(self.client.get(reverse('imtihon:manage_students')).status_code, 200)
