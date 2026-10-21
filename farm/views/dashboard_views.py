from datetime import timedelta

from django.db.models import Sum
from django.utils import timezone
from django.views.generic import ListView

from farm.mixins import BaseSecureViewMixin
from farm.models import Field, Treatment


class FieldDashboardView(BaseSecureViewMixin, ListView):
    model = Field
    template_name = "farm/fields/field_dashboard.html"
    context_object_name = "fields"

    # Inicio es un vistazo: unas pocas filas y «Ver los N» al listado, que es donde se trabaja
    treatments_preview = 3

    def get_queryset(self):
        return Field.ownership_objects.get_queryset_for_user(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        fields = context['fields']

        total_area = fields.aggregate(Sum('area'))['area__sum']
        context['total_area'] = round(total_area, 2) if total_area else 0

        base_treatments = Treatment.objects.filter(field__in=fields).select_related('field')

        # Por fechas y no por `status` (puede estar desfasado), igual que los grupos del listado
        today = timezone.localdate()
        upcoming_days = Treatment.UPCOMING_DAYS
        upcoming_limit_date = today + timedelta(days=upcoming_days)

        delayed_treatments_qs = base_treatments.filter(
            finish_date__isnull=True, date__lt=today
        ).order_by('date')

        upcoming_treatments_qs = base_treatments.filter(
            finish_date__isnull=True,
            date__range=(today, upcoming_limit_date)
        ).order_by('date')

        context['delayed_treatments_count'] = delayed_treatments_qs.count()
        context['pending_treatments_count'] = upcoming_treatments_qs.count()

        type_map = {
            'spraying': 'spray-can-sparkles',
            'fertigation': 'droplet',
        }
        context['treatment_types'] = Treatment.TYPE_CHOICES
        context['type_map'] = type_map

        context['delayed_treatments'] = delayed_treatments_qs[:self.treatments_preview]
        context['delayed_total'] = context['delayed_treatments_count']
        context['upcoming_treatments'] = upcoming_treatments_qs[:self.treatments_preview]
        context['upcoming_total'] = context['pending_treatments_count']
        context['upcoming_days'] = upcoming_days

        return context


class FieldCostView(BaseSecureViewMixin, ListView):
    model = Field
    template_name = "farm/fields/field_costs.html"
    context_object_name = "fields"

    def get_queryset(self):
        return Field.ownership_objects.get_queryset_for_user(self.request.user)

