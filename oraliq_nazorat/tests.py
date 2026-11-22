import csv
import os
import tempfile
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone

from .export import migration_state_apps, old_tables_exist

OLD = [('oraliq_nazorat', '0001_initial')]
REMOVED = [('oraliq_nazorat', '0002_remove_oraliq_exam')]


class RemovalMigrationTests(TransactionTestCase):
    """Migration 0002 must export the old exam before it deletes anything."""

    def migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.migrate(targets)

    def seed_old_exam(self):
        apps = migration_state_apps(connection)
        User = apps.get_model('auth', 'User')
        UserProfile = apps.get_model('user', 'UserProfile')
        Exam = apps.get_model('oraliq_nazorat', 'Exam')
        Question = apps.get_model('oraliq_nazorat', 'Question')
        Choice = apps.get_model('oraliq_nazorat', 'Choice')
        Variant = apps.get_model('oraliq_nazorat', 'Variant')
        Attempt = apps.get_model('oraliq_nazorat', 'Attempt')
        Answer = apps.get_model('oraliq_nazorat', 'Answer')
        Event = apps.get_model('oraliq_nazorat', 'Event')

        exam = Exam.objects.create(code='big-data-oraliq', title='Big Data tahlili — oraliq nazorat')
        question = Question.objects.create(exam=exam, ref='FS-01', topic='storage', difficulty=1, text='Savol?')
        right = Choice.objects.create(question=question, text='Toʻgʻri', is_correct=True)
        Choice.objects.create(question=question, text='Notoʻgʻri', is_correct=False)
        variant = Variant.objects.create(exam=exam, number=1)
        now = timezone.now()
        for n in (1, 2):
            user = User.objects.create(username=f'student{n}@mail.uz', email=f'student{n}@mail.uz',
                                       first_name='Talaba', last_name=str(n), password='!')
            UserProfile.objects.create(user=user, role='student')
            attempt = Attempt.objects.create(
                exam=exam, user=user, variant=variant, status='finished', started_at=now, finished_at=now,
                finish_reason='submitted', question_order=[question.pk],
                choice_order={str(question.pk): [right.pk]}, question_count=1, correct_count=1, score=100.0,
            )
            Answer.objects.create(attempt=attempt, question=question, choice=right)
            Event.objects.create(attempt=attempt, user=user, kind='start', message='Imtihonni boshladi')
        keeper = User.objects.create(username='hamshira@edumed.uz', email='hamshira@edumed.uz', password='!')
        UserProfile.objects.create(user=keeper, role='student')

    def test_export_then_delete_accounts_then_drop_tables(self):
        self.migrate(OLD)
        try:
            self.seed_old_exam()
            with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {'ORALIQ_EXPORT_DIR': tmp}):
                self.migrate(REMOVED)
                folders = list(Path(tmp).glob('oraliq_eksport_*'))
                self.assertEqual(len(folders), 1)
                files = sorted(p.name for p in folders[0].iterdir())
                self.assertEqual(files, ['hodisalar.csv', 'javoblar.csv', 'kirish_urinishlari.csv',
                                         'natijalar.csv', 'talabalar.csv'])
                with open(folders[0] / 'natijalar.csv', encoding='utf-8-sig') as handle:
                    rows = list(csv.DictReader(handle))
                self.assertEqual([r['Login'] for r in rows], ['student1@mail.uz', 'student2@mail.uz'])
                self.assertEqual(rows[0]['Natija (%)'], '100.0')
        finally:
            self.migrate(REMOVED)

        User = migration_state_apps(connection).get_model('auth', 'User')
        self.assertEqual(list(User.objects.values_list('username', flat=True)), ['hamshira@edumed.uz'])
        self.assertFalse(old_tables_exist(connection))

    def test_migration_can_be_reverted(self):
        self.migrate(OLD)
        try:
            self.assertTrue(old_tables_exist(connection))   # tables come back (empty)
        finally:
            self.migrate(REMOVED)
        self.assertFalse(old_tables_exist(connection))

    def test_export_command_explains_when_tables_are_gone(self):
        with self.assertRaisesMessage(CommandError, 'allaqachon oʻchirilgan'):
            call_command('export_oraliq_results')
