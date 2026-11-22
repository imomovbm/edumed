from django.contrib import admin, messages

from . import services
from .models import Answer, Attempt, Choice, Event, Exam, LoginAttempt, Question


@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = ('title', 'subject', 'status', 'duration_minutes', 'question_count', 'starts_at', 'ends_at',
                    'created_at')
    list_filter = ('status', 'subject')
    search_fields = ('title', 'subject')
    filter_horizontal = ('groups', 'students')
    readonly_fields = ('created_by', 'created_at', 'updated_at', 'published_at', 'finished_at', 'source_name')


class ChoiceInline(admin.TabularInline):
    model = Choice
    extra = 0
    fields = ('order', 'text', 'is_correct')


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('order', 'short_text', 'exam', 'source_line')
    list_filter = ('exam',)
    search_fields = ('text',)
    inlines = [ChoiceInline]

    @admin.display(description='Savol')
    def short_text(self, obj):
        return obj.text if len(obj.text) <= 90 else obj.text[:87] + '...'


class AnswerInline(admin.TabularInline):
    model = Answer
    extra = 0
    fields = ('question', 'choice', 'changes', 'answered_at', 'updated_at')
    readonly_fields = fields
    can_delete = False


@admin.register(Attempt)
class AttemptAdmin(admin.ModelAdmin):
    list_display = ('user', 'exam', 'status', 'correct_count', 'score', 'leave_count', 'fullscreen_exits',
                    'started_at', 'finished_at', 'finish_reason')
    list_filter = ('exam', 'status', 'finish_reason')
    search_fields = ('user__username', 'user__first_name', 'user__last_name')
    list_select_related = ('user', 'exam')
    readonly_fields = ('question_order', 'choice_order', 'device_hash', 'ip_address', 'user_agent',
                       'last_seen_at', 'event_count', 'started_at', 'finished_at', 'correct_count', 'score')
    inlines = [AnswerInline]
    actions = ['regrade_selected']

    @admin.action(description="Tanlangan urinishlar natijasini qayta hisoblash")
    def regrade_selected(self, request, queryset):
        for attempt in queryset.select_related('exam'):
            services.regrade(attempt)
        messages.success(request, "Natijalar qayta hisoblandi.")


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'user', 'exam', 'kind', 'level', 'message', 'ip_address')
    list_filter = ('level', 'kind', 'exam')
    search_fields = ('user__username', 'message')
    list_select_related = ('user', 'exam')
    readonly_fields = ('attempt', 'exam', 'user', 'kind', 'level', 'message', 'data', 'ip_address', 'created_at')

    def has_add_permission(self, request):
        return False


@admin.register(LoginAttempt)
class LoginAttemptAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'login', 'success', 'ip_address')
    list_filter = ('success',)
    search_fields = ('login',)
    readonly_fields = ('login', 'success', 'ip_address', 'user_agent', 'created_at')

    def has_add_permission(self, request):
        return False
