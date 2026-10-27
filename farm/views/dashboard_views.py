from datetime import timedelta

from django.conf import settings
from django.db.models import Sum
from django.urls import reverse
from django.utils import timezone
from django.views.generic import ListView

from core.models import is_enabled
from farm.mixins import BaseSecureViewMixin
from farm.models import Field, Treatment
from farm.services import get_shopping_list


class FieldDashboardView(BaseSecureViewMixin, ListView):
    model = Field
    template_name = "farm/fields/field_dashboard.html"
    context_object_name = "fields"

    # Inicio es un vistazo: hasta 10 filas por grupo (cabe lo normal sin que Atrasados tape el resto)
    # y «Ver los N» al listado, que es donde se trabaja
    group_preview = 10
    # El grupo «Próximos» se parte en los primeros 7 días y el resto hasta UPCOMING_DAYS
    soon_days = 7
    # Productos que se muestran en «Producto que vas a necesitar»; el resto, en Preparar productos
    products_preview = 6

    def get_queryset(self):
        return Field.ownership_objects.get_queryset_for_user(self.request.user)

    def _group(self, qs, index):
        """Primeras filas de un grupo + total.

        `urgency_group` lo usa la fila del listado para colorear la fecha. Los dos grupos de próximos
        (≤ 7 días y hasta UPCOMING_DAYS) son ámbar, como en el listado y el detalle: el horizonte
        de «próximos» es único en toda la app.
        """
        tone = min(index, 1)
        rows = list(qs[:self.group_preview])
        for treatment in rows:
            treatment.urgency_group = tone
        return rows, qs.count(), tone

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        fields = context['fields']

        total_area = fields.aggregate(Sum('area'))['area__sum']
        context['total_area'] = round(total_area, 2) if total_area else 0

        # Por fechas y no por `status` (puede estar desfasado), igual que los grupos del listado
        today = timezone.localdate()
        soon_limit = today + timedelta(days=self.soon_days)
        upcoming_limit = today + timedelta(days=Treatment.UPCOMING_DAYS)

        todo = (
            Treatment.objects.filter(field__in=fields, finish_date__isnull=True)
            .select_related('field', 'machine')
            .prefetch_related('treatmentproduct_set__product__product_type')
            .order_by('date', 'name')
        )
        group_querysets = [
            todo.filter(date__lt=today),
            todo.filter(date__gte=today, date__lte=soon_limit),
            todo.filter(date__gt=soon_limit, date__lte=upcoming_limit),
        ]
        groups = []
        for index, qs in enumerate(group_querysets):
            rows, total, tone = self._group(qs, index)
            groups.append({'index': index, 'tone': tone, 'treatments': rows, 'total': total})
        delayed, soon, later = groups
        delayed['label'] = 'Atrasados'
        soon['label'] = f'Próximos {self.soon_days} días'
        later['range_start'] = soon_limit + timedelta(days=1)
        later['range_end'] = upcoming_limit

        # «Ver los N» de cada grupo abre el listado con exactamente las mismas fechas
        list_url = reverse('treatment-list')
        delayed['url'] = f'{list_url}?status=delayed'
        soon['url'] = (f'{list_url}?status=pending&date_from={today.isoformat()}'
                       f'&date_to={soon_limit.isoformat()}')
        later['url'] = (f'{list_url}?status=pending&date_from={later["range_start"].isoformat()}'
                        f'&date_to={upcoming_limit.isoformat()}')
        context['groups'] = groups
        context['has_work'] = any(g['total'] for g in groups)
        # Chips: cada uno enlaza al listado con el mismo filtro, así el número y la lista coinciden
        context['chips'] = [
            {'label': 'Atrasados', 'count': delayed['total'], 'tone': 0,
             'url': f'{list_url}?status=delayed'},
            {'label': f'{self.soon_days} días', 'count': soon['total'], 'tone': 1,
             'url': f'{list_url}?status=pending&date_to={soon_limit.isoformat()}'},
            {'label': f'{Treatment.UPCOMING_DAYS} días', 'count': soon['total'] + later['total'], 'tone': 1,
             'url': f'{list_url}?status=pending&date_to={upcoming_limit.isoformat()}'},
        ]
        context['upcoming_days'] = Treatment.UPCOMING_DAYS

        # ── Producto que vas a necesitar: atrasados + próximos 7 días ──
        urgent_ids = list(
            todo.filter(date__lte=soon_limit).values_list('id', flat=True)
        )
        products = []
        # get_shopping_list ignora un filtro vacío y devolvería todos los pendientes
        if urgent_ids:
            products = sorted(
                get_shopping_list(self.request.user, treatment_ids=urgent_ids),
                key=lambda p: (-p['treatment_count'], p['product_name']),
            )
        context['products'] = products[:self.products_preview]
        context['products_total'] = len(products)
        context['products_hidden'] = max(len(products) - self.products_preview, 0)

        # ── Tiempo: si el módulo está activo y alguna parcela tiene coordenadas ──
        # La previsión se pide aparte (JS) para no frenar Inicio con las llamadas a AEMET.
        context['show_weather'] = (
            is_enabled('WEATHER')
            and bool(getattr(settings, 'AEMET_API_KEY', ''))
            and fields.exclude(geometry='').exists()
        )
        return context


class FieldCostView(BaseSecureViewMixin, ListView):
    model = Field
    template_name = "farm/fields/field_costs.html"
    context_object_name = "fields"

    def get_queryset(self):
        return Field.ownership_objects.get_queryset_for_user(self.request.user)

