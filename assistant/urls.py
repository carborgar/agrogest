from django.urls import path

from assistant import views

urlpatterns = [
    path('asistente/', views.AssistantView.as_view(), name='assistant'),
]
