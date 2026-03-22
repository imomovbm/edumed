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
    path("all-questions/", views.all_questions_view, name="all_questions"),
    path("create-question/", views.create_question_view, name="add_question"),
    path("save-question/", views.save_question_view, name="save_question"),
    path("edit-question/<int:question_id>/", views.edit_question_view, name="edit_question"),

    path("all-quizzes/", views.all_quizzes_view, name="all_quizzes"),
    path("create-quiz/", views.create_quiz_view, name="add_quiz"),
    path("save-quiz/", views.save_quiz_view, name="save_quiz"),
    path("edit-quiz/<int:quiz_id>/", views.edit_quiz_view, name="edit_quiz"),

    path('quiz/<int:quiz_id>/', views.quiz_attempt, name='quiz_attempt'),
    path('quiz/violation/', views.log_violation, name='log_violation'),
    path('quiz/submit/<int:quiz_id>/', views.submit_quiz, name='submit_quiz'),
    path('quiz/answer/<int:response_id>/', views.score_view, name='score_view'),
    path('quiz/details/<int:response_id>/', views.score_details_view, name='score_details'),


    path('forum/', views.forum_view, name='forums'),
    path('post-comment/', views.post_comment_view, name='post_comment'),
]