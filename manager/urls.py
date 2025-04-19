from django.urls import path
from . import views

urlpatterns = [
    path('', views.manager, name='manager'),
]