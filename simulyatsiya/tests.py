import re
from unittest import mock

from django.contrib.auth.models import User
from django.template.loader import get_template
from django.utils.html import escape
from django.test import TestCase, override_settings
from django.urls import reverse

from user.models import UserProfile

from . import registry
from .registry import SIMULATIONS, Simulation, enabled_simulations, get_simulation

FAST_HASHER = override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
IDS = ['venadan-qon-olish', 'gluteal-inyeksiya', 'deltoid-inyeksiya', 'insulin-inyeksiya']


def make_user(username, role='student'):
    user = User.objects.create_user(username, password='x')
    UserProfile.objects.create(user=user, role=role)
    return user


class RegistryTests(TestCase):
    def test_four_simulations_each_with_a_template(self):
        self.assertEqual([s.id for s in enabled_simulations()], IDS)
        for sim in SIMULATIONS:
            get_template(sim.template)                       # exists and compiles
            self.assertTrue(sim.title and sim.description and sim.icon.startswith('fa-'))

    def test_ids_are_unique_url_slugs(self):
        ids = [s.id for s in SIMULATIONS]
        self.assertEqual(len(ids), len(set(ids)))
        for sim_id in ids:
            self.assertRegex(sim_id, r'^[a-z0-9-]+$')

    def test_disabled_entries_are_hidden(self):
        hidden = Simulation('yashirin', 'Yashirin', 'x', 'fa-eye', enabled=False)
        with mock.patch.object(registry, 'SIMULATIONS', SIMULATIONS + [hidden]):
            self.assertNotIn(hidden, enabled_simulations())
            self.assertIsNone(get_simulation('yashirin'))


@FAST_HASHER
class PanelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.student = make_user('talaba')
        cls.teacher = make_user('ustoz', 'teacher')
        cls.admin = make_user('admin', 'superadmin')

    def test_navigation_shows_the_panel_for_every_role(self):
        for user in (self.student, self.teacher, self.admin):
            self.client.force_login(user)
            page = self.client.get(reverse('courses:topics'))
            self.assertContains(page, reverse('simulyatsiya:index'), msg_prefix=user.username)
            self.assertContains(page, '<span>Simulyatsiya</span>', html=True)

    def test_list_shows_exactly_the_registered_simulations(self):
        self.client.force_login(self.student)
        page = self.client.get(reverse('simulyatsiya:index'))
        self.assertEqual(page.status_code, 200)
        links = re.findall(r'href="(/simulyatsiya/[^"/]+/)"', page.content.decode())
        self.assertEqual(links, [reverse('simulyatsiya:detail', args=[i]) for i in IDS])
        for sim in enabled_simulations():
            self.assertContains(page, escape(sim.title))
            self.assertContains(page, escape(sim.description))

    def test_each_simulation_opens_in_a_sandboxed_frame(self):
        self.client.force_login(self.student)
        for sim_id in IDS:
            with self.subTest(sim_id=sim_id):
                page = self.client.get(reverse('simulyatsiya:detail', args=[sim_id]))   # a deep link
                self.assertEqual(page.status_code, 200)
                self.assertContains(page, 'Simulyatsiyalarga qaytish')
                iframe = re.search(r'<iframe[^>]*>', page.content.decode()).group(0)
                self.assertIn('sandbox="allow-scripts"', iframe)
                self.assertNotIn('allow-same-origin', iframe)
                self.assertNotIn('allow-top-navigation', iframe)
                self.assertIn('loading="lazy"', iframe)
                self.assertIn(f'src="{reverse("simulyatsiya:frame", args=[sim_id])}"', iframe)
                self.assertIn('title="Simulyatsiya:', iframe)

    def test_frame_document_is_locked_down(self):
        self.client.force_login(self.student)
        for sim_id in IDS:
            with self.subTest(sim_id=sim_id):
                response = self.client.get(reverse('simulyatsiya:frame', args=[sim_id]))
                self.assertEqual(response.status_code, 200)
                csp = response['Content-Security-Policy']
                self.assertIn("default-src 'none'", csp)
                self.assertIn("frame-ancestors 'self'", csp)
                self.assertNotIn('unsafe-inline', csp)
                self.assertNotIn('http', csp)
                self.assertEqual(response['X-Frame-Options'], 'SAMEORIGIN')
                html = response.content.decode()
                nonce = re.search(r"'nonce-([^']+)'", csp).group(1)
                scripts = re.findall(r'<script[^>]*>', html)
                self.assertTrue(scripts)
                for tag in scripts + re.findall(r'<style[^>]*>', html):
                    self.assertIn(f'nonce="{nonce}"', tag)        # nothing runs without the nonce
                self.assertNotRegex(html, r'(src|href)\s*=\s*["\']?(https?:)?//')   # no external resources
                self.assertNotIn('sendPrompt', html)
                self.assertNotIn('class="ti ', html)              # the originals' unloaded icon font
                self.assertIn('Simulation.start(', html)

    def test_nonce_changes_on_every_load(self):
        self.client.force_login(self.student)
        url = reverse('simulyatsiya:frame', args=[IDS[0]])
        self.assertNotEqual(self.client.get(url)['Content-Security-Policy'],
                            self.client.get(url)['Content-Security-Policy'])

    def test_other_pages_still_forbid_framing(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(reverse('simulyatsiya:detail', args=[IDS[0]]))['X-Frame-Options'], 'DENY')

    def test_unknown_simulation_is_a_proper_not_found_page(self):
        self.client.force_login(self.student)
        for name in ('simulyatsiya:detail', 'simulyatsiya:frame'):
            response = self.client.get(reverse(name, args=['yoq-simulyatsiya']))
            self.assertEqual(response.status_code, 404)
            self.assertContains(response, 'Simulyatsiya topilmadi', status_code=404)
            self.assertContains(response, reverse('simulyatsiya:index'), status_code=404)

    def test_anonymous_users_are_sent_to_the_login_page(self):
        for url in (reverse('simulyatsiya:index'), reverse('simulyatsiya:detail', args=[IDS[0]]),
                    reverse('simulyatsiya:frame', args=[IDS[0]])):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response['Location'].startswith(reverse('user:login')))

    def test_users_without_a_profile_are_blocked(self):
        self.client.force_login(User.objects.create_user('profilsiz', password='x'))
        for url in (reverse('simulyatsiya:index'), reverse('simulyatsiya:frame', args=[IDS[0]])):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response['Location'], reverse('courses:index'))
