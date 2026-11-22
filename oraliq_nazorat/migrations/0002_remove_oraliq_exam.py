"""Retire the finished oraliq exam.

1. Export its results, answers, events and accounts to oraliq_eksport_<date>/
   (BASE_DIR, or the folder in the ORALIQ_EXPORT_DIR environment variable).
2. Delete the exam's student accounts (student<N>@mail.uz with an oraliq attempt).
3. Drop the old tables.

Step 1 runs before anything is deleted; if it fails, the migration stops.
Back up the database before running ``migrate`` (see README).
"""
import sys

from django.conf import settings
from django.db import migrations

STUDENT_LOGIN = r'^student[0-9]+@mail[.]uz$'


def export_and_delete_students(apps, schema_editor):
    from oraliq_nazorat.export import default_export_dir, export_oraliq

    Attempt = apps.get_model('oraliq_nazorat', 'Attempt')
    if not Attempt.objects.exists():
        return  # a fresh database: nothing to keep
    out_dir = default_export_dir()
    counts = export_oraliq(apps, out_dir)
    sys.stdout.write(f"\n  Eski oraliq nazorat maʼlumotlari saqlandi: {out_dir} ({counts['natijalar.csv']} natija)\n")

    User = apps.get_model(settings.AUTH_USER_MODEL)
    student_ids = Attempt.objects.filter(
        user__username__regex=STUDENT_LOGIN, user__is_staff=False, user__is_superuser=False,
    ).values_list('user_id', flat=True)
    accounts = User.objects.filter(pk__in=list(student_ids))
    deleted = accounts.count()
    accounts.delete()
    sys.stdout.write(f"  Oraliq nazorat talabalari hisoblari oʻchirildi: {deleted} ta\n")


class Migration(migrations.Migration):

    dependencies = [
        ("oraliq_nazorat", "0001_initial"),
        # Everything that can point at a user, so deleting the accounts cascades cleanly.
        ("admin", "0003_logentry_add_action_flag_choices"),
        ("courses", "0014_quiz_duration_violations_feedback"),
        ("user", "0005_ai_analysis_reset_resolved"),
    ]

    operations = [
        migrations.RunPython(export_and_delete_students, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name="answer",
            name="on_answer_one_per_question",
        ),
        migrations.RemoveConstraint(
            model_name="attempt",
            name="on_attempt_one_per_user",
        ),
        migrations.RemoveField(
            model_name="choice",
            name="question",
        ),
        migrations.RemoveIndex(
            model_name="event",
            name="on_event_attempt_time",
        ),
        migrations.DeleteModel(
            name="LoginAttempt",
        ),
        migrations.RemoveConstraint(
            model_name="question",
            name="on_question_unique_ref",
        ),
        migrations.RemoveConstraint(
            model_name="variant",
            name="on_variant_unique_number",
        ),
        migrations.RemoveConstraint(
            model_name="variantquestion",
            name="on_vq_unique_question",
        ),
        migrations.RemoveConstraint(
            model_name="variantquestion",
            name="on_vq_unique_order",
        ),
        migrations.RemoveField(
            model_name="answer",
            name="attempt",
        ),
        migrations.RemoveField(
            model_name="answer",
            name="choice",
        ),
        migrations.RemoveField(
            model_name="answer",
            name="question",
        ),
        migrations.RemoveField(
            model_name="attempt",
            name="exam",
        ),
        migrations.RemoveField(
            model_name="attempt",
            name="user",
        ),
        migrations.RemoveField(
            model_name="attempt",
            name="variant",
        ),
        migrations.RemoveField(
            model_name="event",
            name="attempt",
        ),
        migrations.RemoveField(
            model_name="event",
            name="user",
        ),
        migrations.RemoveField(
            model_name="question",
            name="exam",
        ),
        migrations.RemoveField(
            model_name="variant",
            name="exam",
        ),
        migrations.RemoveField(
            model_name="variant",
            name="questions",
        ),
        migrations.RemoveField(
            model_name="variantquestion",
            name="question",
        ),
        migrations.RemoveField(
            model_name="variantquestion",
            name="variant",
        ),
        migrations.DeleteModel(
            name="Choice",
        ),
        migrations.DeleteModel(
            name="Answer",
        ),
        migrations.DeleteModel(
            name="Attempt",
        ),
        migrations.DeleteModel(
            name="Event",
        ),
        migrations.DeleteModel(
            name="Exam",
        ),
        migrations.DeleteModel(
            name="Question",
        ),
        migrations.DeleteModel(
            name="Variant",
        ),
        migrations.DeleteModel(
            name="VariantQuestion",
        ),
    ]
