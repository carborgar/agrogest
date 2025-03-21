from django.urls import path

from . import api_views
from . import views
from .views import TaskListView, TaskDetailView

urlpatterns = [
    path("", views.FieldListView.as_view(), name="field_list"),  # Listado de parcelas
    path('tareas/', TaskListView.as_view(), name='task_list'),  # Listado de tareas
    path('tarea/<int:pk>', TaskDetailView.as_view(), name='task_detail'),  # Detalle de tarea
    # path('tarea/nueva/', views.create_task, name='create_task'),
    path('tarea/nueva/', views.TaskFormView.as_view(), name='create_task'),
    path('tarea/editar/<int:pk>', views.TaskFormView.as_view(), name='edit_task'),

    # API Endpoints
    path('api/fields/', api_views.get_fields, name='api_fields'),
    path('api/machines/', api_views.get_machines, name='api_machines'),
    path('api/products/', api_views.get_products, name='api_products')

]
