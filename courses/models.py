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
  
class Question(models.Model):
    question_text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    TYPE_CHOICES = [
        ('mc', "Bir variantli ochiq test"),
        ('ms', "Ko'p variantli ochiq test"),
        ('tf', "To'g'ri va Noto'g'ri"),
        ('sha', 'Qisqa javobli'),
        ('es', 'Essey, yozma ish'),
    ]
    type = models.CharField(max_length=50, choices=TYPE_CHOICES) 
    image = models.CharField(max_length=255, null=True, blank=True)
    audio = models.CharField(max_length=255, null=True, blank=True)
    video = models.CharField(max_length=255, null=True, blank=True)

class QuestionChoice(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    choice_text = models.TextField()
    is_correct = models.BooleanField()

class Quiz(models.Model):
    title = models.TextField()
    topic = models.ForeignKey(Topic, on_delete=models.SET_NULL, null=True, blank=True)
    TYPE_CHOICES = [
        ('1', 'Mavzuga biriktirilgan topshiriq'),
        ('2', 'Umumiy topshiriqlar'),
    ]
    type = models.CharField(max_length=50, choices=TYPE_CHOICES)     
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
