from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from .blueprint import DIFFICULTY_CHOICES, OPTION_LETTERS, TOPIC_CHOICES


class Exam(models.Model):
    code = models.SlugField("Kod", max_length=50, unique=True)
    title = models.CharField("Nomi", max_length=200)
    subject = models.CharField("Fan", max_length=200, blank=True)
    duration_minutes = models.PositiveSmallIntegerField("Davomiyligi (daqiqa)", default=20)
    max_leaves = models.PositiveSmallIntegerField(
        "Oynadan chiqish limiti", default=3,
        help_text="Talaba imtihon oynasini shuncha marta tark etsa, test avtomatik yakunlanadi.",
    )
    count_fullscreen_exit = models.BooleanField(
        "Toʻliq ekrandan chiqish ham chiqish hisoblansin", default=False,
        help_text="Oʻchiq boʻlsa, toʻliq ekrandan chiqilganda savollar yashiriladi va "
                  "qayd etiladi, lekin limitga qoʻshilmaydi.",
    )
    is_open = models.BooleanField(
        "Imtihon ochiq", default=True,
        help_text="Yopiq boʻlsa, talabalar kutish sahifasida qoladi va testni boshlay olmaydi.",
    )
    show_score = models.BooleanField("Natijani talabaga koʻrsatish", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Imtihon'
        verbose_name_plural = 'Imtihonlar'
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class Question(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='questions')
    ref = models.CharField("Bank raqami", max_length=20)
    topic = models.CharField("Mavzu", max_length=20, choices=TOPIC_CHOICES)
    difficulty = models.PositiveSmallIntegerField("Qiyinlik", choices=DIFFICULTY_CHOICES, default=2)
    text = models.TextField("Savol")
    code = models.TextField("Kod / misol", blank=True)

    class Meta:
        verbose_name = 'Savol'
        verbose_name_plural = 'Savollar'
        ordering = ['exam', 'ref']
        constraints = [
            models.UniqueConstraint(fields=['exam', 'ref'], name='on_question_unique_ref'),
        ]

    def __str__(self):
        text = self.text if len(self.text) <= 80 else self.text[:77] + '...'
        return f'{self.ref}: {text}'

    def correct_choice(self):
        return next((c for c in self.choices.all() if c.is_correct), None)


class Choice(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='choices')
    text = models.TextField("Javob varianti")
    is_correct = models.BooleanField("Toʻgʻri", default=False)

    class Meta:
        verbose_name = 'Javob varianti'
        verbose_name_plural = 'Javob variantlari'
        ordering = ['id']

    def __str__(self):
        return self.text


class Variant(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='variants')
    number = models.PositiveSmallIntegerField("Variant raqami")
    questions = models.ManyToManyField(Question, through='VariantQuestion', related_name='variants')

    class Meta:
        verbose_name = 'Variant'
        verbose_name_plural = 'Variantlar'
        ordering = ['exam', 'number']
        constraints = [
            models.UniqueConstraint(fields=['exam', 'number'], name='on_variant_unique_number'),
        ]

    def __str__(self):
        return f'{self.number}-variant'


class VariantQuestion(models.Model):
    variant = models.ForeignKey(Variant, on_delete=models.CASCADE, related_name='items')
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='variant_items')
    order = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ['variant', 'order']
        constraints = [
            models.UniqueConstraint(fields=['variant', 'question'], name='on_vq_unique_question'),
            models.UniqueConstraint(fields=['variant', 'order'], name='on_vq_unique_order'),
        ]


class Attempt(models.Model):
    """One student's exam: assigned by the setup command, started by the student."""

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
    REASON_CHOICES = [
        (REASON_SUBMITTED, 'Talaba oʻzi yakunladi'),
        (REASON_TIME_UP, 'Vaqt tugadi'),
        (REASON_VIOLATIONS, 'Oynadan chiqish limiti tugadi'),
        (REASON_TEACHER, 'Nazoratchi yakunladi'),
    ]

    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='attempts')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='exam_attempts')
    variant = models.ForeignKey(Variant, on_delete=models.PROTECT, related_name='attempts')
    status = models.CharField("Holat", max_length=12, choices=STATUS_CHOICES, default=ASSIGNED, db_index=True)
    started_at = models.DateTimeField("Boshlangan", null=True, blank=True)
    finished_at = models.DateTimeField("Yakunlangan", null=True, blank=True)
    finish_reason = models.CharField("Yakunlanish sababi", max_length=12, choices=REASON_CHOICES, blank=True)
    extra_minutes = models.PositiveSmallIntegerField("Qoʻshimcha vaqt (daqiqa)", default=0)
    leave_count = models.PositiveSmallIntegerField("Oynadan chiqishlar", default=0)
    fullscreen_exits = models.PositiveSmallIntegerField("Toʻliq ekrandan chiqishlar", default=0)
    # The order the student sees: question ids, and choice ids per question id.
    question_order = models.JSONField(default=list, blank=True)
    choice_order = models.JSONField(default=dict, blank=True)
    question_count = models.PositiveSmallIntegerField(default=0)
    correct_count = models.PositiveSmallIntegerField("Toʻgʻri javoblar", null=True, blank=True)
    score = models.FloatField("Natija (%)", null=True, blank=True)
    # sha256 of the device cookie: the attempt only continues in the browser that started it.
    device_hash = models.CharField(max_length=64, blank=True)
    ip_address = models.GenericIPAddressField("IP manzil", null=True, blank=True)
    user_agent = models.CharField("Brauzer", max_length=400, blank=True)
    last_seen_at = models.DateTimeField("Oxirgi faollik", null=True, blank=True)
    event_count = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = 'Urinish'
        verbose_name_plural = 'Urinishlar'
        ordering = ['exam', 'user__username']
        constraints = [
            models.UniqueConstraint(fields=['exam', 'user'], name='on_attempt_one_per_user'),
        ]

    def __str__(self):
        return f'{self.user} — {self.exam} ({self.get_status_display()})'

    @property
    def is_running(self):
        return self.status == self.RUNNING

    @property
    def is_finished(self):
        return self.status == self.FINISHED

    @property
    def deadline(self):
        if not self.started_at:
            return None
        return self.started_at + timedelta(minutes=self.exam.duration_minutes + self.extra_minutes)

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
            models.UniqueConstraint(fields=['attempt', 'question'], name='on_answer_one_per_question'),
        ]

    @property
    def is_correct(self):
        return bool(self.choice_id and self.choice and self.choice.is_correct)


class Event(models.Model):
    """Everything that happens during the exam, shown to the teacher as a timeline."""

    INFO = 'info'
    WARNING = 'warning'
    DANGER = 'danger'
    LEVEL_CHOICES = [(INFO, 'Maʼlumot'), (WARNING, 'Ogohlantirish'), (DANGER, 'Qoidabuzarlik')]

    attempt = models.ForeignKey(Attempt, on_delete=models.CASCADE, null=True, blank=True, related_name='events')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name='exam_events',
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
        indexes = [models.Index(fields=['attempt', 'created_at'], name='on_event_attempt_time')]

    def __str__(self):
        return f'{self.created_at:%H:%M:%S} {self.kind}: {self.message}'


class LoginAttempt(models.Model):
    """Sign-ins on the exam login page (used to slow down password guessing)."""

    email = models.CharField(max_length=254, db_index=True)
    success = models.BooleanField(default=False)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=400, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        verbose_name = 'Kirish urinishi'
        verbose_name_plural = 'Kirish urinishlari'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.email} {"✓" if self.success else "✗"} {self.created_at:%Y-%m-%d %H:%M}'


def option_letter(index):
    return OPTION_LETTERS[index] if 0 <= index < len(OPTION_LETTERS) else '?'
