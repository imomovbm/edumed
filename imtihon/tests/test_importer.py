"""The test file importer: the teachers' sample file, broken files and odd encodings."""
import codecs

from django.test import SimpleTestCase

from .. import importers
from ..importers import messages as M
from ..importers.base import ParseResult
from .helpers import SAMPLE, make_text


def parse(text, filename='testlar.txt', encoding='utf-8'):
    return importers.parse_file(text.encode(encoding), filename)


def messages(result):
    return [p.message for p in result.problems]


class SampleFileTests(SimpleTestCase):
    def test_sample_file_is_read_exactly(self):
        result = importers.parse_file(SAMPLE.read_bytes(), 'q.txt')
        self.assertTrue(result.ok, messages(result))
        self.assertEqual(result.encoding, 'UTF-8')
        self.assertEqual(result.problems, [])
        self.assertEqual(len(result.questions), 2)

        first, second = result.questions
        self.assertTrue(first.text.startswith('Faqat elementlarining tartibi bilan farqlanuvchi'))
        self.assertTrue(first.text.endswith('Nuqtalar o’rnini to’ldiring.'))   # the file's own apostrophes
        self.assertEqual([o.text for o in first.options],
                         ['O’rin almashtirish', 'O’rinlashtirish', 'Guruhlash', 'Qo’shish qonuni'])
        self.assertEqual([o.is_correct for o in first.options], [True, False, False, False])
        self.assertEqual((first.line, first.options[0].line), (1, 3))

        self.assertEqual(second.text, 'n ta elementdan m tadan tuzilgan guruhlashda kombinatsiyalar nimasi bilan farqlanadi?')
        self.assertEqual([o.text for o in second.options],
                         ['Elementi bilan', 'Elementi yoki tartibi bilan', 'Faqat tartibi bilan', 'To’g’ri javob yo’q'])
        self.assertEqual(second.correct_count, 1)
        self.assertEqual((second.line, second.options[0].line), (11, 13))

    def test_parser_interface(self):
        parser = importers.PARSERS[0]
        result = parser.parse_text(SAMPLE.read_text(encoding='utf-8'))
        self.assertIsInstance(result, ParseResult)
        self.assertEqual(len(result.questions), 2)
        self.assertEqual(importers.accepted_extensions(), ['.txt'])


class FormatTests(SimpleTestCase):
    def test_multi_line_texts_keep_their_lines_and_indentation(self):
        text = ('Kod nimani chiqaradi?\n\n    for i in range(2):\n        print(i)\n====\n#0\n1\n====\n'
                '2\n====\nXato\n++++\n')
        result = parse(text)
        self.assertTrue(result.ok, messages(result))
        question = result.questions[0]
        self.assertEqual(question.text, 'Kod nimani chiqaradi?\n\n    for i in range(2):\n        print(i)')
        self.assertEqual(question.options[0].text, '0\n1')

    def test_last_question_without_closing_separator(self):
        result = parse('Savol?\n====\n#Ha\n====\nYoʻq')
        self.assertTrue(result.ok, messages(result))
        self.assertEqual(len(result.questions), 1)

    def test_longer_separators_blank_lines_and_spaces_are_accepted(self):
        result = parse('\n\nSavol?  \n  ======  \n# Ha\n========\nYoʻq\n+++++++\n\n\n')
        self.assertTrue(result.ok, messages(result))
        self.assertEqual([o.text for o in result.questions[0].options], ['Ha', 'Yoʻq'])

    def test_escaped_hash_is_a_literal_character(self):
        result = parse('C++ da qaysi qator kutubxona ulaydi?\n====\n#\\#include <iostream>\n====\n\\#define X\n++++')
        self.assertTrue(result.ok, messages(result))
        options = result.questions[0].options
        self.assertEqual([(o.text, o.is_correct) for o in options],
                         [('#include <iostream>', True), ('#define X', False)])

    def test_uzbek_latin_cyrillic_russian_and_symbols_are_kept(self):
        text = ('Gʻoʻza, oʻgʻil, gʻisht va o\'g\'il — qaysi biri toʻgʻri yozilgan?\n====\n#oʻgʻil\n====\nogil\n++++\n'
                'Қайси сўз тўғри ёзилган?\n====\n#Ҳаёт\n====\nХаёт\n++++\n'
                'Какой ответ верный?\n====\n#Ответ «А»\n====\nОтвет «Б»\n++++\n'
                'x² + y² = z² boʻlsa, ∑ va π ≈ 3,14; a ≤ b, 50% & <teg>?\n====\n#√2 ≈ 1,41\n====\n½ · 10⁻³ €\n++++\n')
        result = parse(text)
        self.assertTrue(result.ok, messages(result))
        q = result.questions
        self.assertIn('Gʻoʻza, oʻgʻil', q[0].text)
        self.assertIn("o'g'il", q[0].text)
        self.assertEqual(q[1].options[0].text, 'Ҳаёт')
        self.assertEqual(q[2].options[0].text, 'Ответ «А»')
        self.assertEqual(q[3].text, 'x² + y² = z² boʻlsa, ∑ va π ≈ 3,14; a ≤ b, 50% & <teg>?')
        self.assertEqual(q[3].options[1].text, '½ · 10⁻³ €')

    def test_many_questions(self):
        result = parse(make_text(300))
        self.assertTrue(result.ok)
        self.assertEqual(len(result.questions), 300)


class BrokenFileTests(SimpleTestCase):
    def assert_error(self, result, message_start, number=None, line=None):
        self.assertFalse(result.ok)
        found = [p for p in result.errors if p.message.startswith(message_start)]
        self.assertTrue(found, f'{message_start!r} not in {messages(result)}')
        if number is not None:
            self.assertEqual(found[0].number, number)
        if line is not None:
            self.assertEqual(found[0].line, line)
        return found[0]

    def test_no_correct_answer(self):
        result = parse('Birinchi?\n====\n#Ha\n====\nYoʻq\n++++\nIkkinchi?\n====\nHa\n====\nYoʻq\n++++')
        self.assert_error(result, 'Toʻgʻri javob belgilanmagan', number=2, line=7)
        self.assertEqual(len(result.questions), 2)        # nothing is skipped silently

    def test_more_than_one_correct_answer_is_an_error(self):
        result = parse('Savol?\n====\n#A\n====\n#B\n====\nC\n++++')
        problem = self.assert_error(result, 'Bir nechta toʻgʻri javob', number=1, line=5)
        self.assertIn('A, B', problem.message)

    def test_empty_question(self):
        result = parse('Savol?\n====\n#Ha\n====\nYoʻq\n++++\n\n====\n#Ha\n====\nYoʻq\n++++')
        self.assert_error(result, 'Savol matni boʻsh', number=2)

    def test_empty_option(self):
        result = parse('Savol?\n====\n#Ha\n====\n====\nYoʻq\n++++')
        self.assert_error(result, 'B-variant boʻsh', number=1)

    def test_fewer_than_two_options(self):
        self.assert_error(parse('Savol?\n====\n#Ha\n++++'), 'Kamida 2 ta javob varianti', number=1)
        self.assert_error(parse('Separatorsiz savol\n++++'), 'Kamida 2 ta javob varianti', number=1)

    def test_too_many_options(self):
        text = 'Savol?\n' + ''.join(f'====\n{"#" if i == 0 else ""}V{i}\n' for i in range(9)) + '++++'
        self.assert_error(parse(text), 'Javob variantlari 8 tadan oshmasligi', number=1)

    def test_duplicate_options_ignore_apostrophe_style_case_and_spaces(self):
        result = parse("Savol?\n====\n#Toʻgʻri javob\n====\nTo'g'ri   JAVOB\n====\nBoshqa\n++++")
        problem = self.assert_error(result, 'A va B variantlar bir xil', number=1, line=5)
        self.assertIn("To'g'ri", problem.message)

    def test_duplicate_question_is_a_warning(self):
        result = parse('Bir xil savol?\n====\n#A\n====\nB\n++++\nBir xil savol?\n====\n#C\n====\nD\n++++')
        self.assertTrue(result.ok)
        self.assertEqual([(p.number, p.level) for p in result.problems], [(2, importers.WARNING)])

    def test_hash_in_the_wrong_place_is_a_warning(self):
        result = parse('#Savol?\n====\n#A\n====\nB\n#C\n++++')
        self.assertTrue(result.ok)
        self.assertEqual([p.line for p in result.warnings], [1, 6])

    def test_problems_are_sorted_and_all_reported(self):
        result = parse('Q1?\n====\nA\n====\nB\n++++\n\n====\n#A\n====\nA\n++++')
        self.assertEqual([p.number for p in result.errors], [1, 2, 2])

    def test_only_separators(self):
        self.assert_error(parse('++++\n++++\n'), M.NO_QUESTIONS)

    def test_too_many_questions(self):
        self.assert_error(parse(make_text(1001, options=2)), 'Savollar juda koʻp: 1001')


class FileProblemTests(SimpleTestCase):
    def assert_file_error(self, result, message_start):
        self.assertFalse(result.ok)
        self.assertEqual(result.questions, [])
        self.assertEqual(len(result.errors), 1, messages(result))
        self.assertTrue(result.errors[0].message.startswith(message_start), messages(result))
        self.assertIsNone(result.errors[0].number)

    def test_wrong_file_types(self):
        for name in ('testlar.docx', 'testlar.pdf', 'testlar.doc', 'TESTLAR.XLSX', 'testlar'):
            with self.subTest(name=name):
                self.assert_file_error(importers.parse_file(b'Savol?\n====\n#A\n====\nB', name), '«')

    def test_wrong_type_message_names_the_extension(self):
        result = importers.parse_file(b'data', 'testlar.docx')
        self.assertIn('«.docx»', result.errors[0].message)
        self.assertIn('.txt', result.errors[0].message)

    def test_extension_check_ignores_case(self):
        self.assertTrue(importers.parse_file('Savol?\n====\n#A\n====\nB'.encode(), 'TESTLAR.TXT').ok)

    def test_office_and_binary_files_renamed_to_txt(self):
        cases = [
            (b'PK\x03\x04\x14\x00\x06\x00word/document.xml', 'Word (.docx)'),
            (b'%PDF-1.7\n%\xe2\xe3', 'PDF'),
            (b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1', 'eski Word'),
            (b'\x89PNG\r\n\x1a\n', 'rasm'),
            (b'abc\x00\x01\x02def', 'binar'),
        ]
        for data, kind in cases:
            with self.subTest(kind=kind):
                result = importers.parse_file(data, 'testlar.txt')
                self.assert_file_error(result, 'Bu matn fayli emas')
                self.assertIn(kind, result.errors[0].message)

    def test_too_large(self):
        data = b'a' * (importers.MAX_FILE_BYTES + 1)
        result = importers.parse_file(data, 'testlar.txt')
        self.assert_file_error(result, 'Fayl juda katta')
        self.assertIn('2,0 MB', result.errors[0].message)

    def test_empty_file_and_missing_file(self):
        self.assert_file_error(importers.parse_file(b'', 'testlar.txt'), M.EMPTY_FILE)
        self.assert_file_error(importers.parse_file(b'  \n\r\n\t ', 'testlar.txt'), M.EMPTY_FILE)
        self.assert_file_error(importers.parse_file(b'', ''), M.NO_FILE)

    def test_undecodable_bytes(self):
        # 0x98 is not used in Windows-1251 and the bytes are not UTF-8 either.
        self.assert_file_error(importers.parse_file(b'Savol \x98\x98?\n====\n#A\n====\nB', 'testlar.txt'),
                               'Fayl kodlashini aniqlab boʻlmadi')

    def test_text_typed_in_the_editor_is_checked_for_size(self):
        result = importers.parse_text('a' * (importers.MAX_FILE_BYTES + 1))
        self.assertTrue(result.errors[0].message.startswith('Matn juda katta'))


class EncodingTests(SimpleTestCase):
    TEXT = 'Какой ответ верный?\r\n====\r\n#Первый\r\n====\r\nВторой\r\n++++\r\n'

    def check(self, data, label):
        result = importers.parse_file(data, 'testlar.txt')
        self.assertTrue(result.ok, messages(result))
        self.assertEqual(result.encoding, label)
        self.assertEqual(result.questions[0].text, 'Какой ответ верный?')
        self.assertEqual([o.text for o in result.questions[0].options], ['Первый', 'Второй'])
        self.assertEqual(result.questions[0].options[0].line, 3)
        self.assertNotIn('\r', result.text)

    def test_utf8(self):
        self.check(self.TEXT.encode('utf-8'), 'UTF-8')

    def test_utf8_with_bom(self):
        self.check(codecs.BOM_UTF8 + self.TEXT.encode('utf-8'), 'UTF-8 (BOM)')

    def test_utf16_notepad_unicode(self):
        self.check(self.TEXT.encode('utf-16'), 'UTF-16')
        self.check(codecs.BOM_UTF16_BE + self.TEXT.encode('utf-16-be'), 'UTF-16')

    def test_windows_1251(self):
        self.check(self.TEXT.encode('cp1251'), 'Windows-1251')

    def test_old_mac_line_ends(self):
        self.check(self.TEXT.replace('\r\n', '\r').encode('utf-8'), 'UTF-8')

    def test_decomposed_letters_are_normalised(self):
        # "й" typed as и + combining breve compares equal to the composed letter.
        result = parse('Savol?\n====\n#Ответ й\n====\nОтвет й\n++++')
        self.assertFalse(result.ok)
        self.assertTrue(any(p.message.startswith('A va B variantlar bir xil') for p in result.errors))

    def test_invisible_control_characters_are_removed(self):
        result = parse('Sa\x07vol?\x0b\n====\n#Ha\x1b\n====\nYoʻq\n++++')
        self.assertTrue(result.ok, messages(result))
        self.assertEqual(result.questions[0].text, 'Savol?')
        self.assertEqual(result.questions[0].options[0].text, 'Ha')
