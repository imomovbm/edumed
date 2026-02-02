from django.db import models
from django.contrib.auth.models import User

# Create your models here.

class TopicComment(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    topic_id = models.IntegerField()
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    # New field for upvotes
    likes = models.ManyToManyField(User, related_name='comment_likes', blank=True)

    def total_likes(self):
        return self.likes.count()

    def __str__(self):
        return f"{self.user.username} - {self.topic_id}"