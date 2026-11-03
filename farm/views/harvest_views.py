from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.core.paginator import Paginator
from django.db.models import Sum, F, ExpressionWrapper, DecimalField, Q
from django.urls import reverse_lazy
from django.utils.dateparse import parse_date
from django.views.generic import TemplateView
from django.views.generic.edit import UpdateView, DeleteView

from farm.forms import HarvestForm
from farm.mixins import OwnershipRequiredMixin, QuerysetFilterMixin, AuditableMixin
from farm.models import Harvest, Field


def _safe_date(value):
    """Fecha de un parámetro GET; None si falta o no es válida (p. ej. 2026-02-30)."""
    try:
        return parse_date(value or '')
    except ValueError:
        return None


class BaseSecureHarvestMixin(OwnershipRequiredMixin, QuerysetFilterMixin, AuditableMixin):
    pass


class HarvestFormView(BaseSecureHarvestMixin, SuccessMessageMixin, UpdateView):
    """Unified view for creating and editing harvests."""
    model = Harvest
    form_class = HarvestForm
    template_name = 'farm/harvests/cosecha_form.html'
    success_url = reverse_lazy('harvest-summary')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.creating = False

    def get_object(self, queryset=None):
        """Return existing object for edit, or None for create."""
        if 'pk' in self.kwargs:
            return super().get_object(queryset)
        return None

    def get_success_message(self, cleaned_data):
        if self.creating:
            return 'Cosecha registrada correctamente.'
        return 'Cosecha actualizada correctamente.'

    def get_user_fields(self):
        return Field.ownership_objects.get_queryset_for_user(self.request.user)

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields['field'].queryset = self.get_user_fields()
        return form

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Hectáreas de cada parcela para calcular kg/ha en el resumen en vivo
        context['field_areas'] = {str(f.id): str(f.area) for f in self.get_user_fields()}
        context['is_edit'] = bool(self.object and self.object.pk)
        return context

    def form_valid(self, form):
        self.creating = not form.instance.pk
        form.instance.organization = self.request.user.organization
        return super().form_valid(form)


class HarvestDeleteView(OwnershipRequiredMixin, QuerysetFilterMixin, DeleteView):
    model = Harvest
    success_url = reverse_lazy('harvest-summary')

    def form_valid(self, form):
        # Django 4+ borra desde form_valid (delete() solo se usa con el método HTTP DELETE)
        messages.success(self.request, 'Cosecha eliminada correctamente.')
        return super().form_valid(form)


class HarvestSummaryView(BaseSecureHarvestMixin, TemplateView):
    template_name = 'farm/harvests/cosecha_summary.html'
    paginate_by = 50
    YEAR_TABS = 3

    def get_queryset(self):
        return Harvest.ownership_objects.get_queryset_for_user(self.request.user).select_related('field')

    def _url(self, **changes):
        """URL del resumen con los filtros actuales y los cambios indicados (None quita el parámetro)."""
        params = self.request.GET.copy()
        params.pop('page', None)
        for key, value in changes.items():
            params.pop(key, None)
            if value is not None:
                params[key] = value
        query = params.urlencode()
        return f"{self.request.path}?{query}" if query else self.request.path

    def _dates(self, current_year):
        """Rango de fechas activo. Sin parámetros, el año actual; con parámetros vacíos («Todos»), sin límites."""
        get = self.request.GET
        if 'date_from' not in get and 'date_to' not in get:
            return f'{current_year}-01-01', f'{current_year}-12-31'
        # Enlaces antiguos con solo uno de los dos parámetros: el otro queda sin límite (intencionado).
        date_from = get.get('date_from', '') if _safe_date(get.get('date_from')) else ''
        date_to = get.get('date_to', '') if _safe_date(get.get('date_to')) else ''
        return date_from, date_to

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        qs = self.get_queryset()
        get = self.request.GET

        # Parcelas: ?field=1&field=2 (los valores no numéricos se ignoran)
        field_ids = [x for x in get.getlist('field') if x.isascii() and x.isdigit() and len(x) < 10]
        q = (get.get('q') or '').strip()
        current_year = date.today().year
        date_from, date_to = self._dates(current_year)

        if field_ids:
            qs = qs.filter(field_id__in=[int(x) for x in field_ids])
        if date_from:
            qs = qs.filter(date__gte=date_from)
        if date_to:
            qs = qs.filter(date__lte=date_to)
        if q:
            qs = qs.filter(Q(field__name__icontains=q) | Q(notes__icontains=q))

        # Totales globales; los ingresos solo cuentan registros con precio conocido
        income_expr = ExpressionWrapper(F('amount') * F('sale_price_per_kg'), output_field=DecimalField())
        total_kg = qs.aggregate(total=Sum('amount'))['total'] or Decimal('0')
        income = qs.filter(sale_price_per_kg__isnull=False, price_pending=False) \
            .aggregate(income=Sum(income_expr))['income'] or Decimal('0')

        # Desglose por parcela: kg, kg/ha (con la superficie de la parcela) e ingresos
        grouped = (
            qs.values('field_id', 'field__name', 'field__area')
            .annotate(total_kg=Sum('amount'), income_sum=Sum(income_expr))
            .order_by('field__name')
        )
        field_groups = []
        total_area = Decimal('0')
        for g in grouped:
            area = Decimal(str(g['field__area'] or 0))
            total = Decimal(str(g['total_kg'] or 0))
            field_groups.append({
                'field_id': g['field_id'],
                'name': g['field__name'],
                'area': area,
                'total_kg': total,
                'kg_per_ha': total / area if area > 0 else None,
                'income': Decimal(str(g['income_sum'] or 0)),
            })
            if area > 0:
                total_area += area
        kg_per_ha_overall = Decimal(str(total_kg)) / total_area if total_area > 0 else None

        # Registros: paginación en servidor (los totales salen de toda la consulta, no de la página)
        page_obj = Paginator(qs.order_by('-date', '-id'), self.paginate_by).get_page(get.get('page'))

        # Pestañas de año: «Todos» + el año actual y los dos anteriores. «Todos» envía las fechas vacías
        # para distinguirlo de la ausencia de parámetros, que equivale al año actual.
        tabs = [{'label': 'Todos', 'url': self._url(date_from='', date_to=''), 'year': None,
                 'active': not date_from and not date_to}]
        for year in range(current_year, current_year - self.YEAR_TABS, -1):
            start, end = f'{year}-01-01', f'{year}-12-31'
            tabs.append({'label': str(year), 'url': self._url(date_from=start, date_to=end), 'year': year,
                         'active': date_from == start and date_to == end})
        active_tab = next((t for t in tabs if t['active']), None)
        custom_dates = bool(date_from or date_to) and active_tab is None

        # Filtros del panel (sin la búsqueda ni las pestañas de año): contador del botón en móvil
        panel_filter_count = len(field_ids) + (1 if custom_dates else 0)

        context.update({
            'harvests': page_obj.object_list,
            'page_obj': page_obj,
            'harvest_count': page_obj.paginator.count,
            'total_kg': total_kg,
            'total_area': total_area,
            'kg_per_ha_overall': kg_per_ha_overall,
            'income': income,
            'fields': Field.ownership_objects.get_queryset_for_user(self.request.user),
            'selected_field_ids': field_ids,
            'single_field_selected': len(field_ids) == 1,
            'field_groups': field_groups,
            'search_query': q,
            'active_date_from': date_from,
            'active_date_to': date_to,
            'year_tabs': tabs,
            'active_year': active_tab['year'] if active_tab else None,
            'custom_dates': custom_dates,
            'panel_filter_count': panel_filter_count,
            'has_filters': bool(panel_filter_count or q),
            'clear_url': self.request.path,
        })
        return context
