"""The plain text test format (the teachers' sample file):

    Savol matni
    ====
    #Toʻgʻri javob
    ====
    Notoʻgʻri javob
    ====
    Notoʻgʻri javob
    ++++
    Keyingi savol
    ...

* ``++++`` (4 or more ``+`` on a line of its own) ends a question;
* ``====`` (4 or more ``=``) separates the question from the options and the options
  from each other;
* the correct option starts with ``#``; write ``\\#`` for a question or an option
  that really starts with the ``#`` character (``#\\#3`` = the correct option "#3");
* question and option texts may span several lines.
"""
import textwrap

from . import messages as M
from .base import WARNING, BaseParser, ParsedOption, ParsedQuestion, ParseResult, Problem

SEPARATOR_MIN_LENGTH = 4


def _is_separator(stripped, char):
    return len(stripped) >= SEPARATOR_MIN_LENGTH and set(stripped) == {char}


class _Part:
    def __init__(self, start_line):
        self.start_line = start_line   # first line after the separator
        self.lines = []                # (line number, text)

    def text(self):
        rows = [(n, line.rstrip()) for n, line in self.lines]
        while rows and not rows[0][1].strip():
            rows.pop(0)
        while rows and not rows[-1][1].strip():
            rows.pop()
        if not rows:
            return '', self.start_line, []
        text = textwrap.dedent('\n'.join(line for _, line in rows)).strip('\n')
        return text, rows[0][0], rows


class PlainTextParser(BaseParser):
    name = "Matn fayli (==== / ++++ / #)"
    extensions = ('.txt',)

    def split_blocks(self, text):
        """[(parts, separators_seen)] — one entry per question block."""
        blocks = []
        parts, seen = [_Part(1)], False
        for number, line in enumerate(text.split('\n'), start=1):
            stripped = line.strip()
            if _is_separator(stripped, '+'):
                if seen or any(l.strip() for part in parts for _, l in part.lines):
                    blocks.append((parts, seen))
                parts, seen = [_Part(number + 1)], False
            elif _is_separator(stripped, '='):
                parts.append(_Part(number + 1))
                seen = True
            else:
                parts[-1].lines.append((number, line))
        if seen or any(l.strip() for part in parts for _, l in part.lines):
            blocks.append((parts, seen))
        return blocks

    def parse_text(self, text):
        result = ParseResult(text=text, format_name=self.name)
        for number, (parts, _) in enumerate(self.split_blocks(text), start=1):
            question_text, question_line, question_rows = parts[0].text()
            question = ParsedQuestion(number=number, text=question_text, line=question_line)
            if question_text.startswith('\\#'):      # an escaped, literal "#"
                question.text = question_text[1:]
            elif question_text.startswith('#'):
                result.add(Problem(M.QUESTION_STARTS_WITH_HASH, WARNING, number, question_line), question)
            self._warn_hash_inside(result, question, question_rows[1:])
            for part in parts[1:]:
                option_text, option_line, rows = part.text()
                correct = option_text.startswith('#')
                if correct:
                    option_text = option_text[1:].strip()
                if option_text.startswith('\\#'):      # an escaped, literal "#"
                    option_text = option_text[1:]
                question.options.append(ParsedOption(option_text, correct, option_line))
                self._warn_hash_inside(result, question, rows[1:])
            result.questions.append(question)
        return result

    @staticmethod
    def _warn_hash_inside(result, question, rows):
        for line_number, line in rows:
            if line.lstrip().startswith('#'):
                result.add(Problem(M.HASH_INSIDE.format(line=line_number), WARNING, question.number, line_number),
                           question)
