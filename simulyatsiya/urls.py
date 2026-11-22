from django.urls import path

from . import views

app_name = 'simulyatsiya'

urlpatterns = [
    path('', views.index_view, name='index'),
    path('<slug:simulation_id>/', views.detail_view, name='detail'),
    path('<slug:simulation_id>/oyna/', views.frame_view, name='frame'),
]
