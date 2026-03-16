from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import TopicComment, Quiz, QuizQuestion, Response, ResponseDetails, QuestionChoice
from django.contrib.auth.models import User
import json
from django.http import JsonResponse
from django.views.decorators.http import require_POST

# Create your views here.
def index(request):
    return render(request, "courses/index.html", {
        "profile": "profile",
    })


def modules_view(request):
    user_profile = None
    # Get the user profile
    if request.user.is_authenticated:
        try:
            user_profile = request.user.userprofile
        except:
            return redirect('courses:index')
    # Later you can create a 'Progress' model to track this accurately.
    mock_progress = {
        1: 100, # 100% complete
        2: 45,  # 45% complete
        3: 0,   # Not started
    }

    return render(request, "courses/modules.html", {
        "profile": user_profile,
        "progress": mock_progress,
    })

@login_required
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

@login_required
def like_comment(request, comment_id):
    comment = get_object_or_404(TopicComment, id=comment_id)
    if comment.likes.filter(id=request.user.id).exists():
        comment.likes.remove(request.user)
    else:
        comment.likes.add(request.user)
    
    # Redirect back to the same page
    return redirect(request.META.get('HTTP_REFERER', 'courses:index'))


def create_quiz_view(request):
    user_profile = None
    if request.user.is_authenticated:
        try:
            user_profile = request.user.userprofile
        except:
            return redirect('courses:index')

    return render(request, "courses/quiz.html", {
        "profile": user_profile,
    })

def quiz_attempt(request, quiz_id):
    user_profile = None
    if request.user.is_authenticated:
        try:
            user_profile = request.user.userprofile
        except:
            return redirect('courses:index')
        
    quiz = get_object_or_404(Quiz, pk=quiz_id)
    questions = QuizQuestion.objects.filter(quiz=quiz).order_by('order').select_related('question')
    return render(request, 'courses/quiz_attempt.html', {
        "profile": user_profile,
        'quiz': quiz,
        'questions': questions,
        'quiz_duration': 15,  # minutes
    })

@require_POST
def log_violation(request):
    # Save to session or a Violation model if you want to track it
    data = json.loads(request.body)
    # e.g. ViolationLog.objects.create(user=request.user, quiz_id=data['quiz_id'], reason=data['reason'])
    return JsonResponse({'ok': True})

@require_POST
def submit_quiz(request, quiz_id):
    # check if there is a actual user, if not redirect to index
    try:
        if request.user.is_authenticated:
            user_profile = request.user.userprofile
    except:
        return redirect('courses:index')
    
    # take the quiz_id and its object from db
    quiz = get_object_or_404(Quiz, pk=quiz_id)
    response = Response.objects.create(
        user=user_profile.user,
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
            ResponseDetails.objects.create(response=response, question=q)
        else:
            # take this questions correct choice
            correct_choice = QuestionChoice.objects.filter(pk = user_choice, question=q).first()    
            # check if there is actually users choice and is his choice correct. If there is not actual user choice mark it as incorrect
            if correct_choice and correct_choice.is_correct:
                print(correct_choice.is_correct)
                correct_count +=1
                ResponseDetails.objects.create(response=response, question=q, question_choice = correct_choice)
            else:
                incorrect_count +=1

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

def score_view(request, response_id):
    response = get_object_or_404(Response, pk=response_id, user=request.user)
    quiz = response.quiz

    user_profile = None
    if request.user.is_authenticated:
        try:
            user_profile = request.user.userprofile
        except:
            pass

    return render(request, 'courses/quiz_result.html', {
        'profile': user_profile,
        'quiz': quiz,
        'score': response.score,
        'correct_count': response.correct_count,
        'incorrect_count': response.incorrect_count,
        'skipped_count': response.skipped_count,
    })
