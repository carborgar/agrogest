from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Sum, F, ExpressionWrapper, DecimalField, Avg
from django.urls import reverse_lazy
from django.views.generic import TemplateView
from django.views.generic.edit import UpdateView, DeleteView

from farm.forms import HarvestForm
from farm.mixins import OwnershipRequiredMixin, QuerysetFilterMixin, AuditableMixin
from farm.models import Harvest, Field


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

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields['field'].queryset = Field.ownership_objects.get_queryset_for_user(self.request.user)
        return form

    def form_valid(self, form):
        self.creating = not form.instance.pk
        form.instance.organization = self.request.user.organization
        return super().form_valid(form)


class HarvestDeleteView(OwnershipRequiredMixin, QuerysetFilterMixin, DeleteView):
    model = Harvest
    success_url = reverse_lazy('harvest-summary')

    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Cosecha eliminada correctamente.')
        return super().delete(request, *args, **kwargs)


class HarvestSummaryView(BaseSecureHarvestMixin, TemplateView):
    # usar siempre la plantilla moderna
    template_name = 'farm/harvests/cosecha_summary.html'

    def get_queryset(self):
        return Harvest.ownership_objects.get_queryset_for_user(self.request.user).select_related('field')

    def get_template_names(self):
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        qs = self.get_queryset()

        # Apply optional filters from GET params
        # Support filtering by multiple fields: ?field=1&field=2
        field_ids = self.request.GET.getlist('field')
        date_from = self.request.GET.get('date_from')
        date_to = self.request.GET.get('date_to')

        # Default to current year when dates are not provided
        current_year = date.today().year
        if not date_from:
            date_from = f'{current_year}-01-01'
        if not date_to:
            date_to = f'{current_year}-12-31'

        if field_ids:
            # convert to ints safely
            try:
                ids = [int(x) for x in field_ids if x]
            except Exception:
                ids = []
            if ids:
                qs = qs.filter(field_id__in=ids)
        if date_from:
            qs = qs.filter(date__gte=date_from)
        if date_to:
            qs = qs.filter(date__lte=date_to)

        # Totales globales
        total_kg = qs.aggregate(total=Sum('amount'))['total'] or Decimal('0')

        # Ingresos globales (solo registros con precio conocido)
        income_expr_global = ExpressionWrapper(F('amount') * F('sale_price_per_kg'), output_field=DecimalField())
        income = \
        qs.filter(sale_price_per_kg__isnull=False, price_pending=False).aggregate(income=Sum(income_expr_global))[
            'income'] or Decimal('0')

        # Agrupar por parcela: sumar kg y calcular kg/ha usando Field.area, anotar ingreso por parcela
        income_expr = ExpressionWrapper(F('amount') * F('sale_price_per_kg'), output_field=DecimalField())
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
            income_field = Decimal(str(g['income_sum'] or 0))
            kg_per_ha = None
            try:
                if area > 0:
                    kg_per_ha = total / area
            except Exception:
                kg_per_ha = None

            field_groups.append({
                'field_id': g['field_id'],
                'name': g['field__name'],
                'area': area,
                'total_kg': total,
                'kg_per_ha': kg_per_ha,
                'income': income_field,
            })

            if area > 0:
                total_area += area


        kg_per_ha_overall = None
        try:
            if total_area > 0:
                kg_per_ha_overall = Decimal(str(total_kg)) / total_area
        except Exception:
            kg_per_ha_overall = None

        # Promedio por día
        avg_per_day = qs.values('date').annotate(day_total=Sum('amount')).aggregate(avg=Avg('day_total'))[
                          'avg'] or Decimal('0')

        context.update({
            'harvests': qs.order_by('-date'),
            'total_kg': total_kg,
            'total_area': total_area,
            'kg_per_ha_overall': kg_per_ha_overall,
            'income': income,
            'avg_per_day': avg_per_day,
            'fields': Field.ownership_objects.get_queryset_for_user(self.request.user),
            'filter_params': self.request.GET.dict(),
            'selected_field_ids': field_ids,
            'single_field_selected': True if field_ids and len(field_ids) == 1 else False,
            'field_groups': field_groups,
            'active_date_from': date_from,
            'active_date_to': date_to,
            'current_year': current_year,
            'quick_years': list(range(current_year, current_year - 3, -1)),
        })

        return context
