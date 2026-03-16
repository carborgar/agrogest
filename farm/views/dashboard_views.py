from datetime import timedelta

from django.core.paginator import Paginator
from django.db.models import Sum
from django.utils import timezone
from django.views.generic import ListView

from farm.mixins import BaseSecureViewMixin
from farm.models import Field, Treatment


class FieldDashboardView(BaseSecureViewMixin, ListView):
    model = Field
    template_name = "farm/fields/field_dashboard.html"
    context_object_name = "fields"

    treatments_per_page = 5

    def get_queryset(self):
        return Field.ownership_objects.get_queryset_for_user(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        fields = context['fields']

        total_area = fields.aggregate(Sum('area'))['area__sum']
        context['total_area'] = round(total_area, 2) if total_area else 0

        base_treatments = Treatment.objects.filter(field__in=fields).select_related('field')

        delayed_treatments_qs = base_treatments.filter(
            status=Treatment.STATUS_DELAYED
        ).order_by('date')

        today = timezone.now().date()
        upcoming_days = 15
        upcoming_limit_date = today + timedelta(days=upcoming_days)

        upcoming_treatments_qs = base_treatments.filter(
            status=Treatment.STATUS_PENDING,
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

        delayed_page = self.request.GET.get('delayed_page', 1)
        delayed_paginator = Paginator(delayed_treatments_qs, self.treatments_per_page)
        delayed_page_obj = delayed_paginator.get_page(delayed_page)

        upcoming_page = self.request.GET.get('upcoming_page', 1)
        upcoming_paginator = Paginator(upcoming_treatments_qs, self.treatments_per_page)
        upcoming_page_obj = upcoming_paginator.get_page(upcoming_page)

        context['delayed_treatments'] = delayed_page_obj
        context['delayed_total'] = delayed_paginator.count
        context['delayed_showing'] = len(delayed_page_obj)

        context['upcoming_treatments'] = upcoming_page_obj
        context['upcoming_total'] = upcoming_paginator.count
        context['upcoming_showing'] = len(upcoming_page_obj)

        context['delayed_page_param'] = f"delayed_page={delayed_page}" if delayed_page != '1' else ""
        context['upcoming_page_param'] = f"upcoming_page={upcoming_page}" if upcoming_page != '1' else ""
        context['upcoming_days'] = upcoming_days

        return context


class FieldCostView(BaseSecureViewMixin, ListView):
    model = Field
    template_name = "farm/fields/field_costs.html"
    context_object_name = "fields"

    def get_queryset(self):
        return Field.ownership_objects.get_queryset_for_user(self.request.user)

