from django.urls import path
from django.contrib.auth.decorators import login_required
from . import views

app_name = "courses"

urlpatterns = [
    path("", views.index, name="index"), 
    path("modules/", views.modules_view, name="modules"), 
    path("topic/<int:topic_id>/", views.topic_detail, name="topic"), 
    path("comment/<int:comment_id>/like/", views.like_comment, name="like_comment"), # New
]