from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import TopicComment, Quiz, QuizQuestion
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
            pass
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
            pass

    return render(request, "courses/quiz.html", {
        "profile": user_profile,
    })

def quiz_attempt(request, quiz_id):
    user_profile = None
    if request.user.is_authenticated:
        try:
            user_profile = request.user.userprofile
        except:
            pass
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

def submit_quiz(request, quiz_id):
    user_profile = None
    if request.user.is_authenticated:
        try:
            user_profile = request.user.userprofile
        except:
            pass
    return render(request, 'courses/index.html', {
        "profile": user_profile,
    })