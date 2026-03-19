from django.urls import path
from django.contrib.auth.decorators import login_required
from . import views

app_name = "courses"

urlpatterns = [
    path("", views.index, name="index"), 
    path("modules/", views.modules_view, name="modules"), 
    path("topic/<int:topic_id>/", views.topic_detail, name="topic"), 
    path("comment/<int:comment_id>/like/", views.like_comment, name="like_comment"),
    
    # admin panel
    path("create-question/", views.create_question_view, name="add_question"),
    path("save-question/", views.save_question_view, name="save_question"),

    path("create-quiz/", views.create_quiz_view, name="admin_quiz"),
    path('quiz/<int:quiz_id>/', views.quiz_attempt, name='quiz_attempt'),
    path('quiz/violation/', views.log_violation, name='log_violation'),
    path('quiz/submit/<int:quiz_id>/', views.submit_quiz, name='submit_quiz'),
    path('quiz/answer/<int:response_id>/', views.score_view, name='score_view'),
    path('quiz/details/<int:response_id>/', views.score_details_view, name='score_details'),
]