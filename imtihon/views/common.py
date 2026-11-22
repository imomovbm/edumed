import json
from functools import wraps

from django.http import JsonResponse
from django.http.request import RawPostDataException
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import urlencode
from django.views.decorators.cache import never_cache

from user.permissions import can_grade

from ..services import ExamError

DEVICE_MESSAGE = "Bu test boshqa kompyuter yoki brauzerda boshlangan. Nazoratchiga murojaat qiling."


def is_proctor(user):
    return getattr(user, 'is_authenticated', False) and can_grade(user)


def student_login_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('imtihon:login')
        return view(request, *args, **kwargs)
    return wrapper


def proctor_required(view):
    """Teachers and administrators only (403 for everyone else who is signed in)."""
    @wraps(view)
    @never_cache
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(reverse('imtihon:login') + '?' + urlencode({'next': request.get_full_path()}))
        if not can_grade(request.user):
            return render(request, 'imtihon/forbidden.html', status=403)
        return view(request, *args, **kwargs)
    return wrapper


def json_body(request):
    """The JSON payload of an API call. ``navigator.sendBeacon`` (used while the page
    is closing) cannot set headers, so it posts a form with the CSRF token and the
    JSON in a ``payload`` field instead."""
    if request.content_type in ('application/x-www-form-urlencoded', 'multipart/form-data'):
        raw = request.POST.get('payload') or '{}'
    else:
        try:
            raw = request.body or b'{}'
        except RawPostDataException:
            raw = request.POST.get('payload') or '{}'
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError, TypeError):
        data = None
    return data if isinstance(data, dict) else {}


def error(code, message, status=400, **extra):
    return JsonResponse({'ok': False, 'error': code, 'message': message, **extra}, status=status)


def api_view(methods=('POST',)):
    """JSON endpoint of a signed-in user; ExamError becomes a JSON error."""
    def decorator(view):
        @wraps(view)
        @never_cache
        def wrapper(request, *args, **kwargs):
            if request.method not in methods:
                return error('method', "Notoʻgʻri soʻrov.", status=405)
            if not request.user.is_authenticated:
                return error('auth', "Sessiya tugagan. Qayta kiring.", status=401,
                             redirect=reverse('imtihon:login'))
            try:
                return view(request, *args, **kwargs)
            except ExamError as exc:
                return error(exc.code, exc.message, status=403)
        return wrapper
    return decorator
