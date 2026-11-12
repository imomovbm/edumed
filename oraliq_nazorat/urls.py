from django.urls import path

from . import views

app_name = 'oraliq_nazorat'

urlpatterns = [
    # Students
    path('', views.login_view, name='login'),
    path('chiqish/', views.logout_view, name='logout'),
    path('imtihon/', views.exam_view, name='exam'),
    path('natija/', views.result_view, name='result'),

    # Exam page API (JSON)
    path('api/holat/', views.api_status, name='api_status'),
    path('api/boshlash/', views.api_start, name='api_start'),
    path('api/davom/', views.api_resume, name='api_resume'),
    path('api/javob/', views.api_answer, name='api_answer'),
    path('api/hodisa/', views.api_event, name='api_event'),
    path('api/ping/', views.api_ping, name='api_ping'),
    path('api/yakunlash/', views.api_finish, name='api_finish'),

    # Proctors (teachers / administrators)
    path('nazorat/', views.dashboard_view, name='dashboard'),
    path('nazorat/data/', views.dashboard_data, name='dashboard_data'),
    path('nazorat/natijalar.csv', views.export_csv_view, name='export_csv'),
    path('nazorat/imtihon/<int:exam_id>/holat/', views.exam_toggle_view, name='exam_toggle'),
    path('nazorat/urinish/<int:pk>/', views.attempt_detail_view, name='attempt_detail'),
    path('nazorat/urinish/<int:pk>/amal/', views.attempt_action_view, name='attempt_action'),
]
