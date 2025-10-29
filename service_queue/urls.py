from django.urls import path
from . import views

urlpatterns = [
    path('', views.service_queue, name='service_queue'),
]