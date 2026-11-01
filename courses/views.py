import csv
import json
import re
import time
import uuid
from collections import Counter
from datetime import datetime

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Avg, Count, Prefetch, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from user.permissions import (
    NO_ACCESS_MESSAGE, admin_required, can_grade, can_moderate, get_profile,
    grader_required, is_admin, require_profile, safe_next_url,
)

from .grading import (
    PASS_SCORE, TEXT_TYPES, TF_FALSE_LABEL, TF_TRUE_LABEL, apply_manual_grade,
    build_result_rows, grade_submission, pending_text_answers, progress_percent,
    quiz_questions_for, set_topic_progress, tf_choice_value, tf_value_from_text,
    update_topic_progress,
)
from .models import (
    Forum, ForumComment, Question, QuestionChoice, Quiz, QuizQuestion, Response,
    ResponseDetails, Topic, TopicComment, TopicProgress, TopicSection, TopicSectionItem,
)

LOGIN_URL = 'user:login'
MAX_TEXT_LENGTH = 5000          # comments, forum posts, teacher feedback
MAX_TITLE_LENGTH = 255
UZ_MONTHS = ['Yanvar', 'Fevral', 'Mart', 'Aprel', 'May', 'Iyun',
             'Iyul', 'Avgust', 'Sentabr', 'Oktabr', 'Noyabr', 'Dekabr']


# ── Small helpers ─────────────────────────────────────────────────────────────

def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _vote_sets(user, model, objects):
    """(liked_ids, disliked_ids) of ``user`` for the given objects."""
    if not user.is_authenticated or not objects:
        return set(), set()
    ids = [obj.pk for obj in objects]
    liked = set(model.likes.through.objects.filter(
        user_id=user.pk, **{f'{model._meta.model_name}_id__in': ids},
    ).values_list(f'{model._meta.model_name}_id', flat=True))
    disliked = set(model.dislikes.through.objects.filter(
        user_id=user.pk, **{f'{model._meta.model_name}_id__in': ids},
    ).values_list(f'{model._meta.model_name}_id', flat=True))
    return liked, disliked


def _toggle_vote(obj, user, action):
    """Like/dislike toggle shared by forums, forum comments and topic comments."""
    liked = obj.likes.filter(pk=user.pk).exists()
    disliked = obj.dislikes.filter(pk=user.pk).exists()
    if action == 'like':
        if liked:
            obj.likes.remove(user)
            liked = False
        else:
            obj.likes.add(user)
            obj.dislikes.remove(user)
            liked, disliked = True, False
    elif action == 'dislike':
        if disliked:
            obj.dislikes.remove(user)
            disliked = False
        else:
            obj.dislikes.add(user)
            obj.likes.remove(user)
            liked, disliked = False, True
    return {
        'likes': obj.likes.count(),
        'dislikes': obj.dislikes.count(),
        'liked': liked,
        'disliked': disliked,
    }


def _querystring_without(request, *keys):
    params = request.GET.copy()
    for key in keys:
        params.pop(key, None)
    return params.urlencode()


# ── Dashboard ─────────────────────────────────────────────────────────────────

def index(request):
    total_topics = Topic.objects.count()
    total_quizzes = Quiz.objects.count()
    total_users = User.objects.filter(userprofile__isnull=False).count()

    response_stats = Response.objects.aggregate(
        total=Count('id'),
        avg=Avg('score'),
        active=Count('user', distinct=True),
        a=Count('id', filter=Q(score__gte=90)),
        b=Count('id', filter=Q(score__gte=70, score__lt=90)),
        c=Count('id', filter=Q(score__gte=50, score__lt=70)),
        d=Count('id', filter=Q(score__lt=50)),
    )
    progress_stats = TopicProgress.objects.aggregate(
        total=Count('id'), done=Count('id', filter=Q(status='completed')),
    )
    completion_rate = (
        round(progress_stats['done'] / progress_stats['total'] * 100)
        if progress_stats['total'] else 0
    )

    # New members per month for the last 7 months (one query, grouped in Python).
    now = timezone.now()
    months = []
    for i in range(6, -1, -1):
        month = (now.month - i - 1) % 12 + 1
        year = now.year + (now.month - i - 1) // 12
        months.append((year, month))
    start = datetime(months[0][0], months[0][1], 1)
    if settings.USE_TZ:
        start = timezone.make_aware(start)
    signups = dict.fromkeys(months, 0)
    for joined in User.objects.filter(date_joined__gte=start).values_list('date_joined', flat=True):
        key = (joined.year, joined.month)
        if key in signups:
            signups[key] += 1
    monthly_labels = [UZ_MONTHS[m - 1] for _, m in months]
    monthly_signups = [signups[key] for key in months]

    topics = Topic.objects.annotate(avg_score=Avg('quiz__response__score')).order_by('created_at')
    topic_labels = [t.title if len(t.title) <= 24 else t.title[:22] + '…' for t in topics]
    topic_avg_scores = [round(t.avg_score or 0) for t in topics]

    top_students = (
        Response.objects
        .values('user__first_name', 'user__last_name', 'user__id')
        .annotate(avg=Avg('score'), count=Count('id'))
        .order_by('-avg', '-count')[:5]
    )
    recent_responses = (
        Response.objects.select_related('user', 'quiz').order_by('-created_date_time')[:8]
    )

    return render(request, "courses/index.html", {
        # Stats
        'total_topics':         total_topics,
        'total_quizzes':        total_quizzes,
        'total_users':          total_users,
        'active_users':         response_stats['active'],
        'total_responses':      response_stats['total'],
        'avg_platform_score':   round(response_stats['avg'] or 0),
        'completion_rate':      completion_rate,
        'total_forum_posts':    Forum.objects.count(),
        'total_forum_comments': ForumComment.objects.count(),
        # Charts
        'monthly_labels':       monthly_labels,
        'monthly_signups':      monthly_signups,
        'score_a': response_stats['a'], 'score_b': response_stats['b'],
        'score_c': response_stats['c'], 'score_d': response_stats['d'],
        'topic_labels':         topic_labels,
        'topic_avg_scores':     topic_avg_scores,
        # Tables
        'top_students':         top_students,
        'recent_responses':     recent_responses,
    })


@login_required(login_url=LOGIN_URL)
@require_profile
@admin_required
def report_csv_view(request):
    """'Hisobot olish' — all quiz results as a CSV file (opens in Excel)."""
    def cell(value):
        text = '' if value is None else str(value)
        # Stop spreadsheet apps from treating user text as a formula.
        return "'" + text if text[:1] in ('=', '+', '-', '@') else text

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = (
        f'attachment; filename="edumed_natijalar_{timezone.now():%Y%m%d}.csv"'
    )
    response.write('﻿')  # BOM: Excel then reads the file as UTF-8
    writer = csv.writer(response)
    writer.writerow([
        'Sana', 'Talaba', 'Email', 'Viloyat', "Ta'lim muassasasi", 'Test', 'Mavzu',
        'Ball (%)', "To'g'ri", "Noto'g'ri", 'Belgilanmagan', 'Qoidabuzarlik',
    ])
    rows = (
        Response.objects
        .select_related('user', 'user__userprofile', 'quiz', 'quiz__topic')
        .order_by('-created_date_time')
    )
    for r in rows.iterator(chunk_size=500):
        profile = getattr(r.user, 'userprofile', None)
        writer.writerow([cell(v) for v in (
            r.created_date_time.strftime('%Y-%m-%d %H:%M'),
            r.user.get_full_name() or r.user.username,
            r.user.email,
            profile.region if profile else '',
            profile.otm if profile else '',
            r.quiz.title if r.quiz else "(o'chirilgan test)",
            r.quiz.topic.title if r.quiz and r.quiz.topic else 'Umumiy',
            r.score, r.correct_count, r.incorrect_count, r.skipped_count, r.violation_count,
        )])
    return response


# ── Search ────────────────────────────────────────────────────────────────────

def search_view(request):
    query = (request.GET.get('q') or '').strip()[:100]
    topics = quizzes = forums = questions = []
    if len(query) >= 2:
        topics = list(
            Topic.objects
            .filter(Q(title__icontains=query) | Q(description__icontains=query)
                    | Q(sections__title__icontains=query)
                    | Q(sections__items__text__icontains=query))
            .distinct().order_by('created_at')[:20]
        )
        quizzes = list(
            Quiz.objects
            .filter(Q(title__icontains=query) | Q(description__icontains=query))
            .select_related('topic')
            .annotate(question_count=Count('quizquestion', distinct=True))
            .filter(question_count__gt=0)
            .order_by('-created_at')[:20]
        )
        forums = list(
            Forum.objects
            .filter(Q(title__icontains=query) | Q(forum_question__icontains=query))
            .select_related('user', 'topic').order_by('-created_at')[:20]
        )
        if is_admin(request.user):
            questions = list(
                Question.objects.filter(question_text__icontains=query).order_by('-created_at')[:20]
            )
    return render(request, 'courses/search.html', {
        'search_query': query,
        'topics': topics,
        'quizzes': quizzes,
        'forums': forums,
        'questions': questions,
        'total_found': len(topics) + len(quizzes) + len(forums) + len(questions),
    })


# ── Topics ────────────────────────────────────────────────────────────────────

@login_required(login_url=LOGIN_URL)
@require_profile
def topics_view(request):
    topics = list(
        Topic.objects.annotate(quiz_count=Count('quiz', distinct=True)).order_by('created_at')
    )

    # ── Per-topic progress map {topic_id: TopicProgress} ──────────────
    progress_map = {}
    for p in TopicProgress.objects.filter(user=request.user).order_by('id'):
        progress_map.setdefault(p.topic_id, p)

    # ── Stats ─────────────────────────────────────────────────────────
    total_topics = len(topics)
    completed_count = sum(
        1 for t in topics if progress_map.get(t.id) and progress_map[t.id].status == 'completed'
    )
    overall_progress = (
        round(sum(progress_percent(progress_map.get(t.id)) for t in topics) / total_topics)
        if total_topics else 0
    )
    quiz_stats = Response.objects.filter(user=request.user).aggregate(
        avg=Avg('score'), count=Count('id'),
    )

    return render(request, "courses/topics.html", {
        "topics":           topics,
        "progress_map":     progress_map,
        "total_topics":     total_topics,
        "completed_count":  completed_count,
        "overall_progress": overall_progress,
        "avg_score":        round(quiz_stats['avg'] or 0),
        "quiz_count":       quiz_stats['count'],
    })


def _reading_minutes(topic, sections):
    words = len((topic.description or '').split())
    for section in sections:
        words += len((section.title or '').split())
        for item in section.items.all():
            words += len(item.text.split()) + len(item.sub_text.split()) + len(item.label.split())
    return max(1, round(words / 180))


@login_required(login_url=LOGIN_URL)
def topic_detail(request, topic_id):
    topic = get_object_or_404(Topic, pk=topic_id)
    topic_url = reverse('courses:topic', args=[topic.id])

    if request.method == 'POST':
        text = (request.POST.get('comment_text') or '').strip()
        if not get_profile(request.user):
            messages.error(request, "Izoh qoldirish uchun profil kerak.")
        elif not text:
            messages.error(request, "Izoh matni bo'sh bo'lmasligi kerak.")
        elif len(text) > MAX_TEXT_LENGTH:
            messages.error(request, f"Izoh {MAX_TEXT_LENGTH} belgidan oshmasligi kerak.")
        else:
            TopicComment.objects.create(user=request.user, topic=topic, text=text)
            messages.success(request, "Fikringiz muvaffaqiyatli qo'shildi!")
        return redirect(topic_url + '#comments')

    sections = list(topic.sections.prefetch_related('items'))
    comments = list(
        TopicComment.objects
        .filter(topic=topic)
        .select_related('user', 'user__userprofile')
        .annotate(n_likes=Count('likes', distinct=True), n_dislikes=Count('dislikes', distinct=True))
        .order_by('-created_at')
    )
    liked_ids, disliked_ids = _vote_sets(request.user, TopicComment, comments)
    progress = TopicProgress.objects.filter(user=request.user, topic=topic).order_by('id').first()

    # ── Quizzes of the topic with the user's best attempt ─────────────
    quizzes = list(
        Quiz.objects.filter(topic=topic)
        .annotate(question_count=Count('quizquestion', distinct=True))
        .order_by('created_at', 'id')
    )
    best_by_quiz, attempts = {}, Counter()
    for r in (Response.objects.filter(user=request.user, quiz__in=quizzes)
              .order_by('-score', '-created_date_time')):
        attempts[r.quiz_id] += 1
        best_by_quiz.setdefault(r.quiz_id, r)
    quiz_data = []
    for quiz in quizzes:
        best = best_by_quiz.get(quiz.id)
        quiz_data.append({
            'quiz':           quiz,
            'best':           best,          # None if never attempted
            'attempted':      best is not None,
            'attempts':       attempts[quiz.id],
            'passed':         bool(best and best.score >= PASS_SCORE),
            'question_count': quiz.question_count,
        })

    return render(request, 'courses/topic_detail.html', {
        'topic':          topic,
        'topic_id':       topic.id,
        'sections':       sections,
        'toc':            [(i, s.title) for i, s in enumerate(sections, 1) if s.title],
        'quiz_data':      quiz_data,
        'has_quizzes':    bool(quizzes),
        'comments':       comments,
        'liked_ids':      liked_ids,
        'disliked_ids':   disliked_ids,
        'progress':       progress,
        'progress_pct':   progress_percent(progress),
        'pass_score':     PASS_SCORE,
        'reading_minutes': _reading_minutes(topic, sections),
    })


@login_required(login_url=LOGIN_URL)
@require_POST
def like_comment(request, comment_id):
    """No-JS fallback for liking a topic comment (the page uses AJAX voting)."""
    comment = get_object_or_404(TopicComment, id=comment_id)
    _toggle_vote(comment, request.user, request.POST.get('action', 'like'))
    return redirect(reverse('courses:topic', args=[comment.topic_id]) + f'#comment-{comment.id}')


@login_required(login_url=LOGIN_URL)
@require_POST
def delete_topic_comment_view(request, comment_id):
    comment = get_object_or_404(TopicComment, pk=comment_id)
    if comment.user_id != request.user.id and not can_moderate(request.user):
        messages.error(request, NO_ACCESS_MESSAGE)
    else:
        comment.delete()
        messages.success(request, "Izoh o'chirildi.")
    return redirect(reverse('courses:topic', args=[comment.topic_id]) + '#comments')


@login_required(login_url=LOGIN_URL)
@require_profile
@require_POST
def update_progress_view(request, topic_id):
    """Topics without quizzes are marked as read by the student; for the others
    the progress always comes from quiz results."""
    topic = get_object_or_404(Topic, pk=topic_id)
    if Quiz.objects.filter(topic=topic).exists():
        update_topic_progress(request.user, topic)
        messages.info(request, "Bu mavzu bo'yicha o'zlashtirish test natijalari asosida hisoblanadi.")
    else:
        status = request.POST.get('status')
        if status == 'completed':
            set_topic_progress(request.user, topic, 'completed', 100)
            messages.success(request, "Mavzu o'qib chiqilgan deb belgilandi.")
        elif status == 'not_started':
            set_topic_progress(request.user, topic, 'not_started', 0)
            messages.info(request, "Belgi olib tashlandi.")
    return redirect('courses:topic', topic_id=topic.id)


# ── Shared helper: block type descriptions for the template ──
BLOCK_TYPES = [
    ('text',      'Matn',              'fa-align-left',    'Oddiy paragraf matni'),
    ('quote',     'Iqtibos',           'fa-quote-left',    'Muallifga havola bilan iqtibos'),
    ('keypoints', 'Asosiy nuqtalar',   'fa-star',          'Belgilangan muhim fikrlar ro\'yxati'),
    ('timeline',  "Vaqt chizig'i",     'fa-history',       'Sana va tarix ketma-ketligi'),
    ('person',    'Shaxs',             'fa-user-circle',   'Muallif, olim yoki tarixiy shaxs'),
    ('info',      "Ma'lumot bloki",    'fa-info-circle',   'Izohli ma\'lumot yoki eslatma'),
]
VALID_SECTION_TYPES = {code for code, _ in TopicSection.TYPE_CHOICES}
ICON_RE = re.compile(r'^[a-z0-9 -]{1,50}$')


def _clean_icon(value):
    value = (value or '').strip().lower()
    return value if ICON_RE.match(value) else 'fa-book'


def _build_sections_data(topic):
    """Serialize a topic's sections+items to a Python list (for JS pre-load)."""
    return [
        {
            'type':  section.type,
            'title': section.title,
            'order': section.order,
            'items': [
                {
                    'text':     item.text,
                    'sub_text': item.sub_text,
                    'label':    item.label,
                    'order':    item.order,
                }
                for item in section.items.all()
            ],
        }
        for section in topic.sections.prefetch_related('items')
    ]


def _save_sections(topic, sections_json_str):
    """Replace the topic's sections with the posted JSON.

    Returns False (and keeps the existing content) when the payload is missing or
    broken — e.g. the page's JavaScript failed — instead of wiping the topic.
    """
    if sections_json_str is None or not str(sections_json_str).strip():
        return False
    try:
        sections_data = json.loads(sections_json_str)
    except ValueError:
        return False
    if not isinstance(sections_data, list):
        return False

    with transaction.atomic():
        topic.sections.all().delete()  # cascade deletes items too
        for s_idx, section_data in enumerate(sections_data):
            if not isinstance(section_data, dict):
                continue
            items = []
            raw_items = section_data.get('items')
            for i_idx, item_data in enumerate(raw_items if isinstance(raw_items, list) else []):
                if not isinstance(item_data, dict):
                    continue
                text = str(item_data.get('text') or '').strip()
                sub_text = str(item_data.get('sub_text') or '').strip()
                label = str(item_data.get('label') or '').strip()[:100]
                if text or sub_text or label:  # skip completely empty items
                    items.append((text, sub_text, label, _int(item_data.get('order'), i_idx)))
            title = str(section_data.get('title') or '').strip()[:255]
            if not items and not title:
                continue
            stype = section_data.get('type')
            section = TopicSection.objects.create(
                topic=topic,
                type=stype if stype in VALID_SECTION_TYPES else 'text',
                title=title,
                order=_int(section_data.get('order'), s_idx),
            )
            TopicSectionItem.objects.bulk_create([
                TopicSectionItem(section=section, text=t, sub_text=s, label=l, order=o)
                for t, s, l, o in items
            ])
    return True


# ── Create ────────────────────────────────────────────────────
@login_required(login_url=LOGIN_URL)
@require_profile
@admin_required
def create_topic_view(request):
    if request.method == 'POST':
        title = (request.POST.get('title') or '').strip()
        if not title:
            messages.error(request, "Mavzu nomi kiritilishi shart!")
            return redirect('courses:create_topic')

        with transaction.atomic():
            topic = Topic.objects.create(
                title=title,
                description=(request.POST.get('description') or '').strip(),
                icon=_clean_icon(request.POST.get('icon')),
                created_by=request.user,
            )
            _save_sections(topic, request.POST.get('sections_json'))

        messages.success(request, f"'{topic.title}' mavzusi muvaffaqiyatli yaratildi!")
        return redirect('courses:topic', topic_id=topic.id)

    return render(request, 'courses/topic_form.html', {
        'topic':         None,
        'sections_data': [],
        'block_types':   BLOCK_TYPES,
    })


# ── Edit ──────────────────────────────────────────────────────
@login_required(login_url=LOGIN_URL)
@require_profile
@admin_required
def edit_topic_view(request, topic_id):
    topic = get_object_or_404(Topic, pk=topic_id)

    if request.method == 'POST':
        title = (request.POST.get('title') or '').strip()
        if not title:
            messages.error(request, "Mavzu nomi kiritilishi shart!")
            return redirect('courses:edit_topic', topic_id=topic.id)

        with transaction.atomic():
            topic.title = title
            topic.description = (request.POST.get('description') or '').strip()
            topic.icon = _clean_icon(request.POST.get('icon'))
            topic.save()
            saved = _save_sections(topic, request.POST.get('sections_json'))

        if saved:
            messages.success(request, "Mavzu muvaffaqiyatli saqlandi!")
        else:
            messages.warning(request, "Mavzu ma'lumotlari saqlandi, kontent bloklari esa o'zgarmadi.")
        return redirect('courses:edit_topic', topic_id=topic.id)

    return render(request, 'courses/topic_form.html', {
        'topic':         topic,
        'sections_data': _build_sections_data(topic),
        'block_types':   BLOCK_TYPES,
    })


# ── Delete ────────────────────────────────────────────────────
@login_required(login_url=LOGIN_URL)
@require_profile
@admin_required
@require_POST
def delete_topic_view(request, topic_id):
    topic = get_object_or_404(Topic, pk=topic_id)
    title = topic.title
    topic.delete()
    messages.success(request, f"'{title}' mavzusi o'chirildi")
    return redirect('courses:topics')


# ── Questions (admin) ─────────────────────────────────────────────────────────

QUESTION_TYPES = {code for code, _ in Question.TYPE_CHOICES}
CHOICE_FIELD_RE = re.compile(r'^choice_text_(\d+)$')


def _parse_question_form(post):
    """Read the question editor form. Returns (data, errors)."""
    text = (post.get('question_text') or '').strip()
    qtype = post.get('type')
    tf_answer = post.get('tf_answer')
    correct_marks = set(post.getlist('correct_choice'))

    rows = []
    for key in post.keys():
        match = CHOICE_FIELD_RE.match(key)
        if not match:
            continue
        idx = match.group(1)
        choice_text = (post.get(key) or '').strip()
        if not choice_text:
            continue
        raw_id = post.get(f'choice_id_{idx}') or ''
        rows.append({
            'idx': int(idx),
            'text': choice_text,
            'is_correct': idx in correct_marks,
            'id': int(raw_id) if raw_id.isdigit() else None,
        })
    rows.sort(key=lambda r: r['idx'])

    errors = []
    if not text:
        errors.append("Savol matni kiritilishi shart.")
    if qtype not in QUESTION_TYPES:
        errors.append("Savol turini tanlang.")
    if qtype in ('mc', 'ms'):
        n_correct = sum(1 for r in rows if r['is_correct'])
        if len(rows) < 2:
            errors.append("Kamida 2 ta variant kiriting.")
        if qtype == 'mc' and n_correct != 1:
            errors.append("Bitta to'g'ri javobni belgilang.")
        if qtype == 'ms' and n_correct < 1:
            errors.append("Kamida bitta to'g'ri javobni belgilang.")
    elif qtype == 'tf' and tf_answer not in ('true', 'false'):
        errors.append("To'g'ri javobni tanlang: «To'g'ri» yoki «Noto'g'ri».")

    data = {'text': text, 'type': qtype, 'rows': rows, 'tf_answer': tf_answer}
    return data, errors


def _sync_choices(question, data):
    """Save the choices of a question *in place* so earlier student answers keep
    pointing at the same choice rows (re-creating them used to blank out
    'Sizning javobingiz' on old results)."""
    qtype = data['type']
    existing = list(question.questionchoice_set.order_by('id'))

    if qtype in TEXT_TYPES:
        question.questionchoice_set.all().delete()
        return

    if qtype == 'tf':
        want_true = data['tf_answer'] == 'true'
        values = [tf_value_from_text(c.choice_text) for c in existing]
        if len(existing) == 2 and set(values) == {'true', 'false'}:
            for choice, value in zip(existing, values):
                is_correct = (value == 'true') == want_true
                if choice.is_correct != is_correct:
                    choice.is_correct = is_correct
                    choice.save(update_fields=['is_correct'])
        else:
            question.questionchoice_set.all().delete()
            QuestionChoice.objects.create(question=question, choice_text=TF_TRUE_LABEL, is_correct=want_true)
            QuestionChoice.objects.create(question=question, choice_text=TF_FALSE_LABEL, is_correct=not want_true)
        return

    # mc / ms
    by_id = {c.pk: c for c in existing}
    keep = set()
    for row in data['rows']:
        choice = by_id.get(row['id'])
        if choice is not None and choice.pk not in keep:
            if choice.choice_text != row['text'] or choice.is_correct != row['is_correct']:
                choice.choice_text = row['text']
                choice.is_correct = row['is_correct']
                choice.save(update_fields=['choice_text', 'is_correct'])
        else:
            choice = QuestionChoice.objects.create(
                question=question, choice_text=row['text'], is_correct=row['is_correct'],
            )
        keep.add(choice.pk)
    question.questionchoice_set.exclude(pk__in=keep).delete()


def _question_init(question=None, data=None):
    """Initial state for the question editor's JavaScript."""
    if data is not None:
        return {
            'text': data['text'],
            'type': data['type'] if data['type'] in QUESTION_TYPES else 'mc',
            'tf_answer': data['tf_answer'] or '',
            'choices': [{'id': r['id'], 'text': r['text'], 'is_correct': r['is_correct']}
                        for r in data['rows']],
        }
    if question is None:
        return {'text': '', 'type': 'mc', 'tf_answer': '', 'choices': []}
    choices = list(question.questionchoice_set.order_by('id'))
    tf_answer = ''
    if question.type == 'tf':
        tf_answer = next(
            (tf_choice_value(c, i) for i, c in enumerate(choices) if c.is_correct), '',
        )
    return {
        'text': question.question_text,
        'type': question.type,
        'tf_answer': tf_answer,
        'choices': [] if question.type == 'tf' else [
            {'id': c.pk, 'text': c.choice_text or '', 'is_correct': c.is_correct} for c in choices
        ],
    }


def _recent_questions():
    return (
        Question.objects.order_by('-created_at')
        .prefetch_related(Prefetch('questionchoice_set', queryset=QuestionChoice.objects.order_by('id')))[:10]
    )


@login_required(login_url=LOGIN_URL)
@require_profile
@admin_required
def all_questions_view(request):
    questions = Question.objects.annotate(choice_count=Count('questionchoice')).order_by('-created_at')
    return render(request, "courses/all_questions.html", {
        'questions': questions,
    })


@login_required(login_url=LOGIN_URL)
@require_profile
@admin_required
def create_question_view(request):
    return render(request, "courses/question.html", {
        'questions': _recent_questions(),
        'init': _question_init(),
    })


@login_required(login_url=LOGIN_URL)
@require_profile
@admin_required
@require_POST
def save_question_view(request):
    data, errors = _parse_question_form(request.POST)
    if errors:
        for error in errors:
            messages.error(request, error)
        return render(request, "courses/question.html", {
            'questions': _recent_questions(),
            'init': _question_init(data=data),
        })

    with transaction.atomic():
        question = Question.objects.create(question_text=data['text'], type=data['type'])
        _sync_choices(question, data)
    messages.success(request, "Savol qo'shildi")
    return redirect('courses:add_question')


@login_required(login_url=LOGIN_URL)
@require_profile
@admin_required
def edit_question_view(request, question_id):
    question = get_object_or_404(Question, id=question_id)

    if request.method == 'POST':
        data, errors = _parse_question_form(request.POST)
        if errors:
            for error in errors:
                messages.error(request, error)
            return render(request, "courses/question.html", {
                'current_question': question,
                'questions': _recent_questions(),
                'init': _question_init(data=data),
            })
        with transaction.atomic():
            question.question_text = data['text']
            question.type = data['type']
            question.save()
            _sync_choices(question, data)
        messages.success(request, "Savol o'zgartirildi")
        return redirect("courses:edit_question", question.pk)

    return render(request, "courses/question.html", {
        'current_question': question,
        'questions': _recent_questions(),
        'init': _question_init(question),
    })


@login_required(login_url=LOGIN_URL)
@require_profile
@admin_required
@require_POST
def delete_question_view(request, question_id):
    question = get_object_or_404(Question, pk=question_id)
    question.delete()
    messages.success(request, "Savol o'chirildi")
    return redirect('courses:all_questions')


# ── Quizzes (admin) ───────────────────────────────────────────────────────────

def _parse_quiz_form(post):
    title = (post.get('title') or '').strip()
    qtype = post.get('type')
    errors = []
    if not title:
        errors.append("Test nomini kiriting.")
    if qtype not in ('1', '2'):
        errors.append("Test turini tanlang.")

    topic = None
    if qtype == '1':
        topic_id = str(post.get('topic') or '')
        topic = Topic.objects.filter(pk=topic_id).first() if topic_id.isdigit() else None
        if topic is None:
            errors.append("Mavzuga biriktirilgan test uchun mavzuni tanlang.")

    duration = max(1, min(_int(post.get('duration'), 15), 300))

    ids = []
    for raw in post.getlist('question_ids'):
        raw = str(raw)
        if raw.isdigit() and int(raw) not in ids:
            ids.append(int(raw))
    existing = set(Question.objects.filter(pk__in=ids).values_list('pk', flat=True))
    ids = [pk for pk in ids if pk in existing]
    if not ids:
        errors.append("Savollar tanlanmagan")

    return {
        'title': title, 'type': qtype, 'topic': topic, 'duration': duration,
        'description': (post.get('description') or '').strip(), 'question_ids': ids,
    }, errors


def _save_quiz_questions(quiz, question_ids):
    quiz.quizquestion_set.all().delete()
    QuizQuestion.objects.bulk_create([
        QuizQuestion(quiz=quiz, question_id=pk, order=position)
        for position, pk in enumerate(question_ids, start=1)
    ])


@login_required(login_url=LOGIN_URL)
@require_profile
@admin_required
def all_quizzes_view(request):
    quizzes = (
        Quiz.objects.select_related('topic')
        .annotate(question_count=Count('quizquestion', distinct=True),
                  attempt_count=Count('response', distinct=True))
        .order_by('-id')
    )
    return render(request, 'courses/all_quizzes.html', {'quizzes': quizzes})


def _quiz_form_context(quiz=None):
    questions = list(Question.objects.order_by('-created_at'))
    return {
        'current_quiz': quiz,
        'questions': questions,
        'question_data': [
            {'id': q.pk, 'text': q.question_text, 'type': q.type, 'typeDisplay': q.get_type_display()}
            for q in questions
        ],
        'topics': Topic.objects.order_by('created_at'),
        'selected_ids': list(
            quiz.quizquestion_set.order_by('order', 'id').values_list('question_id', flat=True)
        ) if quiz else [],
    }


@login_required(login_url=LOGIN_URL)
@require_profile
@admin_required
def create_quiz_view(request):
    return render(request, "courses/quiz.html", _quiz_form_context())


@login_required(login_url=LOGIN_URL)
@require_profile
@admin_required
@require_POST
def save_quiz_view(request):
    data, errors = _parse_quiz_form(request.POST)
    if errors:
        for error in errors:
            messages.error(request, error)
        return redirect("courses:add_quiz")

    with transaction.atomic():
        quiz = Quiz.objects.create(
            title=data['title'], type=data['type'], topic=data['topic'],
            description=data['description'], duration=data['duration'],
        )
        _save_quiz_questions(quiz, data['question_ids'])
    messages.success(request, "Topshiriq muvaffaqiyatli yaratildi")
    return redirect("courses:add_quiz")


@login_required(login_url=LOGIN_URL)
@require_profile
@admin_required
def edit_quiz_view(request, quiz_id):
    quiz = get_object_or_404(Quiz, pk=quiz_id)

    if request.method == 'POST':
        data, errors = _parse_quiz_form(request.POST)
        if errors:
            for error in errors:
                messages.error(request, error)
            return redirect("courses:edit_quiz", quiz.pk)

        with transaction.atomic():
            quiz.title = data['title']
            quiz.type = data['type']
            quiz.topic = data['topic']
            quiz.description = data['description']
            quiz.duration = data['duration']
            quiz.save()
            _save_quiz_questions(quiz, data['question_ids'])
        messages.success(request, "Topshiriq muvaffaqiyatli o'zgartirildi")
        return redirect("courses:edit_quiz", quiz.pk)

    return render(request, "courses/quiz.html", _quiz_form_context(quiz))


@login_required(login_url=LOGIN_URL)
@require_profile
@admin_required
@require_POST
def delete_quiz_view(request, quiz_id):
    quiz = get_object_or_404(Quiz, pk=quiz_id)
    title = quiz.title
    quiz.delete()
    messages.success(request, f"'{title}' testi o'chirildi")
    return redirect('courses:all_quizzes')


# ── Quizzes (students) ────────────────────────────────────────────────────────

@login_required(login_url=LOGIN_URL)
@require_profile
def quizzes_view(request):
    """'Topshiriqlar' — every quiz with the student's best result."""
    status = request.GET.get('status', 'all')
    quizzes = list(
        Quiz.objects.select_related('topic')
        .annotate(question_count=Count('quizquestion', distinct=True))
        .filter(question_count__gt=0)
        .order_by('created_at', 'id')
    )
    best_by_quiz, attempts = {}, Counter()
    for r in Response.objects.filter(user=request.user, quiz__isnull=False).order_by('-score', '-created_date_time'):
        attempts[r.quiz_id] += 1
        best_by_quiz.setdefault(r.quiz_id, r)

    items = []
    for quiz in quizzes:
        best = best_by_quiz.get(quiz.id)
        items.append({
            'quiz': quiz,
            'question_count': quiz.question_count,
            'best': best,
            'attempts': attempts[quiz.id],
            'passed': bool(best and best.score >= PASS_SCORE),
        })

    attempted = [i for i in items if i['best']]
    summary = {
        'total': len(items),
        'attempted': len(attempted),
        'passed': sum(1 for i in items if i['passed']),
        'avg_best': round(sum(i['best'].score for i in attempted) / len(attempted)) if attempted else 0,
    }
    if status == 'new':
        items = [i for i in items if not i['best']]
    elif status == 'done':
        items = [i for i in items if i['best']]

    general = [i for i in items if not i['quiz'].topic_id]
    by_topic = {}
    for i in sorted((i for i in items if i['quiz'].topic_id),
                    key=lambda i: (i['quiz'].topic.created_at, i['quiz'].topic_id)):
        by_topic.setdefault(i['quiz'].topic, []).append(i)

    return render(request, 'courses/quizzes.html', {
        'status': status,
        'general': general,
        'topic_groups': list(by_topic.items()),
        'summary': summary,
        'pass_score': PASS_SCORE,
        'has_items': bool(items),
    })


def _attempt_key(quiz_id):
    return f'quiz_attempt_{quiz_id}'


@login_required(login_url=LOGIN_URL)
@require_profile
def quiz_attempt(request, quiz_id):
    quiz = get_object_or_404(Quiz.objects.select_related('topic'), pk=quiz_id)
    questions = list(quiz_questions_for(quiz))
    if not questions:
        messages.warning(request, "Bu testda hali savollar yo'q.")
        if quiz.topic_id:
            return redirect('courses:topic', topic_id=quiz.topic_id)
        return redirect('courses:quizzes')

    # The attempt (start time, violations) lives in the session, so reloading the
    # page neither restarts the timer nor clears the violation counter.
    duration_seconds = max(1, quiz.duration or 15) * 60
    key = _attempt_key(quiz.pk)
    state = request.session.get(key)
    now = time.time()
    if not isinstance(state, dict) or now - float(state.get('started', 0)) >= duration_seconds:
        state = {'token': uuid.uuid4().hex, 'started': now, 'violations': 0}
        request.session[key] = state
    remaining = max(0, int(duration_seconds - (now - float(state['started']))))

    return render(request, 'courses/quiz_attempt.html', {
        'quiz': quiz,
        'questions': questions,
        'quiz_duration': duration_seconds // 60,  # minutes
        'remaining_seconds': remaining,
        'attempt_token': state['token'],
        'initial_violations': _int(state.get('violations'), 0),
        'autosave_key': f"edumed-quiz-{request.user.pk}-{quiz.pk}-{state['token']}",
    })


@login_required(login_url=LOGIN_URL)
@require_POST
def log_violation(request):
    """The browser reports anti-cheat violations; the count survives page reloads."""
    try:
        data = json.loads(request.body or b'{}')
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({'ok': False}, status=400)
    if not isinstance(data, dict):
        return JsonResponse({'ok': False}, status=400)
    key = _attempt_key(_int(data.get('quiz_id'), 0))
    state = request.session.get(key)
    count = data.get('count')
    if isinstance(state, dict) and isinstance(count, int) and 0 <= count <= 1000:
        state['violations'] = max(_int(state.get('violations'), 0), count)
        request.session[key] = state
    return JsonResponse({'ok': True})


@login_required(login_url=LOGIN_URL)
@require_profile
@require_POST
def submit_quiz(request, quiz_id):
    quiz = get_object_or_404(Quiz, pk=quiz_id)

    # A double click / resubmitted form must not create a second result.
    token = request.POST.get('attempt_token') or ''
    submitted = request.session.get('quiz_submitted') or {}
    if token and token in submitted:
        previous = Response.objects.filter(pk=submitted[token], user=request.user).first()
        if previous:
            return redirect('courses:score_view', response_id=previous.pk)

    key = _attempt_key(quiz.pk)
    state = request.session.get(key) or {}
    violations = max(_int(request.POST.get('violations'), 0), _int(state.get('violations'), 0))
    violations = max(0, min(violations, 1000))

    response = grade_submission(request.user, quiz, request.POST, violation_count=violations)

    request.session.pop(key, None)
    if token:
        submitted[token] = response.pk
        request.session['quiz_submitted'] = dict(list(submitted.items())[-10:])
    return redirect('courses:score_view', response_id=response.pk)


def _response_for_viewer(request, response_id):
    """The response if the user owns it or may grade it, else None."""
    response = get_object_or_404(
        Response.objects.select_related('quiz', 'quiz__topic', 'user'), pk=response_id,
    )
    if response.user_id == request.user.id or can_grade(request.user):
        return response
    return None


# it gets response_id from redirect above submit_quiz view
@login_required(login_url=LOGIN_URL)
@require_profile
def score_view(request, response_id):
    response = _response_for_viewer(request, response_id)
    if response is None:
        messages.error(request, NO_ACCESS_MESSAGE)
        return redirect('user:index')

    # just display how many +/-/ answers and score of student. POST -> SAVE -> GET method for security
    return render(request, 'courses/quiz_result.html', {
        'quiz': response.quiz,
        'response': response,
        'response_id': response.pk,
        'score': response.score,
        'correct_count': response.correct_count,
        'incorrect_count': response.incorrect_count,
        'skipped_count': response.skipped_count,
        'pending_count': pending_text_answers().filter(response=response).count(),
        'is_owner': response.user_id == request.user.id,
    })


@login_required(login_url=LOGIN_URL)
@require_profile
def score_details_view(request, response_id):
    # The old ?user=<id> parameter is no longer needed: owners and teachers/admins
    # may open a result, nobody else.
    response = _response_for_viewer(request, response_id)
    if response is None:
        messages.error(request, NO_ACCESS_MESSAGE)
        return redirect('user:index')

    quiz = response.quiz
    return render(request, 'courses/quiz_details.html', {
        'response':     response,
        'quiz':         quiz,
        'title':        quiz.title if quiz else "O'chirilgan test",
        'topic_id':     quiz.topic_id if quiz else None,
        'score':        response.score,
        'results':      build_result_rows(response),
        'student':      response.user,
        'is_owner':     response.user_id == request.user.id,
        'can_grade_here': can_grade(request.user),
    })


@login_required(login_url=LOGIN_URL)
@require_profile
@grader_required
@require_POST
def grade_answer_view(request, detail_id):
    """A teacher marks a short/essay answer as correct or incorrect."""
    detail = get_object_or_404(ResponseDetails.objects.select_related('question'), pk=detail_id)
    details_url = reverse('courses:score_details', args=[detail.response_id]) + f'#answer-{detail.pk}'
    if detail.question is None or detail.question.type not in TEXT_TYPES:
        messages.error(request, "Bu turdagi javob avtomatik baholanadi.")
        return redirect(details_url)
    verdict = request.POST.get('verdict')
    if verdict not in ('correct', 'incorrect'):
        messages.error(request, "Bahoni tanlang.")
        return redirect(details_url)

    apply_manual_grade(detail, verdict == 'correct', (request.POST.get('feedback') or '')[:MAX_TEXT_LENGTH])
    messages.success(request, "Baho saqlandi, test natijasi qayta hisoblandi.")
    return redirect(safe_next_url(request) or details_url)


@login_required(login_url=LOGIN_URL)
@require_profile
@grader_required
def grading_view(request):
    """Results that still contain unchecked short/essay answers (oldest first)."""
    pending_counts = dict(
        pending_text_answers().values('response_id').annotate(n=Count('id')).values_list('response_id', 'n')
    )
    responses = (
        Response.objects.filter(pk__in=list(pending_counts))
        .select_related('user', 'quiz', 'quiz__topic')
        .order_by('created_date_time')
    )
    page = Paginator(responses, 25).get_page(request.GET.get('page'))
    for r in page:
        r.pending_count = pending_counts.get(r.pk, 0)

    recently_graded = (
        Response.objects.filter(
            responsedetails__question__type__in=TEXT_TYPES,
            responsedetails__is_correct__isnull=False,
        )
        .exclude(pk__in=list(pending_counts))
        .select_related('user', 'quiz').distinct().order_by('-created_date_time')[:10]
    )
    return render(request, 'courses/grading.html', {
        'page': page,
        'total_pending': sum(pending_counts.values()),
        'recently_graded': recently_graded,
    })


# ── Forums ────────────────────────────────────────────────────────────────────

def _forum_counts(queryset):
    return queryset.annotate(
        like_count=Count('likes', distinct=True),
        dislike_count=Count('dislikes', distinct=True),
        comment_count=Count('forumcomment', distinct=True),
    )


def all_forum_view(request):
    if request.method == "POST":
        if not request.user.is_authenticated:
            return redirect(f"{reverse(LOGIN_URL)}?next={reverse('courses:forums')}")
        if not get_profile(request.user):
            messages.error(request, "Forum ochish uchun profil kerak.")
            return redirect('courses:forums')
        title = (request.POST.get('title') or '').strip()
        forum_question = (request.POST.get('forum_question') or '').strip()
        if not (title and forum_question):
            messages.error(request, "Forum nomi va savol matni kiritilishi shart.")
            return redirect('courses:forums')
        if len(title) > MAX_TITLE_LENGTH or len(forum_question) > MAX_TEXT_LENGTH:
            messages.error(request, "Matn juda uzun.")
            return redirect('courses:forums')
        topic_id = str(request.POST.get('topic_id') or '')
        topic = Topic.objects.filter(pk=topic_id).first() if topic_id.isdigit() else None
        forum = Forum.objects.create(
            user=request.user, title=title,
            forum_question=forum_question, topic=topic,
        )
        messages.success(request, f"Forum #{forum.pk} muvaffaqiyatli yaratildi!")
        return redirect('courses:forum', forum.pk)

    # Filter
    topic_filter = request.GET.get('topic')
    q = (request.GET.get('q') or '').strip()
    forums = _forum_counts(Forum.objects.select_related('user', 'topic'))

    if topic_filter and topic_filter.isdecimal():
        forums = forums.filter(topic__id=topic_filter)
    elif topic_filter == 'general':
        forums = forums.filter(topic__isnull=True)

    if q:
        forums = forums.filter(Q(title__icontains=q) | Q(forum_question__icontains=q))

    # Sort
    sort = request.GET.get('sort', 'new')
    if sort == 'top':
        forums = forums.order_by('-like_count', '-created_at')
    elif sort == 'active':
        forums = forums.order_by('-comment_count', '-created_at')
    else:
        forums = forums.order_by('-created_at')

    # Paginate
    page = Paginator(forums, 10).get_page(request.GET.get('page'))
    liked_ids, disliked_ids = _vote_sets(request.user, Forum, list(page))

    topics = Topic.objects.annotate(forum_count=Count('forum')).order_by('-created_at')
    top_contributors = (
        ForumComment.objects
        .values('user__first_name', 'user__last_name', 'user__id')
        .annotate(comment_count=Count('id', distinct=True), like_count=Count('likes', distinct=True))
        .order_by('-comment_count', '-like_count')[:5]
    )

    return render(request, 'courses/forums.html', {
        'topics': topics,
        'forums': page,
        'liked_ids': liked_ids,
        'disliked_ids': disliked_ids,
        'top_contributors': top_contributors,
        'total_forums': Forum.objects.count(),
        'total_comments': ForumComment.objects.count(),
        'total_users': User.objects.filter(forumcomment__isnull=False).distinct().count(),
        'general_forum_count': Forum.objects.filter(topic__isnull=True).count(),
        'base_qs': _querystring_without(request, 'page'),
        'filter_qs': _querystring_without(request, 'page', 'topic'),
        'search_qs': _querystring_without(request, 'page', 'q'),
        'sort_qs': _querystring_without(request, 'page', 'sort'),
        'sort': sort,
    })


def forum_view(request, forum_id):
    forum = get_object_or_404(_forum_counts(Forum.objects.select_related('user', 'topic')), pk=forum_id)

    def comment_qs():
        return ForumComment.objects.select_related('user').annotate(
            like_count=Count('likes', distinct=True), dislike_count=Count('dislikes', distinct=True),
        )

    # Sort comments
    sort = request.GET.get('sort', 'new')
    comments = comment_qs().filter(forum=forum, parent=None).prefetch_related(
        Prefetch('replies', queryset=comment_qs().order_by('created_at'))
    )
    if sort == 'top':
        comments = comments.order_by('-like_count', '-created_at')
    else:
        comments = comments.order_by('-created_at')

    # Paginate
    page = Paginator(comments, 10).get_page(request.GET.get('page'))
    shown = list(page)
    for comment in list(shown):
        shown.extend(comment.replies.all())
    liked_ids, disliked_ids = _vote_sets(request.user, ForumComment, shown)
    forum_liked, forum_disliked = _vote_sets(request.user, Forum, [forum])

    top_contributors = (
        ForumComment.objects
        .filter(forum=forum)
        .values('user__first_name', 'user__last_name', 'user__id')
        .annotate(comment_count=Count('id', distinct=True), like_count=Count('likes', distinct=True))
        .order_by('-comment_count', '-like_count')[:5]
    )

    return render(request, 'courses/forum.html', {
        'forum': forum,
        'comments': page,
        'liked_ids': liked_ids,
        'disliked_ids': disliked_ids,
        'forum_liked': forum.pk in forum_liked,
        'forum_disliked': forum.pk in forum_disliked,
        'top_contributors': top_contributors,
        'can_moderate_forum': can_moderate(request.user),
        'sort': sort,
    })


@login_required(login_url=LOGIN_URL)
@require_profile
@require_POST
def post_comment_view(request, forum_id):
    forum = get_object_or_404(Forum, pk=forum_id)
    forum_url = reverse('courses:forum', args=[forum.pk])
    text = (request.POST.get('text') or '').strip()
    if not text:
        messages.error(request, "Izoh matni bo'sh bo'lmasligi kerak.")
        return redirect(forum_url)
    if len(text) > MAX_TEXT_LENGTH:
        messages.error(request, f"Izoh {MAX_TEXT_LENGTH} belgidan oshmasligi kerak.")
        return redirect(forum_url)

    parent = None
    parent_id = str(request.POST.get('comment_id') or '')
    if parent_id.isdigit():
        parent = ForumComment.objects.filter(pk=parent_id, forum=forum).select_related('parent').first()
        # Replies are shown one level deep, so answer the top-level comment.
        if parent is not None and parent.parent_id:
            parent = parent.parent

    forum_comment = ForumComment.objects.create(
        user=request.user,
        forum=forum,
        text=text,
        parent=parent,
    )
    messages.success(request, "Fikr muvaffaqiyatli qo'shildi!")
    return redirect(f'{forum_url}#comment-{forum_comment.pk}')


@login_required(login_url=LOGIN_URL)
@require_POST
def delete_forum_view(request, forum_id):
    forum = get_object_or_404(Forum, pk=forum_id)
    if forum.user_id != request.user.id and not can_moderate(request.user):
        messages.error(request, NO_ACCESS_MESSAGE)
        return redirect('courses:forum', forum.pk)
    forum.delete()
    messages.success(request, "Forum o'chirildi.")
    return redirect('courses:forums')


@login_required(login_url=LOGIN_URL)
@require_POST
def delete_forum_comment_view(request, comment_id):
    comment = get_object_or_404(ForumComment, pk=comment_id)
    if comment.user_id != request.user.id and not can_moderate(request.user):
        messages.error(request, NO_ACCESS_MESSAGE)
    else:
        comment.delete()  # replies are removed together with the comment
        messages.success(request, "Izoh o'chirildi.")
    return redirect(reverse('courses:forum', args=[comment.forum_id]) + '#comments')


VOTE_MODELS = {'forum': Forum, 'comment': ForumComment, 'tcomment': TopicComment}


@login_required(login_url=LOGIN_URL)
@require_POST
def toggle_vote_view(request):
    try:
        data = json.loads(request.body or b'{}')
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({'error': 'bad_request'}, status=400)
    if not isinstance(data, dict):
        return JsonResponse({'error': 'bad_request'}, status=400)

    model = VOTE_MODELS.get(data.get('type'))   # 'forum', 'comment' or 'tcomment'
    action = data.get('action')                 # 'like' or 'dislike'
    obj_id = _int(data.get('id'), 0)
    if model is None or action not in ('like', 'dislike') or obj_id <= 0:
        return JsonResponse({'error': 'bad_request'}, status=400)

    obj = get_object_or_404(model, pk=obj_id)
    return JsonResponse(_toggle_vote(obj, request.user, action))
