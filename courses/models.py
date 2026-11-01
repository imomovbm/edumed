from django.db import models
from django.contrib.auth.models import User

class Topic(models.Model):
    title       = models.TextField()
    description = models.TextField(blank=True)
    icon        = models.CharField(max_length=50, blank=True, default='fa-book')
    created_by  = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

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

    def __str__(self):
        return f"{self.topic_id}: {self.get_type_display()} {self.title}".strip()

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
    progress = models.FloatField(default=0)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES)
    enrolled_date = models.DateField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} - {self.topic_id}: {self.status}"

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

    def __str__(self):
        text = self.question_text or ''
        return text if len(text) <= 80 else text[:77] + '...'

class QuestionChoice(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    choice_text = models.TextField(blank=True, null=True)
    is_correct = models.BooleanField()

    def __str__(self):
        return self.choice_text or ''

class Quiz(models.Model):
    title = models.TextField()
    TYPE_CHOICES = [
        ('1', 'Mavzuga biriktirilgan topshiriq'),
        ('2', 'Umumiy topshiriqlar'),
    ]
    type = models.CharField(max_length=50, choices=TYPE_CHOICES)     
    topic = models.ForeignKey(Topic, on_delete=models.SET_NULL, null=True, blank=True)
    description = models.TextField(blank=True)
    duration = models.PositiveIntegerField(default=15, verbose_name="Davomiyligi (daqiqa)")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

class QuizQuestion(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE)
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    order = models.IntegerField()

    def __str__(self):
        return f"{self.quiz_id} #{self.order}"

# Results are kept when a quiz, question or choice is deleted (SET_NULL), so a
# student's history never disappears.
class Response(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    quiz = models.ForeignKey(Quiz, on_delete=models.SET_NULL, null=True, blank=True)
    score = models.FloatField()
    correct_count = models.IntegerField(default=0)
    incorrect_count = models.IntegerField(default=0)
    skipped_count = models.IntegerField(default=0)
    # How many anti-cheat rule violations the browser reported during the attempt.
    violation_count = models.PositiveIntegerField(default=0)
    created_date_time = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} - {self.quiz_id}: {self.score}%"

class ResponseDetails(models.Model):
    response = models.ForeignKey(Response, on_delete=models.CASCADE)
    question = models.ForeignKey(Question, on_delete=models.SET_NULL, null=True, blank=True)
    question_choice = models.ForeignKey(QuestionChoice, on_delete=models.SET_NULL, null=True, blank=True)
    # True/False = graded; None = skipped, or a short/essay answer not checked yet.
    is_correct = models.BooleanField(default=None, null=True)
    user_text_answer = models.TextField(blank=True, null=True)
    # Teacher's comment on a short/essay answer.
    feedback = models.TextField(blank=True, default='')

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

    def __str__(self):
        return self.title

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

    def __str__(self):
        return f"{self.user} - forum {self.forum_id}"
