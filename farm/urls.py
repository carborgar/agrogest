from django.urls import path
from django.views.generic import RedirectView

from farm.views.views import FieldDashboardView, FieldCostView, TreatmentListView, TreatmentDetailView, \
    TreatmentFormView, FinishTreatmentView, DeleteTreatmentView, TreatmentCalendarView, \
    TreatmentExportView, ShoppingListView
from . import api_views
from .views.expense_views import ExpenseListView, ExpenseFormView, ExpenseDeleteView, ExpenseTypeListView, \
    ExpenseTypeFormView, ExpenseTypeDeleteView
from .views.field_views import FieldListView, FieldCreateView, FieldUpdateView, FieldDeleteView

urlpatterns = [
    path("", RedirectView.as_view(url="/parcelas/vistazo/", permanent=False), name="home"),
    path("parcelas/vistazo/", FieldDashboardView.as_view(), name="field_list"),
    path("parcelas/gastos/", FieldCostView.as_view(), name="field-costs"),
    path('tratamientos/', TreatmentListView.as_view(), name='treatment-list'),
    path('tratamientos/<int:pk>', TreatmentDetailView.as_view(), name='treatment-detail'),
    path('tratamientos/nuevo/', TreatmentFormView.as_view(), name='treatment-create'),
    # path('tratamientos/<int:pk>/editar/', TreatmentFormView.as_view(), name='treatment-update'),
    path('tratamientos/<int:pk>/finalizar', FinishTreatmentView.as_view(), name='treatment-finish'),
    path('tratamientos/<int:pk>/eliminar/', DeleteTreatmentView.as_view(), name='treatment-delete'),
    path('tratamientos/calendario/', TreatmentCalendarView.as_view(), name='treatment-calendar'),
    path('tratamientos/<int:pk>/operador/', TreatmentExportView.as_view(), name='treatment-instructions'),
    path('tratamientos/lista-compra/', ShoppingListView.as_view(), name='treatment-shopping-list'),

    path('adm/field/', FieldListView.as_view(), name='field-list'),
    path('adm/field/create/', FieldCreateView.as_view(), name='field-create'),
    path('adm/field/<int:pk>/edit/', FieldUpdateView.as_view(), name='field-edit'),
    path('adm/field/<int:pk>/delete/', FieldDeleteView.as_view(), name='field-delete'),

    # Expense Management
    path('gastos/gestionar/', ExpenseListView.as_view(), name='expense-list'),
    path('gastos/nuevo/', ExpenseFormView.as_view(), name='expense-create'),
    path('gastos/<int:pk>/editar/', ExpenseFormView.as_view(), name='expense-edit'),
    path('gastos/<int:pk>/eliminar/', ExpenseDeleteView.as_view(), name='expense-delete'),

    # Expense Type Management
    path('gastos/tipos/', ExpenseTypeListView.as_view(), name='expense-type-list'),
    path('gastos/tipos/nuevo/', ExpenseTypeFormView.as_view(), name='expense-type-create'),
    path('gastos/tipos/<int:pk>/editar/', ExpenseTypeFormView.as_view(), name='expense-type-edit'),
    path('gastos/tipos/<int:pk>/eliminar/', ExpenseTypeDeleteView.as_view(), name='expense-type-delete'),

    # API Endpoints
    path('api/fields/', api_views.get_fields, name='api-fields'),
    path('api/machines/', api_views.get_machines, name='api-machines'),
    path('api/products/<str:application_type>/', api_views.get_products, name='api-products'),
    path('api/treatments/', api_views.get_calendar_treatments, name='api-calendar-treatments'),
    path('api/treatments/<int:treatment_id>/', api_views.treatment_detail, name='api-treatment-detail'),
    path('api/field-costs-data/', api_views.field_costs_data, name='api-field-costs-data'),

]
