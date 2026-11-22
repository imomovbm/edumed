from datetime import timedelta

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

OPTION_LETTERS = 'ABCDEFGH'


def option_letter(index):
    return OPTION_LETTERS[index] if 0 <= index < len(OPTION_LETTERS) else '?'


class Exam(models.Model):
    DRAFT = 'draft'
    PUBLISHED = 'published'
    FINISHED = 'finished'
    STATUS_CHOICES = [
        (DRAFT, 'Qoralama'),
        (PUBLISHED, 'Eʼlon qilingan'),
        (FINISHED, 'Yakunlangan'),
    ]

    title = models.CharField("Imtihon nomi", max_length=200)
    subject = models.CharField("Fan", max_length=200, blank=True)
    status = models.CharField("Holat", max_length=12, choices=STATUS_CHOICES, default=DRAFT, db_index=True)
    duration_minutes = models.PositiveSmallIntegerField(
        "Davomiyligi (daqiqa)", default=20, validators=[MinValueValidator(1), MaxValueValidator(600)],
    )
    starts_at = models.DateTimeField("Boshlanish vaqti", null=True, blank=True)
    ends_at = models.DateTimeField("Tugash vaqti", null=True, blank=True)
    question_count = models.PositiveSmallIntegerField(
        "Har bir talabaga beriladigan savollar soni", null=True, blank=True,
        validators=[MinValueValidator(1)],
        help_text="Boʻsh qoldirilsa — barcha savollar; son yozilsa — har bir talabaga tasodifiy N ta savol.",
    )
    shuffle_questions = models.BooleanField("Savollar tartibini aralashtirish", default=True)
    shuffle_options = models.BooleanField("Javob variantlarini aralashtirish", default=True)
    groups = models.ManyToManyField('user.StudentGroup', blank=True, related_name='exams', verbose_name="Guruhlar")
    students = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name='assigned_exams', verbose_name="Alohida talabalar",
    )
    max_leaves = models.PositiveSmallIntegerField(
        "Oynadan chiqish limiti", default=3, validators=[MinValueValidator(1), MaxValueValidator(20)],
        help_text="Talaba imtihon oynasini shuncha marta tark etsa, test avtomatik yakunlanadi.",
    )
    count_fullscreen_exit = models.BooleanField(
        "Toʻliq ekrandan chiqish ham chiqish hisoblansin", default=False,
        help_text="Oʻchiq boʻlsa, toʻliq ekrandan chiqilganda savollar yashiriladi va qayd etiladi, "
                  "lekin limitga qoʻshilmaydi.",
    )
    show_score = models.BooleanField("Natijani talabaga koʻrsatish", default=True)
    source_name = models.CharField("Import qilingan fayl", max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_exams',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Imtihon'
        verbose_name_plural = 'Imtihonlar'
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    def window_state(self, now=None):
        """'upcoming' before the start time, 'closed' after the end time, else 'open'."""
        now = now or timezone.now()
        if self.starts_at and now < self.starts_at:
            return 'upcoming'
        if self.ends_at and now >= self.ends_at:
            return 'closed'
        return 'open'

    def accepts_starts(self, now=None):
        return self.status == self.PUBLISHED and self.window_state(now) == 'open'


class Question(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='questions')
    order = models.PositiveIntegerField("Tartib raqami")
    text = models.TextField("Savol")
    source_line = models.PositiveIntegerField("Fayldagi qator", null=True, blank=True)

    class Meta:
        verbose_name = 'Savol'
        verbose_name_plural = 'Savollar'
        ordering = ['exam', 'order', 'id']
        constraints = [models.UniqueConstraint(fields=['exam', 'order'], name='imtihon_question_unique_order')]

    def __str__(self):
        return self.text if len(self.text) <= 80 else self.text[:77] + '...'


class Choice(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='choices')
    order = models.PositiveSmallIntegerField("Tartib raqami")
    text = models.TextField("Javob varianti")
    is_correct = models.BooleanField("Toʻgʻri", default=False)

    class Meta:
        verbose_name = 'Javob varianti'
        verbose_name_plural = 'Javob variantlari'
        ordering = ['question', 'order', 'id']

    def __str__(self):
        return self.text


class Attempt(models.Model):
    """One student's sitting of one exam (created when the student starts)."""

    ASSIGNED = 'assigned'
    RUNNING = 'running'
    FINISHED = 'finished'
    STATUS_CHOICES = [
        (ASSIGNED, 'Boshlanmagan'),
        (RUNNING, 'Davom etmoqda'),
        (FINISHED, 'Yakunlangan'),
    ]

    REASON_SUBMITTED = 'submitted'
    REASON_TIME_UP = 'time_up'
    REASON_VIOLATIONS = 'violations'
    REASON_TEACHER = 'teacher'
    REASON_CLOSED = 'closed'
    REASON_CHOICES = [
        (REASON_SUBMITTED, 'Talaba oʻzi yakunladi'),
        (REASON_TIME_UP, 'Vaqt tugadi'),
        (REASON_VIOLATIONS, 'Oynadan chiqish limiti tugadi'),
        (REASON_TEACHER, 'Nazoratchi yakunladi'),
        (REASON_CLOSED, 'Imtihon yopildi'),
    ]

    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='attempts')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='imtihon_attempts')
    status = models.CharField("Holat", max_length=12, choices=STATUS_CHOICES, default=ASSIGNED, db_index=True)
    started_at = models.DateTimeField("Boshlangan", null=True, blank=True)
    finished_at = models.DateTimeField("Yakunlangan", null=True, blank=True)
    finish_reason = models.CharField("Yakunlanish sababi", max_length=12, choices=REASON_CHOICES, blank=True)
    extra_minutes = models.PositiveSmallIntegerField("Qoʻshimcha vaqt (daqiqa)", default=0)
    leave_count = models.PositiveSmallIntegerField("Oynadan chiqishlar", default=0)
    fullscreen_exits = models.PositiveSmallIntegerField("Toʻliq ekrandan chiqishlar", default=0)
    # What this student sees: question ids, and choice ids per question id, in order.
    question_order = models.JSONField(default=list, blank=True)
    choice_order = models.JSONField(default=dict, blank=True)
    question_count = models.PositiveSmallIntegerField(default=0)
    correct_count = models.PositiveSmallIntegerField("Toʻgʻri javoblar", null=True, blank=True)
    score = models.FloatField("Natija (%)", null=True, blank=True)
    # sha256 of the device cookie: the attempt continues only in the browser that started it.
    device_hash = models.CharField(max_length=64, blank=True)
    ip_address = models.GenericIPAddressField("IP manzil", null=True, blank=True)
    user_agent = models.CharField("Brauzer", max_length=400, blank=True)
    last_seen_at = models.DateTimeField("Oxirgi faollik", null=True, blank=True)
    event_count = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = 'Urinish'
        verbose_name_plural = 'Urinishlar'
        ordering = ['exam', 'user__username']
        constraints = [models.UniqueConstraint(fields=['exam', 'user'], name='imtihon_attempt_one_per_user')]

    def __str__(self):
        return f'{self.user} — {self.exam} ({self.get_status_display()})'

    @property
    def deadline(self):
        """Start + duration (+ extra time), but never later than the exam window end (+ extra)."""
        if not self.started_at:
            return None
        extra = timedelta(minutes=self.extra_minutes)
        deadline = self.started_at + timedelta(minutes=self.exam.duration_minutes) + extra
        if self.exam.ends_at:
            deadline = min(deadline, self.exam.ends_at + extra)
        return deadline

    def remaining_seconds(self, now=None):
        deadline = self.deadline
        if deadline is None:
            return self.exam.duration_minutes * 60
        now = now or timezone.now()
        return max(0, int((deadline - now).total_seconds()))

    @property
    def used_seconds(self):
        if not self.started_at:
            return None
        end = self.finished_at or timezone.now()
        return max(0, int((end - self.started_at).total_seconds()))


class Answer(models.Model):
    attempt = models.ForeignKey(Attempt, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='answers')
    choice = models.ForeignKey(Choice, on_delete=models.SET_NULL, null=True, blank=True, related_name='answers')
    changes = models.PositiveSmallIntegerField("Oʻzgartirishlar", default=0)
    answered_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Javob'
        verbose_name_plural = 'Javoblar'
        constraints = [
            models.UniqueConstraint(fields=['attempt', 'question'], name='imtihon_answer_one_per_question'),
        ]


class Event(models.Model):
    """Everything that happens around an exam, shown to the teacher as a timeline."""

    INFO = 'info'
    WARNING = 'warning'
    DANGER = 'danger'
    LEVEL_CHOICES = [(INFO, 'Maʼlumot'), (WARNING, 'Ogohlantirish'), (DANGER, 'Qoidabuzarlik')]

    attempt = models.ForeignKey(Attempt, on_delete=models.CASCADE, null=True, blank=True, related_name='events')
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, null=True, blank=True, related_name='events')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name='imtihon_events',
    )
    kind = models.CharField("Hodisa", max_length=32, db_index=True)
    level = models.CharField("Daraja", max_length=8, choices=LEVEL_CHOICES, default=INFO)
    message = models.CharField("Tavsif", max_length=300, blank=True)
    data = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        verbose_name = 'Hodisa'
        verbose_name_plural = 'Hodisalar jurnali'
        ordering = ['created_at', 'id']
        indexes = [models.Index(fields=['attempt', 'created_at'], name='imtihon_event_attempt_time')]

    def __str__(self):
        return f'{self.created_at:%H:%M:%S} {self.kind}: {self.message}'


class LoginAttempt(models.Model):
    """Sign-ins on the exam login page (used to slow down password guessing)."""

    login = models.CharField(max_length=254, db_index=True)
    success = models.BooleanField(default=False)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=400, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        verbose_name = 'Kirish urinishi'
        verbose_name_plural = 'Kirish urinishlari'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.login} {"✓" if self.success else "✗"} {self.created_at:%Y-%m-%d %H:%M}'
