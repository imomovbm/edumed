from django.contrib import admin
from .models import (
    Topic, TopicSection, TopicSectionItem, TopicProgress, TopicComment,
    Question, QuestionChoice,
    Quiz, QuizQuestion,
    Response, ResponseDetails,
    Forum, ForumComment,
)


@admin.register(TopicComment)
class TopicCommentAdmin(admin.ModelAdmin):
    list_display = ('user', 'topic', 'text_excerpt', 'total_likes_count', 'created_at')
    list_filter = ('created_at', 'topic')
    search_fields = ('user__username', 'text')
    readonly_fields = ('created_at',)
    list_select_related = ('user', 'topic')

    def text_excerpt(self, obj):
        return obj.text[:50] + "..." if len(obj.text) > 50 else obj.text
    text_excerpt.short_description = "Fikr matni"

    def total_likes_count(self, obj):
        return obj.likes.count()
    total_likes_count.short_description = "Likes"


class TopicSectionInline(admin.TabularInline):
    model = TopicSection
    extra = 0
    fields = ('order', 'type', 'title')
    ordering = ('order',)
    show_change_link = True


@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'icon', 'created_by', 'created_at')
    search_fields = ('title', 'description')
    inlines = [TopicSectionInline]


class TopicSectionItemInline(admin.StackedInline):
    model = TopicSectionItem
    extra = 0
    fields = ('order', 'label', 'text', 'sub_text')
    ordering = ('order',)


@admin.register(TopicSection)
class TopicSectionAdmin(admin.ModelAdmin):
    list_display = ('topic', 'order', 'type', 'title')
    list_filter = ('type', 'topic')
    inlines = [TopicSectionItemInline]


@admin.register(TopicProgress)
class TopicProgressAdmin(admin.ModelAdmin):
    list_display = ('user', 'topic', 'status', 'progress', 'enrolled_date')
    list_filter = ('status', 'topic')
    search_fields = ('user__username', 'topic__title')
    list_select_related = ('user', 'topic')


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
    list_display = ('id', 'title', 'type', 'topic', 'duration', 'question_count')
    list_filter = ('type', 'topic')
    search_fields = ('title',)
    inlines = [QuizQuestionInline]

    def question_count(self, obj):
        return obj.quizquestion_set.count()
    question_count.short_description = "Savollar soni"


class ResponseDetailsInline(admin.TabularInline):
    model = ResponseDetails
    extra = 0
    fields = ('question', 'question_choice', 'user_text_answer', 'is_correct', 'feedback')
    readonly_fields = ('question', 'question_choice', 'user_text_answer')
    can_delete = False


@admin.register(Response)
class ResponseAdmin(admin.ModelAdmin):
    list_display = ('user', 'quiz', 'score', 'correct_count', 'incorrect_count',
                    'skipped_count', 'violation_count', 'created_date_time')
    list_filter = ('quiz',)
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'quiz__title')
    readonly_fields = ('created_date_time',)
    list_select_related = ('user', 'quiz')
    inlines = [ResponseDetailsInline]


class ForumCommentInline(admin.TabularInline):
    model = ForumComment
    extra = 0
    fields = ('user', 'text', 'parent', 'created_at')
    readonly_fields = ('created_at',)
    raw_id_fields = ('user', 'parent')


@admin.register(Forum)
class ForumAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'user', 'topic', 'created_at')
    list_filter = ('topic', 'created_at')
    search_fields = ('title', 'forum_question', 'user__username')
    list_select_related = ('user', 'topic')
    raw_id_fields = ('user',)
    filter_horizontal = ('likes', 'dislikes')
    inlines = [ForumCommentInline]


@admin.register(ForumComment)
class ForumCommentAdmin(admin.ModelAdmin):
    list_display = ('id', 'forum', 'user', 'text_excerpt', 'parent', 'created_at')
    search_fields = ('text', 'user__username', 'forum__title')
    list_select_related = ('forum', 'user')
    raw_id_fields = ('user', 'forum', 'parent')
    filter_horizontal = ('likes', 'dislikes')

    def text_excerpt(self, obj):
        return obj.text[:60] + "..." if len(obj.text) > 60 else obj.text
    text_excerpt.short_description = "Izoh"
