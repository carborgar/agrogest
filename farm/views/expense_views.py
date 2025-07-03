from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView

from farm.forms import ExpenseForm
from farm.mixins import OwnershipRequiredMixin, QuerysetFilterMixin, AuditableMixin
from farm.models import Expense, Field


class BaseSecureExpenseViewMixin(OwnershipRequiredMixin, QuerysetFilterMixin, AuditableMixin):
    """Mixin base que aplica control de acceso, filtrado y auditoría para gastos."""
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
        context['expense_types'] = Expense.EXPENSE_TYPES
        return context


class ExpenseCreateView(BaseSecureExpenseViewMixin, SuccessMessageMixin, CreateView):
    model = Expense
    form_class = ExpenseForm
    template_name = 'expenses/expense_form.html'
    success_url = reverse_lazy('expense-list')
    success_message = 'Gasto creado con éxito.'

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        # Filtrar parcelas por usuario
        form.fields['field'].queryset = Field.ownership_objects.get_queryset_for_user(self.request.user)
        return form

    def form_valid(self, form):
        # Asignar la organización del usuario al gasto
        form.instance.organization = self.request.user.organization
        return super().form_valid(form)


class ExpenseUpdateView(BaseSecureExpenseViewMixin, SuccessMessageMixin, UpdateView):
    model = Expense
    form_class = ExpenseForm
    template_name = 'expenses/expense_form.html'
    success_url = reverse_lazy('expense-list')
    success_message = 'Gasto actualizado con éxito.'

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        # Filtrar parcelas por usuario
        form.fields['field'].queryset = Field.ownership_objects.get_queryset_for_user(self.request.user)
        return form

    def form_valid(self, form):
        # Asegurar que la organización esté establecida (aunque debería existir)
        if not form.instance.organization:
            form.instance.organization = self.request.user.organization
        return super().form_valid(form)


class ExpenseDeleteView(BaseSecureExpenseViewMixin, DeleteView):
    model = Expense
    template_name = 'expenses/expense_confirm_delete.html'
    success_url = reverse_lazy('expense-list')

    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Gasto eliminado con éxito.')
        return super().delete(request, *args, **kwargs)