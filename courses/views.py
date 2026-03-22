from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import TopicComment, Quiz, Question, QuizQuestion, Response, ResponseDetails, QuestionChoice, Topic, Forum, ForumComment
from django.contrib.auth.models import User
import json
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from functools import wraps

def require_profile(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user_profile = getattr(request.user, 'userprofile', None)
        if not user_profile:
            return redirect('courses:index')
        return view_func(request, *args, **kwargs)
    return wrapper

# Create your views here.
def index(request):
    return render(request, "courses/index.html", {
        "profile": "profile",
    })

@login_required(login_url='user:login')
@require_profile
def modules_view(request):
    # Later you can create a 'Progress' model to track this accurately.
    mock_progress = {
        1: 100, # 100% complete
        2: 45,  # 45% complete
        3: 0,   # Not started
    }

    return render(request, "courses/modules.html", {
        "progress": mock_progress,
    })

@login_required(login_url='user:login')
def topic_detail(request, topic_id):
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
    
    return render(request, f'courses/topic_detail_{topic_id}.html', {
        'topic_id': topic_id,
        'quiz_id': topic_id,
        'comments': comments,
        'title': "1-MA'RUZA: Hamshiralik ishi tarixi",
    })

@login_required(login_url='user:login')
@require_profile
def like_comment(request, comment_id):
    comment = get_object_or_404(TopicComment, id=comment_id)
    if comment.likes.filter(id=request.user.id).exists():
        comment.likes.remove(request.user)
    else:
        comment.likes.add(request.user)
    
    # Redirect back to the same page
    return redirect(request.META.get('HTTP_REFERER', 'courses:index'))

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

# add view for watching score details
@login_required(login_url='user:login')
@require_profile
def score_details_view(request, response_id):
    response = get_object_or_404(Response, pk=response_id, user=request.user)
    details = ResponseDetails.objects.filter(response=response).all()
    # for each detail, which is what user selected. First take correct answer of the exact question and assign it to new value
    # with this new value we will show it to student
    for detail in details:
        correct = QuestionChoice.objects.filter(question=detail.question, is_correct=True).first()
        detail.correct_answer_text = correct.choice_text if correct else ''

    return render(request, 'courses/quiz_details.html', {
        'title': response.quiz.title,
        # sometimes we may not have topic
        'topic_id': response.quiz.topic.pk if response.quiz.topic else None,
        'score': response.score,
        'details':details,
    })


# add view for forum
def forum_view(request):
    
    if request.method == "POST" and request.user.is_authenticated:
        title = request.POST.get('title')
        forum_question = request.POST.get('forum_question')
        if not (title and forum_question):
            messages.error(request,"Xatolik!")
            return redirect('courses:forums')
        forum = Forum.objects.create(
            user = request.user,
            title= title,
            forum_question = forum_question,
        )
        messages.success(request, f"Forum #{forum.pk} muvaffaqiyatli yaratildi!")
        return redirect('courses:forums')
    
    topics = Topic.objects.order_by('-created_at')
    forums = Forum.objects.order_by('-created_at')
   
    return render(request, 'courses/forum.html', {
        'topics': topics,
        'forums': forums,
    })