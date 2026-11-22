"""End to end: import the sample file, publish for a group, a student takes it, the teacher exports."""
import csv
import io

from django.test import TestCase
from django.urls import reverse
from openpyxl import load_workbook

from user.models import StudentGroup

from ..forms import NEW_GROUP
from ..models import Attempt, Exam, Question
from .helpers import FAST_HASHER, SAMPLE, api, correct_position, make_exam, make_student, make_teacher


@FAST_HASHER
class ImportToResultFlowTests(TestCase):
    def test_import_publish_take_and_export(self):
        make_teacher('ustoz', 'Ustoz-2026!')
        teacher = self.client

        # The teacher signs in on the exam login page.
        response = teacher.post(reverse('imtihon:login'), {'login': 'ustoz', 'password': 'Ustoz-2026!'})
        self.assertRedirects(response, reverse('imtihon:manage'), fetch_redirect_response=False)

        # Upload the sample file -> preview.
        with open(SAMPLE, 'rb') as handle:
            response = teacher.post(reverse('imtihon:manage_import'), {'subject': 'Ehtimollar', 'file': handle})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '2 ta savol')
        self.assertContains(response, 'Xato yoʻq')
        self.assertContains(response, 'O’rin almashtirish')
        self.assertContains(response, 'Kodlash: UTF-8')
        preview = response.context['result']
        self.assertTrue(preview.ok)
        self.assertEqual(response.context['title'], 'q')                   # from the file name until changed
        self.assertFalse(Exam.objects.exists())                             # nothing saved yet

        # Confirm -> a draft exam.
        response = teacher.post(reverse('imtihon:manage_import'), {
            'action': 'save', 'text': preview.text, 'title': ' Kombinatorika   nazorati ', 'subject': 'Ehtimollar',
            'source_name': 'q.txt',
        })
        exam = Exam.objects.get()
        self.assertRedirects(response, reverse('imtihon:manage_exam', args=[exam.pk]), fetch_redirect_response=False)
        self.assertEqual((exam.title, exam.status, exam.source_name), ('Kombinatorika nazorati', Exam.DRAFT, 'q.txt'))
        keys = [q.choices.get(is_correct=True).text for q in exam.questions.order_by('order')]
        self.assertEqual(keys, ['O’rin almashtirish', 'Elementi bilan'])
        self.assertEqual(Question.objects.get(exam=exam, order=2).choices.count(), 4)

        # Publishing is refused while the exam is not assigned to anyone.
        status_url = reverse('imtihon:manage_exam_status', args=[exam.pk])
        teacher.post(status_url, {'action': 'publish'})
        exam.refresh_from_db()
        self.assertEqual(exam.status, Exam.DRAFT)

        # Two students in two groups, added through the panel (groups created on the spot).
        for login, password, name, group in (('ali01', '135790', 'Aliyev Ali', '101-guruh'),
                                             ('bobur02', '246802', 'Boburov Bobur', '102-guruh')):
            response = teacher.post(reverse('imtihon:manage_students'), {
                'login': login, 'password': password, 'full_name': name, 'group': NEW_GROUP, 'new_group': group})
            self.assertEqual(response.status_code, 302)
        group = StudentGroup.objects.get(name='101-guruh')

        # Settings: 15 minutes, group 101 only; then publish.
        response = teacher.post(reverse('imtihon:manage_exam', args=[exam.pk]), {
            'title': 'Kombinatorika nazorati', 'subject': 'Ehtimollar', 'duration_minutes': '15',
            'starts_at': '', 'ends_at': '', 'question_count': '', 'shuffle_questions': 'on',
            'shuffle_options': 'on', 'max_leaves': '3', 'show_score': 'on', 'groups': [str(group.pk)],
        })
        self.assertRedirects(response, reverse('imtihon:manage_exam', args=[exam.pk]), fetch_redirect_response=False)
        teacher.post(status_url, {'action': 'publish'})
        exam.refresh_from_db()
        self.assertEqual((exam.status, exam.duration_minutes), (Exam.PUBLISHED, 15))
        self.assertEqual(list(exam.groups.all()), [group])

        # A student of the group signs in, takes the exam and answers everything correctly.
        student = self.client_class()
        response = student.post(reverse('imtihon:login'), {'login': 'ALI01', 'password': '135790'})
        self.assertRedirects(response, reverse('imtihon:my_exams'), fetch_redirect_response=False)
        self.assertContains(student.get(reverse('imtihon:my_exams')), 'Kombinatorika nazorati')
        self.assertEqual(student.get(reverse('imtihon:exam', args=[exam.pk])).context['state'], 'lobby')
        data = api(student, exam, 'start', {'accept': True}).json()
        self.assertEqual(len(data['questions']), 2)
        self.assertEqual(data['remaining'], 15 * 60)
        attempt = Attempt.objects.get(user__username='ali01')
        for q in range(2):
            self.assertTrue(api(student, exam, 'answer', {'q': q, 'o': correct_position(attempt, q)}).json()['ok'])
        self.assertTrue(api(student, exam, 'finish').json()['ok'])
        result = student.get(reverse('imtihon:result', args=[exam.pk]))
        self.assertContains(result, '2 <small>/ 2</small>', html=True)
        self.assertContains(result, '100,0%')

        # A student of another group sees nothing.
        other = self.client_class()
        other.post(reverse('imtihon:login'), {'login': 'bobur02', 'password': '246802'})
        self.assertNotContains(other.get(reverse('imtihon:my_exams')), 'Kombinatorika nazorati')
        self.assertEqual(other.get(reverse('imtihon:exam', args=[exam.pk])).status_code, 404)

        # The teacher sees the result live and exports it.
        rows = teacher.get(reverse('imtihon:manage_dashboard_data', args=[exam.pk])).json()['rows']
        self.assertEqual([(r['login'], r['status'], r['score']) for r in rows], [('ali01', 'finished', 100.0)])

        response = teacher.get(reverse('imtihon:manage_export', args=[exam.pk, 'csv']))
        self.assertEqual(response['Content-Type'], 'text/csv; charset=utf-8')
        self.assertIn('attachment; filename="natijalar_Kombinatorika_nazorati_', response['Content-Disposition'])
        table = list(csv.DictReader(io.StringIO(response.content.decode('utf-8-sig'))))
        self.assertEqual(len(table), 1)
        self.assertEqual((table[0]['Login'], table[0]['Guruh'], table[0]['Toʻgʻri'], table[0]['Natija (%)']),
                         ('ali01', '101-guruh', '2', '100.0'))

        response = teacher.get(reverse('imtihon:manage_export', args=[exam.pk, 'xlsx']))
        book = load_workbook(io.BytesIO(response.content))
        self.assertEqual(book.sheetnames, ['Natijalar', 'Javoblar'])
        header, first = list(book['Natijalar'].iter_rows(values_only=True))[:2]
        self.assertEqual(first[header.index('Login')], 'ali01')
        self.assertEqual(first[header.index('Natija (%)')], 100.0)
        answers = list(book['Javoblar'].iter_rows(values_only=True))[1:]
        self.assertEqual([row[-1] for row in answers], ['Toʻgʻri', 'Toʻgʻri'])

        # Finishing the exam keeps the results.
        teacher.post(status_url, {'action': 'finish'})
        exam.refresh_from_db()
        self.assertEqual(exam.status, Exam.FINISHED)
        self.assertContains(student.get(reverse('imtihon:my_exams')), '100,0%')


@FAST_HASHER
class ImportPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.teacher = make_teacher()

    def setUp(self):
        self.client.force_login(self.teacher)

    def upload(self, content, name='testlar.txt', **extra):
        handle = io.BytesIO(content if isinstance(content, bytes) else content.encode('utf-8'))
        handle.name = name
        return self.client.post(reverse(extra.pop('url_name', 'imtihon:manage_import'), args=extra.pop('args', [])),
                                {'file': handle, 'title': 'Sinov', **extra})

    def test_broken_file_shows_every_problem_and_cannot_be_saved(self):
        text = 'Savol 1?\n====\nA\n====\nB\n++++\n\n====\n#A\n====\nA\n++++\nSavol 3?\n====\n#A\n====\n#B\n++++'
        response = self.upload(text)
        self.assertContains(response, '3 ta savol')
        self.assertContains(response, '4 ta xato')
        self.assertContains(response, '1-savol, 1-qator:')
        self.assertContains(response, 'Toʻgʻri javob belgilanmagan')
        self.assertContains(response, '2-savol, 7-qator:')
        self.assertContains(response, 'Savol matni boʻsh')
        self.assertContains(response, 'A va B variantlar bir xil')
        self.assertContains(response, 'Bir nechta toʻgʻri javob belgilangan (A, B)')
        self.assertContains(response, 'data-line="7"')                       # "go to line" buttons
        self.assertContains(response, 'value="save" disabled')
        response = self.client.post(reverse('imtihon:manage_import'), {'action': 'save', 'text': text, 'title': 'Sinov'})
        self.assertContains(response, 'Xatolar tuzatilmaguncha saqlab boʻlmaydi')
        self.assertFalse(Exam.objects.exists())

    def test_fix_in_the_editor_then_save(self):
        response = self.upload('Savol?\n====\nHa\n====\nYoʻq\n++++')
        self.assertFalse(response.context['result'].ok)
        fixed = 'Savol?\n====\n#Ha\n====\nYoʻq\n++++'
        response = self.client.post(reverse('imtihon:manage_import'),
                                    {'action': 'check', 'text': fixed, 'title': 'Sinov', 'source_name': 'testlar.txt'})
        self.assertTrue(response.context['result'].ok)
        self.assertContains(response, 'Fayl toʻgʻri')
        self.client.post(reverse('imtihon:manage_import'),
                         {'action': 'save', 'text': fixed, 'title': 'Sinov', 'source_name': 'testlar.txt'})
        exam = Exam.objects.get()
        self.assertEqual(exam.questions.get().choices.get(is_correct=True).text, 'Ha')

    def test_editor_text_keeps_line_numbers_even_with_leading_blank_lines(self):
        response = self.upload('\n\nSavol?\n====\nHa\n====\nYoʻq\n++++')
        self.assertContains(response, '1-savol, 3-qator:')
        self.assertContains(response, '<textarea class="editor" id="editor" name="text" rows="18" spellcheck="false">\n\n\nSavol?')

    def test_wrong_file_type_and_empty_upload(self):
        response = self.upload(b'PK\x03\x04', name='testlar.docx')
        self.assertContains(response, '«.docx» turidagi fayl qabul qilinmaydi')
        self.assertNotContains(response, 'id="editor"')
        response = self.client.post(reverse('imtihon:manage_import'), {'title': 'Sinov'})
        self.assertContains(response, 'Fayl tanlanmagan')
        self.assertFalse(Exam.objects.exists())

    def test_title_is_required(self):
        response = self.client.post(reverse('imtihon:manage_import'),
                                    {'action': 'save', 'text': 'S?\n====\n#A\n====\nB', 'title': '  '})
        self.assertContains(response, 'Imtihon nomini kiriting')
        self.assertFalse(Exam.objects.exists())

    def test_reimport_replaces_the_questions_of_a_draft(self):
        exam = make_exam(count=5, status=Exam.DRAFT)
        response = self.client.post(reverse('imtihon:manage_reimport', args=[exam.pk]),
                                    {'action': 'save', 'text': SAMPLE.read_text(encoding='utf-8'), 'source_name': 'q.txt'})
        self.assertRedirects(response, reverse('imtihon:manage_exam', args=[exam.pk]), fetch_redirect_response=False)
        exam.refresh_from_db()
        self.assertEqual((exam.questions.count(), exam.title, exam.source_name), (2, 'Test imtihon', 'q.txt'))

    def test_reimport_is_refused_once_students_started(self):
        group = StudentGroup.objects.create(name='G')
        exam = make_exam(groups=[group], count=5)
        Attempt.objects.create(exam=exam, user=make_student('ali01', group), status=Attempt.RUNNING)
        response = self.client.post(reverse('imtihon:manage_reimport', args=[exam.pk]),
                                    {'action': 'save', 'text': SAMPLE.read_text(encoding='utf-8')})
        self.assertRedirects(response, reverse('imtihon:manage_exam', args=[exam.pk]), fetch_redirect_response=False)
        self.assertEqual(exam.questions.count(), 5)
