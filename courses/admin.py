
# Register your models here.
from django.contrib import admin
from .models import TopicComment

# --- 1. User & Profile Management ---

# --- 2. Topic Comments & Upvotes ---
@admin.register(TopicComment)
class TopicCommentAdmin(admin.ModelAdmin):
    # Shows who commented, on what topic, and how many likes they got
    list_display = ('user', 'topic_id', 'text_excerpt', 'total_likes_count', 'created_at')
    list_filter = ('created_at', 'topic_id')
    search_fields = ('user__username', 'text')
    readonly_fields = ('created_at',)

    def text_excerpt(self, obj):
        return obj.text[:50] + "..." if len(obj.text) > 50 else obj.text
    text_excerpt.short_description = "Fikr matni"

    def total_likes_count(self, obj):
        return obj.likes.count()
    total_likes_count.short_description = "Likes"
