from django.urls import path

from . import api_views
from . import views
from .views import *
from django.views.generic import RedirectView

urlpatterns = [
    path("", RedirectView.as_view(url="/parcelas/vistazo/", permanent=False), name="home"),
    path("parcelas/vistazo/", FieldListView.as_view(), name="field_list"),
    path("parcelas/gastos/", FieldCostView.as_view(), name="field_costs"),
    path('tratamientos/', TreatmentListView.as_view(), name='treatment-list'),
    path('tratamientos/<int:pk>', TreatmentDetailView.as_view(), name='treatment-detail'),
    path('tratamientos/nuevo/', TreatmentFormView.as_view(), name='treatment-create'),
    # path('tratamientos/<int:pk>/editar/', TreatmentFormView.as_view(), name='treatment-update'),
    path('tratamientos/<int:pk>/finalizar', FinishTreatmentView.as_view(), name='treatment-finish'),
    path('tratamientos/<int:pk>/eliminar/', DeleteTreatmentView.as_view(), name='treatment-delete'),
    path('tratamientos/calendario/', TreatmentCalendarView.as_view(), name='treatment-calendar'),
    path('tratamientos/<int:pk>/operador/', TreatmentExportView.as_view(), name='treatment-instructions'),
    path('tratamientos/lista-compra/', ShoppingListView.as_view(), name='treatment-shopping-list'),

    # API Endpoints
    path('api/fields/', api_views.get_fields, name='api-fields'),
    path('api/machines/', api_views.get_machines, name='api-machines'),
    path('api/products/<str:application_type>/', api_views.get_products, name='api-products'),
    path('api/treatments/', api_views.get_calendar_treatments, name='api-calendar-treatments'),
    path('api/treatments/<int:treatment_id>/', api_views.treatment_detail, name='api-treatment-detail'),
    path('api/field-costs-data/', api_views.field_costs_data, name='api-field-costs-data'),

]
