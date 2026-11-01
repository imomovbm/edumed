"""Quiz grading, manual (teacher) grading and topic-progress bookkeeping.

Every question of a submitted quiz gets at least one ``ResponseDetails`` row:

* ``is_correct=True``  -> answered correctly
* ``is_correct=False`` -> answered incorrectly
* ``is_correct=None``  -> skipped, or a short/essay answer waiting for a teacher

``Response.correct_count + incorrect_count + skipped_count`` is always the number
of questions the quiz had when it was submitted, and ``score`` is
``correct_count / that total * 100``.
"""
from django.db import transaction
from django.db.models import Max, Prefetch

from .models import (
    QuestionChoice, Quiz, QuizQuestion, Response, ResponseDetails, TopicProgress,
)

PASS_SCORE = 60  # a topic quiz counts as passed from this score (%)

CHOICE_TYPES = ('mc', 'ms', 'tf')
TEXT_TYPES = ('sha', 'es')

TF_TRUE_LABEL = "To'g'ri"
TF_FALSE_LABEL = "Noto'g'ri"
_TF_TRUE_WORDS = {"to'g'ri", 'togri', 'true', 'ha', 'yes', 'rost', 'верно', 'правда'}
_TF_FALSE_WORDS = {"noto'g'ri", 'notogri', 'false', "yo'q", 'yoq', 'no', 'yolg\'on', 'неверно', 'ложь'}


def _normalize(text):
    text = (text or '').strip().lower()
    for apostrophe in ('‘', '’', 'ʻ', 'ʼ', '`', '´'):
        text = text.replace(apostrophe, "'")
    return text


def tf_value_from_text(text):
    """'true' / 'false' for a recognised true/false label, otherwise None."""
    text = _normalize(text)
    if text in _TF_TRUE_WORDS:
        return 'true'
    if text in _TF_FALSE_WORDS:
        return 'false'
    return None


def tf_choice_value(choice, position):
    """Map a true/false QuestionChoice to 'true' / 'false'.

    Uses the text first ("To'g'ri" / "Noto'g'ri" are what the editor creates) and
    falls back to the position (first choice = true).
    """
    return tf_value_from_text(choice.choice_text) or ('true' if position == 0 else 'false')


def tf_label(value):
    return {'true': TF_TRUE_LABEL, 'false': TF_FALSE_LABEL}.get(value, value)


def _choices_of(question):
    """Choices in a stable order; uses the prefetch cache when present."""
    return sorted(question.questionchoice_set.all(), key=lambda c: c.pk)


def _resolve_single_choice(question, raw_value):
    """Turn a submitted value (choice id, or 'true'/'false' for TF) into a choice."""
    choices = _choices_of(question)
    value = (raw_value or '').strip()
    if value.isdigit():
        return next((c for c in choices if c.pk == int(value)), None)
    if question.type == 'tf' and value.lower() in ('true', 'false'):
        return next(
            (c for i, c in enumerate(choices) if tf_choice_value(c, i) == value.lower()),
            None,
        )
    return None


def quiz_questions_for(quiz):
    """QuizQuestion rows in quiz order, with questions and choices prefetched."""
    return (
        QuizQuestion.objects
        .filter(quiz=quiz)
        .select_related('question')
        .prefetch_related(Prefetch(
            'question__questionchoice_set',
            queryset=QuestionChoice.objects.order_by('id'),
        ))
        .order_by('order', 'id')
    )


@transaction.atomic
def grade_submission(user, quiz, data, violation_count=0):
    """Create a Response (with details) for a submitted quiz form and return it."""
    response = Response.objects.create(
        user=user, quiz=quiz, score=0, violation_count=violation_count,
    )
    correct = incorrect = skipped = 0
    details = []

    for qq in quiz_questions_for(quiz):
        q = qq.question
        key = f'q_{q.pk}'

        if q.type == 'ms':
            valid = {c.pk: c for c in _choices_of(q)}
            selected = []
            for raw in data.getlist(key):
                raw = str(raw).strip()
                if raw.isdigit() and int(raw) in valid and valid[int(raw)] not in selected:
                    selected.append(valid[int(raw)])
            if not selected:
                skipped += 1
                details.append(ResponseDetails(response=response, question=q, is_correct=None))
                continue
            correct_ids = {pk for pk, c in valid.items() if c.is_correct}
            ok = {c.pk for c in selected} == correct_ids
            correct += ok
            incorrect += not ok
            details.extend(
                ResponseDetails(response=response, question=q, question_choice=c, is_correct=ok)
                for c in selected
            )

        elif q.type in ('mc', 'tf'):
            raw = (data.get(key) or '').strip()
            if not raw:
                skipped += 1
                details.append(ResponseDetails(response=response, question=q, is_correct=None))
                continue
            choice = _resolve_single_choice(q, raw)
            ok = bool(choice and choice.is_correct)
            correct += ok
            incorrect += not ok
            details.append(ResponseDetails(
                response=response, question=q, question_choice=choice, is_correct=ok,
            ))

        else:  # 'sha', 'es' (and any unknown type): a teacher grades it later
            text = (data.get(key) or '').strip()
            skipped += 1
            details.append(ResponseDetails(
                response=response, question=q, user_text_answer=text or None, is_correct=None,
            ))

    ResponseDetails.objects.bulk_create(details)
    _store_counts(response, correct, incorrect, skipped)

    if quiz.topic_id:
        update_topic_progress(user, quiz.topic)
    return response


def _store_counts(response, correct, incorrect, skipped):
    total = correct + incorrect + skipped
    response.correct_count = correct
    response.incorrect_count = incorrect
    response.skipped_count = skipped
    response.score = round(correct / total * 100, 1) if total else 0
    response.save(update_fields=['correct_count', 'incorrect_count', 'skipped_count', 'score'])


def _bucket(is_correct):
    return {True: 'correct', False: 'incorrect'}.get(is_correct, 'skipped')


@transaction.atomic
def apply_manual_grade(detail, is_correct, feedback=''):
    """Teacher decision on a short/essay answer; keeps the response totals in sync."""
    detail = ResponseDetails.objects.select_for_update().select_related('response').get(pk=detail.pk)
    response = Response.objects.select_for_update().get(pk=detail.response_id)

    counts = {
        'correct': response.correct_count,
        'incorrect': response.incorrect_count,
        'skipped': response.skipped_count,
    }
    old, new = _bucket(detail.is_correct), _bucket(is_correct)
    if old != new:
        counts[old] = max(0, counts[old] - 1)
        counts[new] += 1

    detail.is_correct = is_correct
    detail.feedback = (feedback or '').strip()
    detail.save(update_fields=['is_correct', 'feedback'])
    _store_counts(response, counts['correct'], counts['incorrect'], counts['skipped'])

    if response.quiz_id and response.quiz.topic_id:
        update_topic_progress(response.user, response.quiz.topic)
    return response


def pending_text_answers():
    """Short/essay answers that no teacher has checked yet."""
    return (
        ResponseDetails.objects
        .filter(question__type__in=TEXT_TYPES, is_correct__isnull=True,
                user_text_answer__isnull=False)
        .exclude(user_text_answer='')
    )


def update_topic_progress(user, topic):
    """Recompute a user's TopicProgress from their quiz results.

    * not_started - no quiz of the topic attempted yet
    * in_progress - something attempted, but not every quiz passed
    * completed   - every quiz of the topic passed (best score >= PASS_SCORE)
    ``progress`` is the share of the topic's quizzes already passed (0-100).
    Topics without quizzes are completed manually by the student instead.
    """
    quiz_ids = list(Quiz.objects.filter(topic=topic).values_list('id', flat=True))
    if not quiz_ids:
        return None

    best_scores = dict(
        Response.objects
        .filter(user=user, quiz_id__in=quiz_ids)
        .values('quiz_id')
        .annotate(best=Max('score'))
        .values_list('quiz_id', 'best')
    )
    attempted = len(best_scores)
    passed = sum(1 for s in best_scores.values() if s is not None and s >= PASS_SCORE)
    total = len(quiz_ids)

    if attempted == 0:
        status = 'not_started'
    elif passed >= total:
        status = 'completed'
    else:
        status = 'in_progress'
    progress = round(passed / total * 100)

    return set_topic_progress(user, topic, status, progress)


def progress_percent(progress):
    """0-100 for a TopicProgress row (None = not started)."""
    if progress is None:
        return 0
    if progress.status == 'completed':
        return 100
    return max(0, min(100, round(progress.progress or 0)))


def set_topic_progress(user, topic, status, progress):
    """Create/update the single TopicProgress row (and drop accidental duplicates)."""
    rows = TopicProgress.objects.filter(user=user, topic=topic).order_by('id')
    obj = rows.first()
    if obj is None:
        return TopicProgress.objects.create(user=user, topic=topic, status=status, progress=progress)
    rows.exclude(pk=obj.pk).delete()
    if obj.status != status or obj.progress != progress:
        obj.status, obj.progress = status, progress
        obj.save(update_fields=['status', 'progress'])
    return obj


def build_result_rows(response):
    """Rows for the 'answers' page: one per question, in the order they were saved."""
    details = (
        ResponseDetails.objects
        .filter(response=response)
        .select_related('question', 'question_choice')
        .prefetch_related(Prefetch(
            'question__questionchoice_set',
            queryset=QuestionChoice.objects.order_by('id'),
        ))
        .order_by('id')
    )
    rows = {}
    for d in details:
        key = d.question_id if d.question_id else f'deleted-{d.pk}'
        row = rows.get(key)
        if row is None:
            q = d.question
            choices = _choices_of(q) if q else []
            row = rows[key] = {
                'question': q,
                'deleted': q is None,
                'type': q.type if q else None,
                'is_correct': d.is_correct,
                'user_choices': [],
                'user_choice_ids': set(),
                'user_text': d.user_text_answer,
                'correct_answers': [c.choice_text for c in choices if c.is_correct],
                'correct_ids': {c.pk for c in choices if c.is_correct},
                'feedback': d.feedback,
                'detail_id': d.pk,
                'pending': False,
            }
        if d.question_choice_id and d.question_choice:
            row['user_choices'].append(d.question_choice.choice_text)
            row['user_choice_ids'].add(d.question_choice_id)

    for row in rows.values():
        q = row['question']
        if q is None:
            continue
        # Older submissions stored true/false as text and never set is_correct.
        if q.type == 'tf' and not row['user_choices'] and row['user_text'] in ('true', 'false'):
            choice = _resolve_single_choice(q, row['user_text'])
            row['user_choices'] = [choice.choice_text if choice else tf_label(row['user_text'])]
            if row['is_correct'] is None:
                row['is_correct'] = bool(choice and choice.is_correct)
        elif q.type == 'ms' and row['is_correct'] is None and row['user_choice_ids']:
            row['is_correct'] = row['user_choice_ids'] == row['correct_ids']
        elif q.type in TEXT_TYPES:
            row['pending'] = row['is_correct'] is None and bool(row['user_text'])
    for row in rows.values():
        row['state'] = 'pending' if row['pending'] else _bucket(row['is_correct'])
    return list(rows.values())


def regrade_legacy_response(response):
    """Fix a response saved by the old grader (true/false always marked wrong,
    multi-select rows without is_correct). Returns True when something changed."""
    changed = False
    correct, incorrect, skipped = (
        response.correct_count, response.incorrect_count, response.skipped_count,
    )
    for row in build_result_rows(response):
        q = row['question']
        if q is None or row['is_correct'] is None:
            continue
        rows = ResponseDetails.objects.filter(response=response, question=q)
        stored = set(rows.values_list('is_correct', flat=True))
        if stored == {row['is_correct']}:
            continue
        if q.type == 'tf' and row['is_correct'] is True and stored == {None}:
            # The old grader counted this answer as incorrect.
            correct, incorrect = correct + 1, max(0, incorrect - 1)
        rows.update(is_correct=row['is_correct'])
        changed = True
    if changed:
        _store_counts(response, correct, incorrect, skipped)
    return changed


__all__ = [
    'PASS_SCORE', 'CHOICE_TYPES', 'TEXT_TYPES', 'TF_TRUE_LABEL', 'TF_FALSE_LABEL',
    'tf_choice_value', 'tf_value_from_text', 'tf_label', 'quiz_questions_for', 'grade_submission',
    'apply_manual_grade', 'pending_text_answers', 'update_topic_progress',
    'set_topic_progress', 'progress_percent', 'build_result_rows', 'regrade_legacy_response',
]
