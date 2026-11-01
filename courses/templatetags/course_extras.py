# courses/templatetags/course_extras.py
from django import template
from django.templatetags.static import static

register = template.Library()

DEFAULT_AVATAR = 'img/avatar.png'


@register.filter
def get_item(dictionary, key):
    """Allows dict[variable] lookup in templates: {{ dict|get_item:key }}"""
    if hasattr(dictionary, 'get'):
        return dictionary.get(key)
    return None


@register.filter
def avatar_url(profile):
    """Avatar of a UserProfile (``avatar`` may be a full URL, an absolute path or a
    static path). Falls back to the default picture."""
    url = (getattr(profile, 'avatar', None) or '').strip()
    if not url:
        return static(DEFAULT_AVATAR)
    if url.startswith(('http://', 'https://', '/')):
        return url
    return static(url)


@register.filter
def progress_pct(progress):
    """0-100 integer for a TopicProgress (None = not started)."""
    from courses.grading import progress_percent
    return progress_percent(progress or None)


@register.filter
def score_color(score):
    """Bootstrap colour name for a percentage score (matches the badges used everywhere)."""
    try:
        score = float(score)
    except (TypeError, ValueError):
        return 'secondary'
    if score >= 90:
        return 'success'
    if score >= 70:
        return 'primary'
    if score >= 50:
        return 'warning'
    return 'danger'
