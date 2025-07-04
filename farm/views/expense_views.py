from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView

from farm.forms import ExpenseForm
from farm.mixins import OwnershipRequiredMixin, QuerysetFilterMixin, AuditableMixin
from farm.models import Expense, Field, ExpenseType


class BaseSecureExpenseViewMixin(OwnershipRequiredMixin, QuerysetFilterMixin):
    """Mixin base que aplica control de acceso y filtrado para gastos."""
    pass


class BaseSecureExpenseFormMixin(BaseSecureExpenseViewMixin, AuditableMixin):
    """Mixin para vistas de formularios de gastos que incluye auditoría."""
    pass


class ExpenseListView(BaseSecureExpenseViewMixin, ListView):
    model = Expense
    template_name = 'expenses/expense_list.html'
    context_object_name = 'expenses'
    paginate_by = 20
    ordering = ['-payment_date']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['fields'] = Field.ownership_objects.get_queryset_for_user(self.request.user)
        context['expense_types'] = ExpenseType.ownership_objects.get_queryset_for_user(self.request.user)
        return context


class ExpenseFormView(BaseSecureExpenseFormMixin, SuccessMessageMixin, UpdateView):
    """Unified view for creating and editing expenses"""
    model = Expense
    form_class = ExpenseForm
    template_name = 'expenses/expense_form.html'
    success_url = reverse_lazy('expense-list')

    def get_object(self, queryset=None):
        """Return existing object for edit, or None for create"""
        if 'pk' in self.kwargs:
            return super().get_object(queryset)
        return None

    def get_success_message(self, cleaned_data):
        if self.object and self.object.pk:
            return 'Gasto actualizado con éxito.'
        return 'Gasto creado con éxito.'

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        # Filtrar parcelas y tipos de gasto por usuario
        form.fields['field'].queryset = Field.ownership_objects.get_queryset_for_user(self.request.user)
        form.fields['expense_type'].queryset = ExpenseType.ownership_objects.get_queryset_for_user(self.request.user)
        return form

    def form_valid(self, form):
        # Asignar la organización del usuario al gasto
        form.instance.organization = self.request.user.organization
        return super().form_valid(form)


class ExpenseDeleteView(BaseSecureExpenseViewMixin, DeleteView):
    model = Expense
    success_url = reverse_lazy('expense-list')

    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Gasto eliminado con éxito.')
        return super().delete(request, *args, **kwargs)


# ExpenseType CRUD Views
class ExpenseTypeListView(BaseSecureExpenseViewMixin, ListView):
    model = ExpenseType
    template_name = 'expenses/expense_type_list.html'
    context_object_name = 'expense_types'
    ordering = ['name']


class ExpenseTypeFormView(BaseSecureExpenseFormMixin, SuccessMessageMixin, UpdateView):
    """Unified view for creating and editing expense types"""
    model = ExpenseType
    template_name = 'expenses/expense_type_form.html'
    fields = ['name', 'description']
    success_url = reverse_lazy('expense-type-list')

    def get_object(self, queryset=None):
        """Return existing object for edit, or None for create"""
        if 'pk' in self.kwargs:
            return super().get_object(queryset)
        return None

    def get_success_message(self, cleaned_data):
        if self.object and self.object.pk:
            return 'Tipo de gasto actualizado con éxito.'
        return 'Tipo de gasto creado con éxito.'

    def form_valid(self, form):
        # Asignar la organización del usuario al tipo de gasto
        form.instance.organization = self.request.user.organization
        return super().form_valid(form)


class ExpenseTypeDeleteView(BaseSecureExpenseViewMixin, DeleteView):
    model = ExpenseType
    success_url = reverse_lazy('expense-type-list')

    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Tipo de gasto eliminado con éxito.')
        return super().delete(request, *args, **kwargs)