"""Question bank of the "Big Data tahlili" midterm (oraliq nazorat).

Every topic module defines ``PREFIX`` and ``QUESTIONS``; each question is written
with :func:`Q` as ``Q(difficulty, text, correct, wrong1, wrong2, wrong3, code=...)``.
The correct answer is always written first here — the order shown to students is
shuffled (once when the choices are stored, and again for every student), so the
position never gives the answer away.

Difficulty: 1 = boshlangʻich, 2 = oʻrta, 3 = murakkabroq. ``blueprint.TOPICS``
says how many questions of each difficulty a variant takes from every topic.
"""
import re
import textwrap
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace

from ..blueprint import SLOTS, TOPICS


@dataclass(frozen=True)
class BankQuestion:
    difficulty: int
    text: str
    correct: str
    wrong: tuple
    code: str = ''
    tags: tuple = ()
    topic: str = ''
    ref: str = ''
    options: tuple = field(default=(), compare=False)


def Q(difficulty, text, correct, *wrong, code='', tags=()):
    """``tags`` keep questions that give each other away out of one variant:
    ``"x"`` — the question asks about fact *x*; ``"~x"`` — its text reveals *x*.
    See :func:`conflicts`."""
    text = ' '.join(textwrap.dedent(text).split()) if '\n' in text else text.strip()
    code = textwrap.dedent(code).strip('\n')
    if isinstance(tags, str):
        tags = (tags,)
    return BankQuestion(
        difficulty, text, correct.strip(), tuple(w.strip() for w in wrong),
        code=code, tags=tuple(tags),
    )


def _modules():
    from . import json_q, lakehouse, mapreduce, nosql, python_q, spark, storage
    return {
        'storage': storage,
        'mapreduce': mapreduce,
        'spark': spark,
        'nosql': nosql,
        'lakehouse': lakehouse,
        'json': json_q,
        'python': python_q,
    }


def load_bank():
    """All questions, with ``topic`` and a stable ``ref`` (e.g. ``MR-07``) filled in."""
    questions = []
    for topic, module in _modules().items():
        for number, q in enumerate(module.QUESTIONS, start=1):
            questions.append(replace(
                q, topic=topic, ref=f'{module.PREFIX}-{number:02d}',
                options=(q.correct, *q.wrong),
            ))
    return questions


def _asked(q):
    return {t for t in q.tags if not t.startswith('~')}


def _revealed(q):
    return {t.lstrip('~') for t in q.tags}


def conflicts(a, b):
    """True when one question asks about a fact the other one asks about or reveals."""
    return bool(_asked(a) & _revealed(b)) or bool(_asked(b) & _revealed(a))


def _normalized(text):
    return re.sub(r'\W+', ' ', text.lower()).strip()


def validate_bank(questions, variants=41):
    """Return a list of problems (empty list = the bank is usable)."""
    problems = []
    seen_texts = {}
    topics = {code for code, _, _ in TOPICS}
    for q in questions:
        where = q.ref
        if q.topic not in topics:
            problems.append(f'{where}: nomaʼlum mavzu {q.topic!r}')
        if q.difficulty not in (1, 2, 3):
            problems.append(f'{where}: qiyinlik 1, 2 yoki 3 boʻlishi kerak')
        if not q.text:
            problems.append(f'{where}: savol matni boʻsh')
        if len(q.wrong) != 3:
            problems.append(f'{where}: 3 ta notoʻgʻri javob kerak, {len(q.wrong)} ta berilgan')
        options = [q.correct, *q.wrong]
        if any(not o for o in options):
            problems.append(f'{where}: boʻsh javob varianti bor')
        if len({o.strip() for o in options}) != len(options):
            problems.append(f'{where}: javob variantlari takrorlangan')
        key = (_normalized(q.text), q.code.strip())
        if key in seen_texts:
            problems.append(f'{where}: {seen_texts[key]} bilan bir xil savol')
        seen_texts[key] = where

    per_slot = Counter((q.topic, q.difficulty) for q in questions)
    needed = Counter(SLOTS)
    for slot, count in needed.items():
        have = per_slot.get(slot, 0)
        # Each question may appear in at most 3 variants.
        minimum = -(-variants * count // 3)
        if have < minimum:
            problems.append(
                f'{slot[0]} / qiyinlik {slot[1]}: {have} ta savol bor, kamida {minimum} ta kerak'
            )
    return problems


def bank_summary(questions):
    summary = defaultdict(Counter)
    for q in questions:
        summary[q.topic][q.difficulty] += 1
    return summary
