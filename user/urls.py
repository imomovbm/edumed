from django.urls import path
from . import views

app_name = "user"

urlpatterns = [
    # Main pages
    path('', views.index, name='index'),
    path('register/', views.register_view, name='register'),
    path('settings/', views.settings_view, name='settings'),
    path('ai-analysis/', views.ai_analysis_view, name='ai_analysis'),

    # Authentication views
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('forgot-password/', views.forgot_password_view, name='forgot_password'),

    # Administration
    path('all-users/', views.all_users_view, name='all_users'),
    path('reset-requests/<int:request_id>/resolve/', views.resolve_reset_request_view, name='resolve_reset_request'),
    path('delete/<int:user_id>/', views.delete_user_view, name='delete_user'),
    path('<int:user_id>/', views.user_detail_view, name='user_detail'),
    path('<int:user_id>/role/', views.change_role_view, name='change_role'),
    path('<int:user_id>/reset-password/', views.reset_password_view, name='reset_password'),
    path('<int:user_id>/ai-analysis/', views.ai_analysis_view, name='user_ai_analysis'),
]
