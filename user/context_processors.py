from .permissions import can_grade, can_moderate, get_profile, is_admin


def user_profile(request):
    user = getattr(request, 'user', None)
    profile = get_profile(user) if user is not None else None
    grader = bool(profile) and can_grade(user)

    pending_grading = 0
    if grader:
        # Imported lazily: the courses app depends on the user app, not the other way round.
        from courses.grading import pending_text_answers
        pending_grading = pending_text_answers().values('response_id').distinct().count()

    return {
        'user_profile': profile,
        'unread_count': 0,  # later: Notification.objects.filter(user=request.user, read=False).count()
        'is_admin': bool(profile) and is_admin(user),
        'can_grade': grader,
        'can_moderate': bool(profile) and can_moderate(user),
        'pending_grading_count': pending_grading,
    }
