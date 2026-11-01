# courses/management/commands/recalculate_scores.py
#
#   python manage.py recalculate_scores --dry-run   # show what would change
#   python manage.py recalculate_scores             # apply
#
# Fixes results saved by the old grader:
#   * true/false answers were always marked as wrong (score too low),
#   * multi-select answers were stored without is_correct,
# and recomputes every student's topic progress with the current rules.

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction

from courses.grading import regrade_legacy_response, update_topic_progress
from courses.models import Quiz, Response, Topic, TopicProgress


class Command(BaseCommand):
    help = "Re-grade old quiz results (true/false bug) and recompute topic progress."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help="Only report the changes; nothing is saved.",
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        with transaction.atomic():
            regraded = 0
            candidates = (
                Response.objects
                .filter(responsedetails__question__type__in=['tf', 'ms'])
                .distinct().order_by('id')
            )
            for response in candidates.iterator(chunk_size=200):
                before = response.score
                if regrade_legacy_response(response):
                    regraded += 1
                    if response.score != before:
                        self.stdout.write(
                            f"  natija #{response.pk} ({response.user}): {before}% -> {response.score}%"
                        )

            # Recompute progress for every (student, topic) that has quizzes.
            topics_with_quizzes = set(
                Quiz.objects.filter(topic__isnull=False).values_list('topic_id', flat=True)
            )
            pairs = set(
                Response.objects.filter(quiz__topic__isnull=False)
                .values_list('user_id', 'quiz__topic_id')
            )
            pairs |= set(
                TopicProgress.objects.filter(topic_id__in=topics_with_quizzes)
                .values_list('user_id', 'topic_id')
            )
            users = User.objects.in_bulk({u for u, _ in pairs})
            topics = Topic.objects.in_bulk({t for _, t in pairs})
            for user_id, topic_id in sorted(pairs):
                if user_id in users and topic_id in topics:
                    update_topic_progress(users[user_id], topics[topic_id])

            summary = (
                f"{regraded} ta natija qayta baholandi, "
                f"{len(pairs)} ta mavzu progressi qayta hisoblandi."
            )
            if dry_run:
                transaction.set_rollback(True)
                self.stdout.write(self.style.WARNING(f"[dry-run] {summary} Hech narsa saqlanmadi."))
            else:
                self.stdout.write(self.style.SUCCESS(summary))
