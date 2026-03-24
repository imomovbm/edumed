from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import TopicComment, Quiz, Question, QuizQuestion, Response, ResponseDetails, QuestionChoice, Topic, Forum, ForumComment, TopicProgress, TopicSection, TopicSectionItem
from django.contrib.auth.models import User
import json
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.db.models import Count, Avg
from functools import wraps
from django.core.paginator import Paginator
from datetime import date
from django.utils import timezone

def require_profile(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user_profile = getattr(request.user, 'userprofile', None)
        if not user_profile:
            return redirect('courses:index')
        return view_func(request, *args, **kwargs)
    return wrapper

def index(request):
    # ── Platform-wide stats ────────────────────────────────────────────
    total_topics    = Topic.objects.count()
    total_quizzes   = Quiz.objects.count()
    total_users     = User.objects.filter(userprofile__isnull=False).count()
    total_responses = Response.objects.count()

    # Active users = users who submitted at least one response
    active_users = Response.objects.values('user').distinct().count()

    # Average platform score
    avg_platform_score = round(
        Response.objects.aggregate(avg=Avg('score'))['avg'] or 0
    )

    # Completion rate: completed TopicProgress / all TopicProgress
    total_progress   = TopicProgress.objects.count()
    completed_count  = TopicProgress.objects.filter(status='completed').count()
    completion_rate  = round((completed_count / total_progress * 100) if total_progress else 0)

    # Forum activity
    total_forum_posts    = Forum.objects.count()
    total_forum_comments = ForumComment.objects.count()

    monthly_labels = []
    monthly_signups = []
    UZ_MONTHS = ['Yanvar','Fevral','Mart','Aprel','May','Iyun',
                 'Iyul','Avgust','Sentabr','Oktabr','Noyabr','Dekabr']
    now = timezone.now()
    for i in range(6, -1, -1):
        month = (now.month - i - 1) % 12 + 1
        year  = now.year + ((now.month - i - 1) // 12)
        count = User.objects.filter(
            date_joined__year=year,
            date_joined__month=month,
        ).count()
        monthly_labels.append(UZ_MONTHS[month - 1])
        monthly_signups.append(count)

    # ── Score distribution across all responses ────────────────────────
    score_a = Response.objects.filter(score__gte=90).count()
    score_b = Response.objects.filter(score__gte=70, score__lt=90).count()
    score_c = Response.objects.filter(score__gte=50, score__lt=70).count()
    score_d = Response.objects.filter(score__lt=50).count()

    # ── Per-topic average scores for radar ────────────────────────────
    topics = Topic.objects.order_by('created_at')
    topic_labels = []
    topic_avg_scores = []
    for topic in topics:
        avg = Response.objects.filter(quiz__topic=topic).aggregate(avg=Avg('score'))['avg'] or 0
        topic_labels.append(topic.title[:20])  # truncate for chart
        topic_avg_scores.append(round(avg))

    # ── Top 5 students by avg score ───────────────────────────────────
    top_students = (
        Response.objects
        .values('user__first_name', 'user__last_name', 'user__id')
        .annotate(avg=Avg('score'), count=Count('id'))
        .filter(count__gte=1)
        .order_by('-avg')[:5]
    )

    # ── Recent activity ───────────────────────────────────────────────
    recent_responses = Response.objects.select_related(
        'user', 'quiz'
    ).order_by('-created_date_time')[:8]
    print(monthly_signups)
    return render(request, "courses/index.html", {
        # Stats
        'total_topics':         total_topics,
        'total_quizzes':        total_quizzes,
        'total_users':          total_users,
        'active_users':         active_users,
        'total_responses':      total_responses,
        'avg_platform_score':   avg_platform_score,
        'completion_rate':      completion_rate,
        'total_forum_posts':    total_forum_posts,
        'total_forum_comments': total_forum_comments,
        # Charts
        'monthly_labels':       monthly_labels,
        'monthly_signups':      monthly_signups,
        'score_a': score_a, 'score_b': score_b,
        'score_c': score_c, 'score_d': score_d,
        'topic_labels':         topic_labels,
        'topic_avg_scores':     topic_avg_scores,
        # Tables
        'top_students':         top_students,
        'recent_responses':     recent_responses,
    })

@login_required(login_url='user:login')
@require_profile
def topics_view(request):
    topics = Topic.objects.order_by('created_at')

    # ── Per-topic progress map {topic_id: TopicProgress} ──────────────
    user_progresses = TopicProgress.objects.filter(user=request.user)
    progress_map = {p.topic_id: p for p in user_progresses}

    # ── Stats ─────────────────────────────────────────────────────────
    total_topics    = topics.count()
    completed_count = user_progresses.filter(status='completed').count()
    in_progress_count = user_progresses.filter(status='in_progress').count()

    # Overall progress % — weight completed=100, in_progress=50, rest=0
    if total_topics > 0:
        overall_progress = round(
            (completed_count * 100 + in_progress_count * 50) / total_topics
        )
    else:
        overall_progress = 0

    # Average quiz score across all user responses
    avg_result = Response.objects.filter(user=request.user).aggregate(avg=Avg('score'))
    avg_score  = round(avg_result['avg'] or 0)

    # Total quiz attempts
    quiz_count = Response.objects.filter(user=request.user).count()

    return render(request, "courses/topics.html", {
        "topics":           topics,
        "progress_map":     progress_map,
        "total_topics":     total_topics,
        "completed_count":  completed_count,
        "overall_progress": overall_progress,
        "avg_score":        avg_score,
        "quiz_count":       quiz_count,
    })


@login_required(login_url='user:login')
def topic_detail(request, topic_id):
    topic = get_object_or_404(Topic, pk=topic_id)
    related_quizzes = Quiz.objects.filter(topic=topic)

    if request.method == 'POST':
        comment_text = request.POST.get('comment_text')
        if comment_text:
            TopicComment.objects.create(
                user=request.user,
                topic_id=topic_id,
                text=comment_text
            )
            messages.success(request, "Fikringiz muvaffaqiyatli qo'shildi!")
            return redirect('courses:topic', topic_id=topic_id)

    comments = TopicComment.objects.filter(topic_id=topic_id).order_by('-created_at')
    progress = TopicProgress.objects.filter(user=request.user, topic=topic).first()

    return render(request, 'courses/topic_detail.html', {
        'topic': topic,
        'topic_id': topic_id,
        'related_quizzes': related_quizzes,
        'comments': comments,
        'progress': progress,
    })

@login_required(login_url='user:login')
def like_comment(request, comment_id):
    comment = get_object_or_404(TopicComment, id=comment_id)
    action = request.GET.get('action', 'like')
    if action == 'like':
        if request.user in comment.likes.all():
            comment.likes.remove(request.user)
        else:
            comment.likes.add(request.user)
            comment.dislikes.remove(request.user)
    elif action == 'dislike':
        if request.user in comment.dislikes.all():
            comment.dislikes.remove(request.user)
        else:
            comment.dislikes.add(request.user)
            comment.likes.remove(request.user)
    return redirect(request.META.get('HTTP_REFERER', 'courses:index'))

@login_required(login_url='user:login')
@require_POST
def update_progress_view(request, topic_id):
    topic = get_object_or_404(Topic, pk=topic_id)
    status = request.POST.get('status')
    if status in ['not_started', 'in_progress', 'completed']:
        TopicProgress.objects.update_or_create(
            user=request.user, topic=topic,
            defaults={'status': status}
        )
    return redirect('courses:topic', topic_id=topic_id)

# ── Shared helper: block type descriptions for the template ──
BLOCK_TYPES = [
    ('text',      'Matn',              'fa-align-left',    'Oddiy paragraf matni'),
    ('quote',     'Iqtibos',           'fa-quote-left',    'Muallifga havola bilan iqtibos'),
    ('keypoints', 'Asosiy nuqtalar',   'fa-star',          'Belgilangan muhim fikrlar ro\'yxati'),
    ('timeline',  "Vaqt chizig'i",     'fa-history',       'Sana va tarix ketma-ketligi'),
    ('person',    'Shaxs',             'fa-user-circle',   'Muallif, olim yoki tarixiy shaxs'),
    ('info',      "Ma'lumot bloki",    'fa-info-circle',   'Izohli ma\'lumot yoki eslatma'),
]


def _build_sections_data(topic):
    """Serialize a topic's sections+items to a Python list (for JS pre-load)."""
    result = []
    for section in topic.sections.all():
        result.append({
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
        })
    return result


def _save_sections(topic, sections_json_str):
    """Parse sections JSON, delete old sections, create new ones."""
    # Delete all existing sections (cascade deletes items too)
    topic.sections.all().delete()

    try:
        sections_data = json.loads(sections_json_str or '[]')
    except json.JSONDecodeError:
        sections_data = []

    for section_data in sections_data:
        section = TopicSection.objects.create(
            topic=topic,
            type=section_data.get('type', 'text'),
            title=section_data.get('title', ''),
            order=section_data.get('order', 0),
        )
        for item_data in section_data.get('items', []):
            text     = item_data.get('text', '').strip()
            sub_text = item_data.get('sub_text', '').strip()
            label    = item_data.get('label', '').strip()
            # skip completely empty items
            if not (text or sub_text or label):
                continue
            TopicSectionItem.objects.create(
                section=section,
                text=text,
                sub_text=sub_text,
                label=label,
                order=item_data.get('order', 0),
            )


# ── Create ────────────────────────────────────────────────────
@login_required(login_url='user:login')
@require_profile
def create_topic_view(request):
    if request.method == 'POST':
        title       = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        icon        = request.POST.get('icon', 'fa-book').strip()
        sections_json = request.POST.get('sections_json', '[]')

        if not title:
            messages.error(request, "Mavzu nomi kiritilishi shart!")
            return redirect('courses:create_topic')

        topic = Topic.objects.create(
            title=title,
            description=description,
            icon=icon,
            created_by=request.user,
        )
        _save_sections(topic, sections_json)

        messages.success(request, f"'{topic.title}' mavzusi muvaffaqiyatli yaratildi!")
        return redirect('courses:topic', topic_id=topic.id)

    return render(request, 'courses/topic_form.html', {
        'topic':        None,
        'sections_data': json.dumps([]),
        'block_types':  BLOCK_TYPES,
    })


# ── Edit ──────────────────────────────────────────────────────
@login_required(login_url='user:login')
@require_profile
def edit_topic_view(request, topic_id):
    topic = get_object_or_404(Topic, pk=topic_id)

    if request.method == 'POST':
        title         = request.POST.get('title', '').strip()
        description   = request.POST.get('description', '').strip()
        icon          = request.POST.get('icon', 'fa-book').strip()
        sections_json = request.POST.get('sections_json', '[]')

        if not title:
            messages.error(request, "Mavzu nomi kiritilishi shart!")
            return redirect('courses:edit_topic', topic_id=topic_id)

        topic.title       = title
        topic.description = description
        topic.icon        = icon
        topic.save()
        _save_sections(topic, sections_json)

        messages.success(request, "Mavzu muvaffaqiyatli saqlandi!")
        return redirect('courses:edit_topic', topic_id=topic_id)

    sections_data = json.dumps(_build_sections_data(topic), ensure_ascii=False)
    return render(request, 'courses/topic_form.html', {
        'topic':        topic,
        'sections_data': sections_data,
        'block_types':  BLOCK_TYPES,
    })


# ── Delete ────────────────────────────────────────────────────
@login_required(login_url='user:login')
@require_profile
@require_POST
def delete_topic_view(request, topic_id):
    topic = get_object_or_404(Topic, pk=topic_id)
    title = topic.title
    topic.delete()
    messages.success(request, f"'{title}' mavzusi o'chirildi")
    return redirect('courses:modules')


@login_required(login_url='user:login')
@require_profile
def all_questions_view(request):
    questions = Question.objects.order_by('-created_at')

    return render(request, "courses/all_questions.html", {
        'questions': questions,
    })

@login_required(login_url='user:login')
@require_profile
def create_question_view(request):
    questions = Question.objects.order_by('-created_at')[:10]

    return render(request, "courses/question.html", {
        'questions': questions,
    })

@require_POST
@login_required(login_url='user:login')
@require_profile
def save_question_view(request):
    # get the question text and type, it is an input for any type of question
    question_text = request.POST.get('question_text')
    type = request.POST.get('type')
    # if we do not have any question text and type, we do not proceed
    if not (question_text and type):
        return redirect('courses:index')
    # if there is then we  will create question object first then register its answers with loop
    question = Question.objects.create(question_text=question_text, type=type)
    # determine the correct choice id
    correct_choices = request.POST.getlist('correct_choice')
    # for multiple choice or multiple select questions we can do iteration until it breaks
    if type in ['mc', 'ms']:    
        i = 1
        while True:
            # take the choice text value and compare if it is correct answer
            # we will break forever loop once we do not have next input
            choice_text = request.POST.get(f'choice_text_{i}')
            if not choice_text:
                break
            is_correct = str(i) in correct_choices  # compare as strings
            QuestionChoice.objects.create(question=question, choice_text=choice_text, is_correct=is_correct)
            i += 1
    elif type == 'tf':
        tf_answer = request.POST.get('tf_answer')  # 'true' or 'false'
        QuestionChoice.objects.create(question=question, choice_text="To'g'ri", is_correct=(tf_answer == 'true'))
        QuestionChoice.objects.create(question=question, choice_text="Noto'g'ri", is_correct=(tf_answer == 'false'))
    messages.success(request, "Savol qo'shildi")         
    return redirect('courses:add_question')

@login_required(login_url='user:login')
@require_profile
def edit_question_view(request, question_id):
    questions = Question.objects.order_by('-created_at')[:10]
    
    if question_id:
        question = get_object_or_404(Question, id=question_id)
        question_choices = QuestionChoice.objects.filter(question=question).all()

    if request.method == 'POST':
        question_text = request.POST.get('question_text')
        type = request.POST.get('type')
        # if there is then we  will create question object first then register its answers with loop
        question.question_text = question_text
        question.type = type
        question.save()
        # first clear all of the answers of previous
        question.questionchoice_set.all().delete()

        # determine the correct choice id
        correct_choices = request.POST.getlist('correct_choice')
        if type in ['mc', 'ms']:
            i = 1
            while True:
                # take the choice text value and compare if it is correct answer
                # we will break forever loop once we do not have next input
                choice_text = request.POST.get(f'choice_text_{i}')
                if not choice_text:
                    break
                is_correct = str(i) in correct_choices  # compare as strings
                QuestionChoice.objects.create(question=question, choice_text=choice_text, is_correct=is_correct)
                i += 1
        elif type == 'tf':
            tf_answer = request.POST.get('tf_answer')  # 'true' or 'false'
            QuestionChoice.objects.create(question=question, choice_text="To'g'ri", is_correct=(tf_answer == 'true'))
            QuestionChoice.objects.create(question=question, choice_text="Noto'g'ri", is_correct=(tf_answer == 'false'))
        messages.success(request, "Savol o'zgartirildi") 
        return redirect("courses:edit_question", question.pk)

    return render(request, "courses/question.html", {
        'current_question': question,
        'question_choices': question_choices,
        'questions':questions,
    })

@login_required(login_url='user:login')
@require_profile
@require_POST
def delete_question_view(request, question_id):
    question = get_object_or_404(Question, pk=question_id)
    question.delete()
    messages.success(request, "Savol o'chirildi")
    return redirect('courses:all_questions')

@login_required(login_url='user:login')
@require_profile
def all_quizzes_view(request):
    quizzes = Quiz.objects.order_by('-id')
    return render(request, 'courses/all_quizzes.html', {'quizzes': quizzes})

@login_required(login_url='user:login')
@require_profile
def create_quiz_view(request):
    questions = Question.objects.order_by('-created_at')
    topics = Topic.objects.all()
    return render(request, "courses/quiz.html", {
        'questions':questions,
        'topics':topics
    })

@login_required(login_url='user:login')
@require_profile
@require_POST
def save_quiz_view(request):
    title = request.POST.get('title')
    type = request.POST.get('type')
    description = request.POST.get('description')
    if not (title and type):
        messages.error(request, "To'ldirilmagan maydonlar mavjud") 
        return redirect("courses:add_quiz")
    if topic_id := request.POST.get('topic'):
        topic = get_object_or_404(Topic, pk = topic_id)
    else:
        topic = None

    question_ids = request.POST.getlist('question_ids')
    question_orders = request.POST.getlist('question_orders')
    if not (question_ids and question_orders):
        messages.error(request, "Savollar tanlanmagan") 
        return redirect("courses:add_quiz")

    quiz = Quiz.objects.create(
        title = title,
        type = type,
        topic = topic, 
        description = description,
    )

    for question_id, order in zip(question_ids, question_orders):
        question = get_object_or_404(Question, pk = question_id)
        QuizQuestion.objects.create(
            quiz = quiz,
            question = question,
            order = int(order)
        )
    messages.success(request, "Topshiriq muvaffaqiyatli yaratildi") 
    return redirect("courses:add_quiz")

@login_required(login_url='user:login')
@require_profile
def edit_quiz_view(request, quiz_id):
    quiz = get_object_or_404(Quiz, pk = quiz_id)
    
    if request.method == 'POST':
        title = request.POST.get('title')
        type = request.POST.get('type')
        description = request.POST.get('description')
        if not (title and type):
            messages.error(request, "To'ldirilmagan maydonlar mavjud") 
            return redirect("courses:add_quiz")
        if topic_id := request.POST.get('topic'):
            topic = get_object_or_404(Topic, pk = topic_id)
        else:
            topic = None

        question_ids = request.POST.getlist('question_ids')
        question_orders = request.POST.getlist('question_orders')
        if not (question_ids and question_orders):
            messages.error(request, "Savollar tanlanmagan") 
            return redirect("courses:add_quiz")

        quiz.title = title
        quiz.type = type
        quiz.topic = topic
        quiz.description = description
        quiz.save()
        quiz.quizquestion_set.all().delete()
        for question_id, order in zip(question_ids, question_orders):
            question = get_object_or_404(Question, pk = question_id)
            QuizQuestion.objects.create(
                quiz = quiz,
                question = question,
                order = int(order)
            )
        messages.success(request, "Topshiriq muvaffaqiyatli o'zgartirildi") 
        return redirect("courses:edit_quiz", quiz_id)
    
    questions = Question.objects.order_by('-created_at')
    topics = Topic.objects.all()
    return render(request, "courses/quiz.html", {
        'current_quiz': quiz,
        'questions':questions,
        'topics':topics
    })

# views.py
@login_required(login_url='user:login')
@require_profile
@require_POST
def delete_quiz_view(request, quiz_id):
    quiz = get_object_or_404(Quiz, pk=quiz_id)
    quiz.delete()
    messages.success(request, f"'{quiz.title}' testi o'chirildi")
    return redirect('courses:all_quizzes')

@login_required(login_url='user:login')
@require_profile
def quiz_attempt(request, quiz_id):
        
    quiz = get_object_or_404(Quiz, pk=quiz_id)
    questions = QuizQuestion.objects.filter(quiz=quiz).order_by('order').select_related('question')
    return render(request, 'courses/quiz_attempt.html', {
        'quiz': quiz,
        'questions': questions,
        'quiz_duration': 15,  # minutes
    })

@login_required(login_url='user:login')
@require_POST
def log_violation(request):
    # Save to session or a Violation model if you want to track it
    data = json.loads(request.body)
    # e.g. ViolationLog.objects.create(user=request.user, quiz_id=data['quiz_id'], reason=data['reason'])
    return JsonResponse({'ok': True})

@login_required(login_url='user:login')
@require_profile
@require_POST
def submit_quiz(request, quiz_id):
    # take the quiz_id and its object from db
    quiz = get_object_or_404(Quiz, pk=quiz_id)
    response = Response.objects.create(
        user=request.user,
        quiz=quiz,
        score = 0,
    )
    # now take all the questions related or linked to this quiz
    questions = QuizQuestion.objects.filter(quiz=quiz).select_related('question')
    # initialize score, from 0 to calculate overall
    correct_count = 0
    incorrect_count = 0
    skipped_count = 0
    # debug for checking number of questions in quiz
    # print(f'quiz question amount: {len(questions)}')

    # now for loop to iterate each question
    for qq in questions:
        # qq is only one instance of QuizQestion
       # we need question of that instance 
        q = qq.question
        # take users input from POST (q = one question, we take id of that question)
        if q.type == 'mc':
            user_choice = request.POST.get(f'q_{q.pk}')
            # if user is not selected anything
            if not user_choice:
                skipped_count +=1
                ResponseDetails.objects.create(response=response, question=q, is_correct=None)
            else:
                # take this questions correct choice
                correct_choice = QuestionChoice.objects.filter(pk = user_choice, question=q).first()    
                # check if there is actually users choice and is his choice correct. If there is not actual user choice mark it as incorrect
                if correct_choice and correct_choice.is_correct:
                    correct_count +=1
                    ResponseDetails.objects.create(response=response, question=q, question_choice = correct_choice, is_correct= True)
                else:
                    incorrect_count +=1
                    ResponseDetails.objects.create(response=response, question=q, question_choice = correct_choice, is_correct= False)
        elif q.type == 'ms':
            selected_ids = request.POST.getlist(f'q_{q.pk}')
            if not selected_ids:
                skipped_count += 1
            else:
                correct_ids  = set(QuestionChoice.objects.filter(question=q, is_correct=True).values_list('id', flat=True))
                selected_ids = set(int(i) for i in selected_ids)
                for cid in selected_ids:
                    choice = QuestionChoice.objects.filter(id=cid, question=q).first()
                    ResponseDetails.objects.create(response=response, question=q, question_choice=choice)
                if selected_ids == correct_ids:
                    correct_count += 1
                else:
                    incorrect_count += 1
        elif q.type == 'tf':
            answer = request.POST.get(f'q_{q.pk}')
            if not answer:
                skipped_count += 1
            else:
                correct_choice = QuestionChoice.objects.filter(question=q, is_correct=True).first()
                is_correct = correct_choice and correct_choice.choice_text.lower() == answer.lower()
                ResponseDetails.objects.create(response=response, question=q, user_text_answer=answer)
                if is_correct:
                    correct_count += 1
                else:
                    incorrect_count += 1
        elif q.type in ('sha', 'es'):
            text = request.POST.get(f'q_{q.pk}', '').strip()
            if not text:
                skipped_count += 1
            else:
                ResponseDetails.objects.create(response=response, question=q, user_text_answer=text)
                # Text answers need manual grading — count as skipped for now
                skipped_count += 1 

    # calculate score in percentage
    number_of_questions = len(questions)
    score = round((correct_count/number_of_questions)*100,1) if number_of_questions > 0 else 0
    # save to db score and quiz response
    response.score = score
    response.correct_count = correct_count
    response.incorrect_count = incorrect_count
    response.skipped_count = skipped_count
    response.save()
    return redirect('courses:score_view', response_id=response.pk)

# it gets response_id from redirect above submit_quiz view
@login_required(login_url='user:login')
@require_profile
def score_view(request, response_id):
    # take response and quiz objects
    response = get_object_or_404(Response, pk=response_id, user=request.user)
    quiz = response.quiz

    # just display how many +/-/ answers and score of student. POST -> SAVE -> GET method for security
    return render(request, 'courses/quiz_result.html', {
        'quiz': quiz,
        'response_id': response.pk,
        'score': response.score,
        'correct_count': response.correct_count,
        'incorrect_count': response.incorrect_count,
        'skipped_count': response.skipped_count,
    })

@login_required(login_url='user:login')
@require_profile
def score_details_view(request, response_id):
    response = get_object_or_404(Response, pk=response_id, user=request.user)
    
    # 1. Fetch all details and prefetch questions/choices to avoid N+1 queries
    details = ResponseDetails.objects.filter(response=response).select_related('question', 'question_choice')
    
    # 2. Group details by question
    # We use a dict to group multiple ResponseDetails (for 'ms' type) together
    grouped_results = {}
    
    for d in details:
        q = d.question
        if q.id not in grouped_results:
            # Find the correct answer(s) for this question
            correct_choices = QuestionChoice.objects.filter(question=q, is_correct=True)
            
            grouped_results[q.id] = {
                'question': q,
                'is_correct': d.is_correct, # Logic depends on type
                'user_choices': [],
                'user_text': d.user_text_answer,
                'correct_answers': [c.choice_text for c in correct_choices],
                'type': q.type
            }
        
        if d.question_choice:
            grouped_results[q.id]['user_choices'].append(d.question_choice.choice_text)

    # 3. Final polish for the template
    results_list = list(grouped_results.values())

    return render(request, 'courses/quiz_details.html', {
        'title': response.quiz.title,
        'topic_id': response.quiz.topic.pk if response.quiz.topic else None,
        'score': response.score,
        'results': results_list,
    })


def all_forum_view(request):
    if request.method == "POST" and request.user.is_authenticated:
        title = request.POST.get('title')
        forum_question = request.POST.get('forum_question')
        if not (title and forum_question):
            messages.error(request, "Xatolik!")
            return redirect('courses:forums')
        topic_id = request.POST.get('topic_id')
        topic = Topic.objects.filter(pk=topic_id).first() if topic_id else None
        forum = Forum.objects.create(
            user=request.user, title=title,
            forum_question=forum_question, topic=topic,
        )
        messages.success(request, f"Forum #{forum.pk} muvaffaqiyatli yaratildi!")
        return redirect('courses:forums')

    # Filter
    topic_filter = request.GET.get('topic')
    q = request.GET.get('q')
    forums = Forum.objects.all()

    if topic_filter and topic_filter.isdecimal():
        forums = forums.filter(topic__id=topic_filter)
    elif topic_filter == 'general':
        forums = forums.filter(topic__isnull=True)

    if q:
        forums = forums.filter(title__icontains=q) | forums.filter(forum_question__icontains=q)

    # Sort
    sort = request.GET.get('sort', 'new')
    if sort == 'top':
        forums = forums.annotate(like_count=Count('likes')).order_by('-like_count')
    elif sort == 'active':
        forums = forums.annotate(comment_count=Count('forumcomment')).order_by('-comment_count')
    else:
        forums = forums.order_by('-created_at')

    # Paginate
    paginator = Paginator(forums, 10)
    page = request.GET.get('page', 1)
    forums = paginator.get_page(page)

    topics = Topic.objects.order_by('-created_at')
    top_contributors = (
        ForumComment.objects
        .values('user__first_name', 'user__last_name', 'user__id')
        .annotate(comment_count=Count('id'), like_count=Count('likes'))
        .order_by('-comment_count')[:5]
    )

    return render(request, 'courses/forums.html', {
        'topics': topics,
        'forums': forums,
        'top_contributors': top_contributors,
        'total_forums': Forum.objects.count(),
        'total_comments': ForumComment.objects.count(),
        'total_users': User.objects.filter(forumcomment__isnull=False).distinct().count(),
        'general_forum_count': Forum.objects.filter(topic__isnull=True).count(),
    })

def forum_view(request, forum_id):
    forum = get_object_or_404(Forum, pk=forum_id)

    # Sort comments
    sort = request.GET.get('sort', 'new')
    comments = ForumComment.objects.filter(forum=forum, parent=None)
    if sort == 'top':
        comments = comments.annotate(like_count=Count('likes')).order_by('-like_count')
    else:
        comments = comments.order_by('-created_at')

    # Paginate
    paginator = Paginator(comments, 10)
    page = request.GET.get('page', 1)
    comments = paginator.get_page(page)

    top_contributors = (
        ForumComment.objects
        .filter(forum=forum)
        .values('user__first_name', 'user__last_name', 'user__id')
        .annotate(comment_count=Count('id'), like_count=Count('likes'))
        .order_by('-comment_count')[:5]
    )

    return render(request, 'courses/forum.html', {
        'forum': forum,
        'comments': comments,
        'top_contributors': top_contributors,
    })

@login_required(login_url='user:login')
@require_profile
@require_POST
def post_comment_view(request, forum_id):

    forum = get_object_or_404(Forum, pk=forum_id)
    text = request.POST.get('text')
    if not text:
        messages.error(request,"Xatolik!")
        return redirect('courses:forum', forum_id)
    
    parent_id = request.POST.get('comment_id')
    parent = ForumComment.objects.filter(pk=parent_id).first() if parent_id else None
    
    forum_comment = ForumComment.objects.create(
        user = request.user,
        forum = forum,
        text = text,
        parent = parent,
    )
    messages.success(request, f"Fikr muvaffaqiyatli qo'shildi!")
    return redirect('courses:forum', forum_id)


@login_required(login_url='user:login')
@require_POST
def toggle_vote_view(request):
    data = json.loads(request.body)
    obj_type = data.get('type')   # 'forum' or 'comment'
    obj_id   = data.get('id')
    action   = data.get('action') # 'like' or 'dislike'
    
    if obj_type == 'forum':
        obj = get_object_or_404(Forum, pk=obj_id)
    else:
        obj = get_object_or_404(ForumComment, pk=obj_id)
    
    # toggle like
    if action == 'like':
        if request.user in obj.likes.all():
            obj.likes.remove(request.user)  # unlike
        else:
            obj.likes.add(request.user)
            obj.dislikes.remove(request.user)
    elif action == 'dislike':
        if request.user in obj.dislikes.all():
            obj.dislikes.remove(request.user)  # un-dislike
        else:
            obj.dislikes.add(request.user)
            obj.likes.remove(request.user)

    return JsonResponse({
        'likes': obj.likes.count(),
        'dislikes': obj.dislikes.count(),
    })