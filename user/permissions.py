"""Role helpers shared by every app.

Roles live on ``UserProfile.role``. A Django superuser (``is_superuser``) is always
treated as an administrator, so the site keeps working for accounts created with
``createsuperuser``.
"""
from functools import wraps

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme

from .models import UserProfile

ADMIN_ROLES = ('superadmin',)
# Teachers check short/essay answers ("o'qituvchi tomonidan tekshiriladi").
GRADER_ROLES = ('superadmin', 'teacher')
# Moderators can remove forum posts and comments.
MODERATOR_ROLES = ('superadmin', 'moder')

NO_ACCESS_MESSAGE = "Sizda bu sahifaga kirish huquqi yo'q."


def get_profile(user):
    """Return the user's profile (or None).

    A superuser without a profile gets a 'superadmin' profile on first use, so
    the in-site admin panel is reachable right after ``createsuperuser``.
    """
    if not getattr(user, 'is_authenticated', False):
        return None
    try:
        return user.userprofile
    except UserProfile.DoesNotExist:
        if user.is_superuser:
            return UserProfile.objects.create(user=user, role='superadmin')
        return None


def has_role(user, *roles):
    if not getattr(user, 'is_authenticated', False):
        return False
    if user.is_superuser:
        return True
    profile = get_profile(user)
    return bool(profile and profile.role in roles)


def is_admin(user):
    return has_role(user, *ADMIN_ROLES)


def can_grade(user):
    return has_role(user, *GRADER_ROLES)


def can_moderate(user):
    return has_role(user, *MODERATOR_ROLES)


def safe_next_url(request):
    """The ?next= / next= target when it points to this site, otherwise None."""
    target = request.POST.get('next') or request.GET.get('next')
    if target and url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure(),
    ):
        return target
    return None


def _wants_json(request):
    return (
        request.headers.get('x-requested-with') == 'XMLHttpRequest'
        or 'application/json' in request.headers.get('accept', '')
        or request.content_type == 'application/json'
    )


def require_profile(view_func):
    """Only users that have a UserProfile may continue (use after login_required)."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not get_profile(request.user):
            if _wants_json(request):
                return JsonResponse({'error': 'profile_required'}, status=403)
            messages.error(request, "Profilingiz topilmadi. Iltimos, administratorga murojaat qiling.")
            return redirect('courses:index')
        return view_func(request, *args, **kwargs)
    return wrapper


def role_required(*roles):
    """Allow the view only for the given roles (superusers always pass)."""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not has_role(request.user, *roles):
                if _wants_json(request):
                    return JsonResponse({'error': 'forbidden'}, status=403)
                messages.error(request, NO_ACCESS_MESSAGE)
                return redirect('courses:index')
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


admin_required = role_required(*ADMIN_ROLES)
grader_required = role_required(*GRADER_ROLES)
