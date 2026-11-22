"""
URL configuration for edumed project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/stable/topics/http/urls/
"""
from django.conf import settings
from django.contrib import admin
from django.http import Http404, HttpResponse
from django.urls import include, path
from django.views.decorators.http import require_GET

from . import views


@require_GET
def service_worker(request):
    sw_path = settings.BASE_DIR / 'static' / 'service-worker.js'
    try:
        content = sw_path.read_text(encoding='utf-8')
    except OSError:
        raise Http404("service-worker.js not found")
    return HttpResponse(content, content_type='application/javascript')


urlpatterns = [
    path('service-worker.js', service_worker),
    path('', views.index, name="index"),
    path('admin/', admin.site.urls),
    path('courses/', include('courses.urls')),
    path('user/', include('user.urls')),
]
