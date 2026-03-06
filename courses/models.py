from django.db import models
from django.contrib.auth.models import User

class Topic(models.Model):
    title = models.TextField()

class TopicProgress(models.Model):
    STATUS_CHOICES = [
    ('not_started', 'Not Started'),
    ('in_progress', 'In Progress'),
    ('completed', 'Completed'),
    ]
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES)
    enrolled_date = models.DateField(auto_now_add=True)

class TopicComment(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    likes = models.ManyToManyField(User, related_name='comment_likes', blank=True)

    def total_likes(self):
        return self.likes.count()

    def __str__(self):
        return f"{self.user.username} - {self.topic_id}"

class TypeQuestion(models.Model):
    TYPE_CHOICES = [
        ('1', 'Multiple choice'),
        ('2', 'O\'qituvchi'),
        ('3', 'Talaba'),
        ('4', 'Moder'),
    ]
    type = models.CharField(max_length=50, choices=TYPE_CHOICES) 
    
class Question(models.Model):
    question_text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    type_question = models.ForeignKey(TypeQuestion, on_delete=models.PROTECT)
    image = models.CharField(max_length=255, null=True, blank=True)
    audio = models.CharField(max_length=255, null=True, blank=True)
    video = models.CharField(max_length=255, null=True, blank=True)

class QuestionChoice(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    choice_text = models.TextField()
    is_correct = models.BooleanField()

class QuizType(models.Model):
    TYPE_CHOICES = [
        ('1', 'Oraliq'),
        ('2', 'O\'qituvchi'),
        ('3', 'Talaba'),
        ('4', 'Moder'),
    ]
    type = models.CharField(max_length=50, choices=TYPE_CHOICES)     

class Quiz(models.Model):
    title = models.TextField()
    topic = models.ForeignKey(Topic, on_delete=models.SET_NULL, null=True, blank=True)
    quiz_type = models.ForeignKey(QuizType, on_delete=models.PROTECT)
    description = models.TextField(blank=True)

class QuizQuestion(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE)
    order = models.IntegerField()

class Response(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE)
    score = models.FloatField()
    created_date_time = models.DateTimeField(auto_now_add=True)

class ResponseDetails(models.Model):
    response = models.ForeignKey(Response, on_delete=models.CASCADE)
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    question_choice = models.ForeignKey(QuestionChoice, on_delete=models.CASCADE, null=True, blank=True)
    user_text_answer = models.TextField(blank=True, null=True)
