"""Checks every parsed question, whatever file format it came from."""
import re
import unicodedata

from . import messages as M
from .base import WARNING, Problem

MIN_OPTIONS = 2
MAX_OPTIONS = 8
MAX_QUESTIONS = 1000
MAX_QUESTION_LENGTH = 10_000
MAX_OPTION_LENGTH = 2_000
LETTERS = 'ABCDEFGH'
APOSTROPHES = re.compile("[ʻʼ’‘`´′ʹʽ]")


def comparable(text):
    """Text as compared for duplicates: oʻ / o' / o’ and case/spacing differences are ignored."""
    text = unicodedata.normalize('NFC', text or '').casefold()
    text = APOSTROPHES.sub("'", text)
    return ' '.join(text.split())


def _letter(index):
    return LETTERS[index] if index < len(LETTERS) else str(index + 1)


def validate(result):
    """Add the problems of every question to ``result`` (in place) and return it."""
    if not result.questions:
        result.add(Problem(M.NO_QUESTIONS))
        return result
    if len(result.questions) > MAX_QUESTIONS:
        result.add(Problem(M.TOO_MANY_QUESTIONS.format(count=len(result.questions), limit=MAX_QUESTIONS)))

    seen_texts = {}
    for q in result.questions:
        def add(message, line=None, level='error', q=q):
            result.add(Problem(message, level, q.number, line or q.line), q)

        if not q.text:
            add(M.EMPTY_QUESTION)
        elif len(q.text) > MAX_QUESTION_LENGTH:
            add(M.QUESTION_TOO_LONG.format(length=len(q.text), limit=MAX_QUESTION_LENGTH))

        count = len(q.options)
        if count < MIN_OPTIONS:
            add(M.TOO_FEW_OPTIONS.format(count=count))
        elif count > MAX_OPTIONS:
            add(M.TOO_MANY_OPTIONS.format(count=count, limit=MAX_OPTIONS))

        first_seen = {}
        for index, option in enumerate(q.options):
            if not option.text:
                add(M.EMPTY_OPTION.format(letter=_letter(index)), option.line)
                continue
            if len(option.text) > MAX_OPTION_LENGTH:
                add(M.OPTION_TOO_LONG.format(letter=_letter(index), length=len(option.text),
                                             limit=MAX_OPTION_LENGTH), option.line)
            key = comparable(option.text)
            if key in first_seen:
                shown = option.text if len(option.text) <= 60 else option.text[:57] + '…'
                add(M.DUPLICATE_OPTION.format(first=_letter(first_seen[key]), second=_letter(index), text=shown),
                    option.line)
            else:
                first_seen[key] = index

        correct = [index for index, option in enumerate(q.options) if option.is_correct]
        if count >= MIN_OPTIONS and not correct:
            add(M.NO_CORRECT)
        elif len(correct) > 1:
            add(M.MANY_CORRECT.format(letters=', '.join(_letter(i) for i in correct)),
                q.options[correct[1]].line)

        if q.text:
            key = comparable(q.text)
            if key in seen_texts:
                add(M.DUPLICATE_QUESTION.format(other=seen_texts[key]), level=WARNING)
            else:
                seen_texts[key] = q.number

    result.problems.sort(key=lambda p: (p.number or 0, p.line or 0))
    return result
