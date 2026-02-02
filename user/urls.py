from django.urls import path
from django.contrib.auth.decorators import login_required
from . import views

app_name = "user"

urlpatterns = [
    # Main pages
    path('', views.index, name='index'), 
    path('register/', views.register_view, name='register'),
    
    # Authentication views
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'), # <-- NEW LOGOUT URL
    path('forgot-password/', views.forgot_password_view, name='forgot_password'),
]