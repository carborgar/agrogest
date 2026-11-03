from datetime import date

from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Count, Q
from django.db.models.functions import TruncMonth
from django.db.models.aggregates import Sum
from django.urls import reverse_lazy
from django.utils.dateparse import parse_date
from django.views.generic import ListView, UpdateView, DeleteView

from farm.forms import ExpenseForm
from farm.mixins import OwnershipRequiredMixin, QuerysetFilterMixin, AuditableMixin
from farm.models import Expense, Field, ExpenseType


def _safe_date(value):
    """Fecha de un parámetro GET; None si falta o no es válida (p. ej. 2026-02-30)."""
    try:
        return parse_date(value or '')
    except ValueError:
        return None


class BaseSecureExpenseViewMixin(OwnershipRequiredMixin, QuerysetFilterMixin):
    """Mixin base que aplica control de acceso y filtrado para gastos."""
    pass


class BaseSecureExpenseFormMixin(BaseSecureExpenseViewMixin, AuditableMixin):
    """Mixin para vistas de formularios de gastos que incluye auditoría."""
    pass


class ExpenseListView(BaseSecureExpenseViewMixin, ListView):
    model = Expense
    template_name = 'farm/expenses/expense_list.html'
    context_object_name = 'expenses'
    ordering = ['-payment_date', '-id']
    # Paginación en servidor: los grupos por mes y los totales salen de toda la consulta, no de la página.
    paginate_by = 50
    YEAR_TABS = 3

    def get_queryset(self):
        qs = super().get_queryset()

        field_ids = self.request.GET.getlist('field')
        type_ids = self.request.GET.getlist('type')
        date_from = _safe_date(self.request.GET.get('date_from'))
        date_to = _safe_date(self.request.GET.get('date_to'))
        q = (self.request.GET.get('q') or '').strip()

        if field_ids:
            qs = qs.filter(field_id__in=field_ids)
        if type_ids:
            qs = qs.filter(expense_type_id__in=type_ids)
        if date_from:
            qs = qs.filter(payment_date__gte=date_from)
        if date_to:
            qs = qs.filter(payment_date__lte=date_to)
        if q:
            qs = qs.filter(
                Q(description__icontains=q) | Q(field__name__icontains=q) | Q(expense_type__name__icontains=q)
            )

        return qs.select_related('field', 'expense_type')

    def _url(self, **changes):
        """URL del listado con los filtros actuales y los cambios indicados (None quita el parámetro)."""
        params = self.request.GET.copy()
        params.pop('page', None)
        for key, value in changes.items():
            params.pop(key, None)
            if value is not None:
                params[key] = value
        query = params.urlencode()
        return f"{self.request.path}?{query}" if query else self.request.path

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        full_qs = self.object_list
        get = self.request.GET

        totals = full_qs.aggregate(total=Sum('amount'), count=Count('id'))
        context['total_amount'] = totals['total'] or 0
        context['expense_count'] = totals['count']

        # Total y número de gastos de cada mes (de toda la consulta, para las cabeceras de grupo)
        months = full_qs.annotate(month=TruncMonth('payment_date')).values('month') \
            .annotate(total=Sum('amount'), count=Count('id')).order_by()
        context['month_totals'] = {m['month'].strftime('%Y-%m'): m for m in months}

        # Listas para los filtros
        context['fields'] = Field.ownership_objects.get_queryset_for_user(self.request.user)
        context['expense_types'] = ExpenseType.ownership_objects.get_queryset_for_user(self.request.user)
        context['selected_field_ids'] = get.getlist('field')
        context['selected_type_ids'] = get.getlist('type')
        context['search_query'] = (get.get('q') or '').strip()

        # Solo las fechas válidas cuentan como filtro (la consulta ignora las demás)
        date_from = get.get('date_from', '') if _safe_date(get.get('date_from')) else ''
        date_to = get.get('date_to', '') if _safe_date(get.get('date_to')) else ''
        context['active_date_from'] = date_from
        context['active_date_to'] = date_to

        # Pestañas de año: «Todos» + el año actual y los dos anteriores
        current_year = date.today().year
        tabs = [{'label': 'Todos', 'url': self._url(date_from=None, date_to=None),
                 'active': not date_from and not date_to}]
        for year in range(current_year, current_year - self.YEAR_TABS, -1):
            start, end = f'{year}-01-01', f'{year}-12-31'
            tabs.append({'label': str(year), 'url': self._url(date_from=start, date_to=end),
                         'active': date_from == start and date_to == end})
        context['year_tabs'] = tabs
        custom_dates = bool(date_from or date_to) and not any(t['active'] for t in tabs)
        context['custom_dates'] = custom_dates

        # Filtros del panel (sin contar la búsqueda ni las pestañas de año): para el contador del botón en móvil
        context['panel_filter_count'] = (
            len(context['selected_field_ids']) + len(context['selected_type_ids']) + (1 if custom_dates else 0)
        )
        context['has_filters'] = bool(
            context['panel_filter_count'] or context['search_query'] or date_from or date_to
        )
        context['clear_url'] = self.request.path

        return context


class ExpenseFormView(BaseSecureExpenseFormMixin, SuccessMessageMixin, UpdateView):
    """Unified view for creating and editing expenses"""
    model = Expense
    form_class = ExpenseForm
    template_name = 'farm/expenses/expense_form.html'
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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Pasar información de las hectáreas de las parcelas para JavaScript
        fields = Field.ownership_objects.get_queryset_for_user(self.request.user)
        context['field_areas'] = {str(field.id): str(field.area) for field in fields}
        context['is_edit'] = bool(self.object and self.object.pk)

        return context

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
    template_name = 'farm/expenses/expense_type_list.html'
    context_object_name = 'expense_types'
    ordering = ['name']

    def get_queryset(self):
        qs = super().get_queryset().order_by("name")
        qs = qs.annotate(
            expense_count=Count('expense'),
            total_amount=Sum('expense__amount'),
        )
        return qs


class ExpenseTypeFormView(BaseSecureExpenseFormMixin, SuccessMessageMixin, UpdateView):
    """Unified view for creating and editing expense types"""
    model = ExpenseType
    template_name = 'farm/expenses/expense_type_form.html'
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

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields['name'].widget.attrs.update({'class': 'tf-inp', 'placeholder': 'Ej. Mano de obra'})
        form.fields['description'].widget.attrs.update({'class': 'tf-inp', 'rows': 2,
                                                        'placeholder': 'Para qué se usa este tipo'})
        return form

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['expense_count'] = self.object.expense_set.count() if self.object else 0
        return context

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
