from django.contrib import admin, messages

from . import services
from .models import Answer, Attempt, Choice, Event, Exam, LoginAttempt, Question, Variant, VariantQuestion


@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = ('title', 'code', 'is_open', 'duration_minutes', 'max_leaves', 'count_fullscreen_exit',
                    'show_score', 'created_at')
    list_editable = ('is_open',)
    search_fields = ('title', 'code')


class ChoiceInline(admin.TabularInline):
    model = Choice
    extra = 0
    fields = ('text', 'is_correct')


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('ref', 'topic', 'difficulty', 'short_text', 'exam')
    list_filter = ('exam', 'topic', 'difficulty')
    search_fields = ('ref', 'text')
    inlines = [ChoiceInline]

    @admin.display(description='Savol')
    def short_text(self, obj):
        return obj.text if len(obj.text) <= 90 else obj.text[:87] + '...'


class VariantQuestionInline(admin.TabularInline):
    model = VariantQuestion
    extra = 0
    fields = ('order', 'question')
    raw_id_fields = ('question',)


@admin.register(Variant)
class VariantAdmin(admin.ModelAdmin):
    list_display = ('number', 'exam', 'question_count', 'student')
    list_filter = ('exam',)
    inlines = [VariantQuestionInline]

    @admin.display(description='Savollar')
    def question_count(self, obj):
        return obj.items.count()

    @admin.display(description='Talaba')
    def student(self, obj):
        return ', '.join(a.user.username for a in obj.attempts.select_related('user')) or '— (zaxira)'


class AnswerInline(admin.TabularInline):
    model = Answer
    extra = 0
    fields = ('question', 'choice', 'changes', 'answered_at', 'updated_at')
    readonly_fields = fields
    can_delete = False


@admin.register(Attempt)
class AttemptAdmin(admin.ModelAdmin):
    list_display = ('user', 'exam', 'variant', 'status', 'correct_count', 'score', 'leave_count',
                    'fullscreen_exits', 'started_at', 'finished_at', 'finish_reason')
    list_filter = ('exam', 'status', 'finish_reason')
    search_fields = ('user__username', 'user__email', 'user__first_name', 'user__last_name')
    list_select_related = ('user', 'exam', 'variant')
    readonly_fields = ('question_order', 'choice_order', 'device_hash', 'ip_address', 'user_agent',
                       'last_seen_at', 'event_count', 'started_at', 'finished_at', 'correct_count', 'score')
    inlines = [AnswerInline]
    actions = ['regrade_selected']

    @admin.action(description="Tanlangan urinishlar natijasini qayta hisoblash")
    def regrade_selected(self, request, queryset):
        for attempt in queryset.select_related('exam', 'variant'):
            services.regrade(attempt)
        messages.success(request, "Natijalar qayta hisoblandi.")


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'user', 'kind', 'level', 'message', 'ip_address')
    list_filter = ('level', 'kind', 'attempt__exam')
    search_fields = ('user__username', 'message')
    list_select_related = ('user',)
    readonly_fields = ('attempt', 'user', 'kind', 'level', 'message', 'data', 'ip_address', 'created_at')

    def has_add_permission(self, request):
        return False


@admin.register(LoginAttempt)
class LoginAttemptAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'email', 'success', 'ip_address')
    list_filter = ('success',)
    search_fields = ('email',)
    readonly_fields = ('email', 'success', 'ip_address', 'user_agent', 'created_at')

    def has_add_permission(self, request):
        return False
