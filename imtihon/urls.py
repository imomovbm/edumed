from django.urls import path

from .views import manage, people, student

app_name = 'imtihon'

urlpatterns = [
    # Students. The login page is the root of the app: the device cookie is scoped to it.
    path('', student.login_view, name='login'),
    path('chiqish/', student.logout_view, name='logout'),
    path('imtihonlarim/', student.my_exams_view, name='my_exams'),
    path('<int:exam_id>/', student.exam_view, name='exam'),
    path('<int:exam_id>/natija/', student.result_view, name='result'),

    # Exam page API (JSON)
    path('<int:exam_id>/api/holat/', student.api_status, name='api_status'),
    path('<int:exam_id>/api/boshlash/', student.api_start, name='api_start'),
    path('<int:exam_id>/api/davom/', student.api_resume, name='api_resume'),
    path('<int:exam_id>/api/javob/', student.api_answer, name='api_answer'),
    path('<int:exam_id>/api/hodisa/', student.api_event, name='api_event'),
    path('<int:exam_id>/api/ping/', student.api_ping, name='api_ping'),
    path('<int:exam_id>/api/yakunlash/', student.api_finish, name='api_finish'),

    # Teachers and administrators: exams
    path('boshqaruv/', manage.exams_view, name='manage'),
    path('boshqaruv/import/', manage.import_view, name='manage_import'),
    path('boshqaruv/<int:exam_id>/', manage.exam_view, name='manage_exam'),
    path('boshqaruv/<int:exam_id>/import/', manage.import_view, name='manage_reimport'),
    path('boshqaruv/<int:exam_id>/holat/', manage.exam_status_view, name='manage_exam_status'),
    path('boshqaruv/<int:exam_id>/ochirish/', manage.exam_delete_view, name='manage_exam_delete'),
    path('boshqaruv/<int:exam_id>/kuzatuv/', manage.dashboard_view, name='manage_dashboard'),
    path('boshqaruv/<int:exam_id>/kuzatuv/data/', manage.dashboard_data_view, name='manage_dashboard_data'),
    path('boshqaruv/<int:exam_id>/natijalar.<str:fmt>', manage.export_view, name='manage_export'),
    path('boshqaruv/urinish/<int:pk>/', manage.attempt_view, name='manage_attempt'),
    path('boshqaruv/urinish/<int:pk>/amal/', manage.attempt_action_view, name='manage_attempt_action'),

    # Teachers and administrators: students and groups
    path('boshqaruv/talabalar/', people.students_view, name='manage_students'),
    path('boshqaruv/talabalar/<int:user_id>/', people.student_edit_view, name='manage_student'),
    path('boshqaruv/talabalar/<int:user_id>/ochirish/', people.student_delete_view, name='manage_student_delete'),
    path('boshqaruv/guruhlar/', people.groups_view, name='manage_groups'),
    path('boshqaruv/guruhlar/<int:group_id>/', people.group_edit_view, name='manage_group'),
    path('boshqaruv/guruhlar/<int:group_id>/ochirish/', people.group_delete_view, name='manage_group_delete'),
]
