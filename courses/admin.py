from django.contrib import admin
from .models import (
    Topic, TopicProgress, TopicComment,
    Question, QuestionChoice,
    Quiz, QuizQuestion,
    Response, ResponseDetails
)

@admin.register(TopicComment)
class TopicCommentAdmin(admin.ModelAdmin):
    list_display = ('user', 'topic_id', 'text_excerpt', 'total_likes_count', 'created_at')
    list_filter = ('created_at', 'topic')
    search_fields = ('user__username', 'text')
    readonly_fields = ('created_at',)

    def text_excerpt(self, obj):
        return obj.text[:50] + "..." if len(obj.text) > 50 else obj.text
    text_excerpt.short_description = "Fikr matni"

    def total_likes_count(self, obj):
        return obj.likes.count()
    total_likes_count.short_description = "Likes"


@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = ('id', 'title')
    search_fields = ('title',)


@admin.register(TopicProgress)
class TopicProgressAdmin(admin.ModelAdmin):
    list_display = ('user', 'topic', 'status', 'enrolled_date')
    list_filter = ('status',)
    search_fields = ('user__username', 'topic__title')


class QuestionChoiceInline(admin.TabularInline):
    model = QuestionChoice
    extra = 4
    fields = ('choice_text', 'is_correct')


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('id', 'question_excerpt', 'type', 'created_at')
    list_filter = ('type',)                  # now filters by the field directly
    search_fields = ('question_text',)
    readonly_fields = ('created_at',)
    inlines = [QuestionChoiceInline]

    def question_excerpt(self, obj):
        return obj.question_text[:80] + "..." if len(obj.question_text) > 80 else obj.question_text
    question_excerpt.short_description = "Savol matni"


class QuizQuestionInline(admin.TabularInline):
    model = QuizQuestion
    extra = 1
    fields = ('question', 'order')
    ordering = ('order',)
    # autocomplete_fields needs search_fields on the target admin (QuestionAdmin has it ✅)
    autocomplete_fields = ('question',)


@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'type', 'topic', 'question_count')
    list_filter = ('type', 'topic')
    search_fields = ('title',)
    inlines = [QuizQuestionInline]

    def question_count(self, obj):
        return obj.quizquestion_set.count()
    question_count.short_description = "Savollar soni"


class ResponseDetailsInline(admin.TabularInline):
    model = ResponseDetails
    extra = 0
    readonly_fields = ('question', 'question_choice', 'user_text_answer')
    can_delete = False


@admin.register(Response)
class ResponseAdmin(admin.ModelAdmin):
    list_display = ('user', 'quiz', 'score', 'created_date_time')
    list_filter = ('quiz',)
    search_fields = ('user__username', 'quiz__title')
    readonly_fields = ('created_date_time',)
    inlines = [ResponseDetailsInline]