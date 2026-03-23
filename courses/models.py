from django.db import models
from django.contrib.auth.models import User

class Topic(models.Model):
    title       = models.TextField()
    description = models.TextField(blank=True)
    icon        = models.CharField(max_length=50, blank=True, default='fa-book')
    created_by  = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)

class TopicSection(models.Model):
    TYPE_CHOICES = [
        ('text',      'Matn bloki'),
        ('quote',     'Iqtibos'),
        ('keypoints', 'Asosiy nuqtalar'),
        ('timeline',  'Vaqt chizig\'i'),
        ('person',    'Shaxs haqida'),
        ('info',      'Ma\'lumot bloki'),
    ]
    topic  = models.ForeignKey(Topic, on_delete=models.CASCADE, related_name='sections')
    type   = models.CharField(max_length=20, choices=TYPE_CHOICES)
    title  = models.CharField(max_length=255, blank=True)
    order  = models.IntegerField(default=0)

    class Meta:
        ordering = ['order']

class TopicSectionItem(models.Model):
    section   = models.ForeignKey(TopicSection, on_delete=models.CASCADE, related_name='items')
    text      = models.TextField()               # main text or bullet point
    sub_text  = models.TextField(blank=True)     # secondary text
    label     = models.CharField(max_length=100, blank=True)  # date for timeline, name for person
    order     = models.IntegerField(default=0)

    class Meta:
        ordering = ['order']

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
    likes = models.ManyToManyField(User, related_name='topic_comment_likes', blank=True)
    dislikes = models.ManyToManyField(User, related_name='topic_comment_dislikes', blank=True)

    def total_likes(self):
        return self.likes.count()

    def total_dislikes(self):
        return self.dislikes.count()

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
    choice_text = models.TextField(blank=True, null=True)
    is_correct = models.BooleanField()

class Quiz(models.Model):
    title = models.TextField()
    TYPE_CHOICES = [
        ('1', 'Mavzuga biriktirilgan topshiriq'),
        ('2', 'Umumiy topshiriqlar'),
    ]
    type = models.CharField(max_length=50, choices=TYPE_CHOICES)     
    topic = models.ForeignKey(Topic, on_delete=models.SET_NULL, null=True, blank=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

class QuizQuestion(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE)
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    order = models.IntegerField()

# ── Model on_delete fixes needed ──────────────────────────────────────────────
#
# PROBLEM 1: Response.quiz = CASCADE
#   Deleting a quiz deletes ALL student results for that quiz — data loss!
#   Fix: SET_NULL so results are preserved even if quiz is removed.
#
# PROBLEM 2: ResponseDetails.question = CASCADE
#   Deleting a question deletes the response detail row — history is lost.
#   Fix: SET_NULL so we keep the answer record even if question is deleted.
#
# PROBLEM 3: ResponseDetails.question_choice = CASCADE (already nullable)
#   Same issue — if a choice is deleted, the detail row vanishes.
#   Fix: SET_NULL.
#
class Response(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    quiz = models.ForeignKey(Quiz, on_delete=models.SET_NULL, null=True, blank=True)  # ← was CASCADE
    score = models.FloatField()
    correct_count = models.IntegerField(default=0)
    incorrect_count = models.IntegerField(default=0)
    skipped_count = models.IntegerField(default=0)
    created_date_time = models.DateTimeField(auto_now_add=True)

class ResponseDetails(models.Model):
    response = models.ForeignKey(Response, on_delete=models.CASCADE)
    question = models.ForeignKey(Question, on_delete=models.SET_NULL, null=True, blank=True)  # ← was CASCADE
    question_choice = models.ForeignKey(QuestionChoice, on_delete=models.SET_NULL, null=True, blank=True)  # ← was CASCADE
    is_correct = models.BooleanField(default=None, null=True)
    user_text_answer = models.TextField(blank=True, null=True)

class Forum(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, null=True, blank=True)
    title = models.TextField()
    forum_question = models.TextField()
    likes = models.ManyToManyField(User, related_name='forum_likes', blank=True)
    dislikes = models.ManyToManyField(User, related_name='forum_dislikes', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def total_likes(self):
        return self.likes.count()
    
    def total_dislikes(self):
        return self.dislikes.count()

class ForumComment(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    forum = models.ForeignKey(Forum, on_delete=models.CASCADE)
    text =  models.TextField()
    likes = models.ManyToManyField(User, related_name='forum_comment_likes', blank=True)
    dislikes = models.ManyToManyField(User, related_name='forum_comment_dislikes', blank=True)
    parent = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='replies'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def total_likes(self):
        return self.likes.count()
    
    def total_dislikes(self):
        return self.dislikes.count()