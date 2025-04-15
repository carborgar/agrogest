from django.urls import path

from . import api_views
from . import views
from .views import TreatmentListView, TreatmentDetailView

urlpatterns = [
    path("", views.FieldListView.as_view(), name="field_list"),
    path('tratamientos/', TreatmentListView.as_view(), name='treatment-list'),
    path('tratamientos/<int:pk>', TreatmentDetailView.as_view(), name='treatment-detail'),
    path('tratamientos/nuevo/', views.TreatmentFormView.as_view(), name='treatment-create'),
    # path('tratamientos/<int:pk>/editar/', views.TreatmentFormView.as_view(), name='treatment-update'),
    path('tratamientos/<int:pk>/finalizar', views.finish_treatment, name='treatment-finish'),
    path('tratamientos/<int:pk>/eliminar/', views.delete_treatment, name='treatment-delete'),
    path('tratamientos/calendario/', views.treatment_calendar, name='treatment-calendar'),

    # API Endpoints
    path('api/fields/', api_views.get_fields, name='api-fields'),
    path('api/machines/', api_views.get_machines, name='api-machines'),
    path('api/products/<str:application_type>/', api_views.get_products, name='api-products'),
    path('api/treatments/', api_views.get_calendar_tasks, name='api-calendar-treatments'),
    path('api/treatments/<int:task_id>/', api_views.treatment_detail, name='api-treatment-detail'),

]
