"""
URL configuration for edumed project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from . import views


from django.http import HttpResponse
from django.conf import settings
from django.conf.urls.static import static
from django.views.decorators.http import require_GET
import os

@require_GET
def service_worker(request):
    sw_path = os.path.join(settings.BASE_DIR, 'static', 'service-worker.js')
    with open(sw_path, 'r') as f:
        return HttpResponse(f.read(), content_type='application/javascript')

urlpatterns = [
    path('service-worker.js', service_worker),
    path('', views.index, name="index"),
    path('admin/', admin.site.urls),
    path('courses/', include('courses.urls')),
    path('user/', include('user.urls')),
]
