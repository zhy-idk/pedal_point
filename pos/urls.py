from django.urls import path
from . import views

urlpatterns = [
    path('', views.pos, name='pos'),
]