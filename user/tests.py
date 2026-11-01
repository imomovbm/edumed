from types import SimpleNamespace
from unittest import mock

from django.contrib.auth.models import User
from django.test import override_settings
from django.urls import reverse

from courses.models import Response
from edumed.test_utils import PASSWORD, EdumedTestCase, make_question, make_quiz, make_topic, make_user

from .models import PasswordResetRequest, UserProfile


REGISTER_DATA = {
    'first_name': 'Malika', 'last_name': 'Karimova', 'email': 'Malika@Example.UZ',
    'phone_number': '+998 90 123 45 67', 'gender': '0', 'region': 'Samarqand Viloyati',
    'otm': 'Samarqand Davlat Tibbiyot Universiteti', 'date_of_birth': '2004-05-17',
    'password': 'Hamshira-2026!', 'password2': 'Hamshira-2026!',
}


class RegistrationTests(EdumedTestCase):
    def test_register_creates_user_and_profile(self):
        response = self.client.post(reverse('user:register'), REGISTER_DATA)
        self.assertRedirects(response, reverse('user:index'))
        user = User.objects.get(email='malika@example.uz')
        self.assertEqual(user.username, 'malika@example.uz')
        self.assertEqual((user.userprofile.role, user.userprofile.gender), ('student', 0))

    def test_errors_keep_entered_data(self):
        data = dict(REGISTER_DATA, password2='other-password')
        response = self.client.post(reverse('user:register'), data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="Malika"')
        self.assertContains(response, 'Parollar bir xil emas!')
        self.assertFalse(User.objects.filter(email='malika@example.uz').exists())

    def test_duplicate_email_is_case_insensitive(self):
        response = self.client.post(reverse('user:register'), dict(REGISTER_DATA, email='STUDENT@edumed.uz'))
        self.assertContains(response, "Bu email avval ro&#x27;yxatdan o&#x27;tgan.")

    def test_weak_password_and_missing_fields(self):
        response = self.client.post(reverse('user:register'), dict(REGISTER_DATA, password='12345678', password2='12345678'))
        self.assertEqual(response.status_code, 200)
        response = self.client.post(reverse('user:register'), {})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.filter(email__iexact='malika@example.uz').count(), 0)


class LoginLogoutTests(EdumedTestCase):
    def test_login_is_case_insensitive_and_follows_next(self):
        url = reverse('user:login') + '?next=' + reverse('courses:topics')
        response = self.client.post(url, {'email': 'Student@Edumed.UZ', 'password': PASSWORD})
        self.assertRedirects(response, reverse('courses:topics'))

    def test_external_next_is_ignored(self):
        response = self.client.post(reverse('user:login') + '?next=https://evil.example/',
                                    {'email': 'student@edumed.uz', 'password': PASSWORD})
        self.assertRedirects(response, reverse('user:index'))

    def test_wrong_password_keeps_email(self):
        response = self.client.post(reverse('user:login'), {'email': 'student@edumed.uz', 'password': 'nope'})
        self.assertContains(response, 'value="student@edumed.uz"')
        response = self.client.post(reverse('user:login'), {})
        self.assertEqual(response.status_code, 200)

    def test_logout_needs_post(self):
        self.login(self.student)
        self.client.get(reverse('user:logout'))
        self.assertEqual(self.client.get(reverse('user:index')).status_code, 200)
        self.client.post(reverse('user:logout'))
        self.assertEqual(self.client.get(reverse('user:index')).status_code, 302)


class ForgotPasswordTests(EdumedTestCase):
    def test_request_is_linked_by_phone_in_any_format(self):
        self.student.userprofile.phone = '+998 (90) 123-45-67'
        self.student.userprofile.save()
        self.client.post(reverse('user:forgot_password'), {'contact_input': '901234567'})
        self.assertEqual(PasswordResetRequest.objects.get().linked_user, self.student)

    def test_requests_are_rate_limited(self):
        for _ in range(5):
            self.client.post(reverse('user:forgot_password'), {'contact_input': 'student@edumed.uz'})
        self.assertEqual(PasswordResetRequest.objects.count(), 3)


class AdminUserManagementTests(EdumedTestCase):
    def test_student_cannot_list_or_delete_users(self):
        self.login(self.student)
        self.assertEqual(self.client.get(reverse('user:all_users')).status_code, 302)
        self.client.post(reverse('user:delete_user', args=[self.other.id]))
        self.assertTrue(User.objects.filter(pk=self.other.pk).exists())
        self.assertEqual(self.client.get(reverse('user:user_detail', args=[self.other.id])).status_code, 302)

    def test_admin_deletes_others_but_not_self(self):
        self.login(self.admin)
        self.client.post(reverse('user:delete_user', args=[self.admin.id]))
        self.assertTrue(User.objects.filter(pk=self.admin.pk).exists())
        self.client.post(reverse('user:delete_user', args=[self.other.id]))
        self.assertFalse(User.objects.filter(pk=self.other.pk).exists())

    def test_change_role(self):
        self.login(self.admin)
        self.client.post(reverse('user:change_role', args=[self.student.id]), {'role': 'teacher'})
        self.student.userprofile.refresh_from_db()
        self.assertEqual(self.student.userprofile.role, 'teacher')
        self.client.post(reverse('user:change_role', args=[self.admin.id]), {'role': 'student'})
        self.admin.userprofile.refresh_from_db()
        self.assertEqual(self.admin.userprofile.role, 'superadmin')

    def test_reset_password_shows_temporary_password_once(self):
        PasswordResetRequest.objects.create(contact_input='student@edumed.uz', linked_user=self.student)
        self.login(self.admin)
        self.client.post(reverse('user:reset_password', args=[self.student.id]))
        detail = self.client.get(reverse('user:user_detail', args=[self.student.id]))
        temp = detail.context['temp_password']
        self.assertTrue(temp)
        self.student.refresh_from_db()
        self.assertTrue(self.student.check_password(temp))
        self.assertTrue(PasswordResetRequest.objects.get().is_resolved)
        again = self.client.get(reverse('user:user_detail', args=[self.student.id]))
        self.assertIsNone(again.context['temp_password'])

    def test_users_page_lists_open_reset_requests(self):
        PasswordResetRequest.objects.create(contact_input='+998901234567')
        self.login(self.admin)
        response = self.client.get(reverse('user:all_users'))
        self.assertContains(response, '+998901234567')


class SettingsTests(EdumedTestCase):
    def test_update_profile(self):
        self.login(self.student)
        self.client.post(reverse('user:settings'), {
            'action': 'profile', 'first_name': 'Aziza', 'last_name': 'Olimova', 'phone': '911112233',
            'gender': '0', 'region': 'Navoiy Viloyati', 'otm': '', 'date_of_birth': '2003-01-02',
        })
        self.student.refresh_from_db()
        self.assertEqual(self.student.first_name, 'Aziza')
        self.assertEqual((self.student.userprofile.gender, self.student.userprofile.region), (0, 'Navoiy Viloyati'))

    def test_change_password(self):
        self.login(self.student)
        self.client.post(reverse('user:settings'), {
            'action': 'password', 'old_password': 'wrong', 'new_password': 'Yangi-parol-77', 'new_password2': 'Yangi-parol-77'})
        self.student.refresh_from_db()
        self.assertTrue(self.student.check_password(PASSWORD))
        self.client.post(reverse('user:settings'), {
            'action': 'password', 'old_password': PASSWORD, 'new_password': 'Yangi-parol-77', 'new_password2': 'Yangi-parol-77'})
        self.student.refresh_from_db()
        self.assertTrue(self.student.check_password('Yangi-parol-77'))
        # still logged in
        self.assertEqual(self.client.get(reverse('user:index')).status_code, 200)


class ProfilePageTests(EdumedTestCase):
    def test_female_gender_is_shown(self):
        self.student.userprofile.gender = 0
        self.student.userprofile.save()
        self.login(self.student)
        self.assertContains(self.client.get(reverse('user:index')), 'Ayol')

    def test_chart_uses_real_topics_and_platform_average(self):
        topic = make_topic('Bioetika')
        make_topic('Testsiz mavzu')
        quiz = make_quiz('Q', [make_question('Q', 'sha')], topic=topic)
        Response.objects.create(user=self.student, quiz=quiz, score=80)
        Response.objects.create(user=self.other, quiz=quiz, score=40)
        self.login(self.student)
        chart = self.client.get(reverse('user:index')).context['chart_data']
        self.assertEqual(chart, {'labels': ['Bioetika'], 'user': [80], 'platform': [60]})


def fake_message(text='Kuchli tomonlar:\n- Bioetika', stop_reason='end_turn'):
    return SimpleNamespace(stop_reason=stop_reason, content=[SimpleNamespace(type='text', text=text)])


class AIAnalysisTests(EdumedTestCase):
    def setUp(self):
        quiz = make_quiz('Q', [make_question('Q', 'sha')], topic=make_topic())
        Response.objects.create(user=self.student, quiz=quiz, score=75)
        self.login(self.student)

    def test_disabled_without_api_key(self):
        response = self.client.post(reverse('user:ai_analysis'), follow=True)
        self.assertIn("AI tahlili hozircha yoqilmagan.", self.messages_of(response))

    @override_settings(ANTHROPIC_API_KEY='test-key', ANTHROPIC_MODEL='claude-opus-5-5')
    def test_analysis_is_saved_and_rate_limited(self):
        anthropic = __import__('anthropic')
        with mock.patch.object(anthropic, 'Anthropic') as client_cls:
            client_cls.return_value.beta.messages.create.return_value = fake_message()
            self.client.post(reverse('user:ai_analysis'))
            kwargs = client_cls.return_value.beta.messages.create.call_args.kwargs
            self.assertEqual(kwargs['model'], 'claude-opus-5-5')
            self.assertEqual(kwargs['fallbacks'], 'default')
            self.assertNotIn('student@edumed.uz', str(kwargs['messages']))  # no personal data sent
            profile = UserProfile.objects.get(user=self.student)
            self.assertIn('Bioetika', profile.ai_analysis)

            self.client.post(reverse('user:ai_analysis'))  # within the cooldown
            self.assertEqual(client_cls.return_value.beta.messages.create.call_count, 1)

    @override_settings(ANTHROPIC_API_KEY='test-key')
    def test_api_errors_become_messages(self):
        anthropic = __import__('anthropic')
        with mock.patch.object(anthropic, 'Anthropic') as client_cls:
            client_cls.return_value.beta.messages.create.return_value = fake_message(stop_reason='refusal')
            response = self.client.post(reverse('user:ai_analysis'), follow=True)
        self.assertIn("AI bu so'rov bo'yicha tahlil bera olmadi.", self.messages_of(response))
        self.assertEqual(UserProfile.objects.get(user=self.student).ai_analysis, '')

    @override_settings(ANTHROPIC_API_KEY='test-key')
    def test_students_cannot_run_analysis_for_others(self):
        other = make_user('third@edumed.uz')
        response = self.client.post(reverse('user:user_ai_analysis', args=[other.id]))
        self.assertRedirects(response, reverse('user:index'))
