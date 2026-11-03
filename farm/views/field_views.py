import json

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q, ProtectedError, RestrictedError
from django.shortcuts import redirect
from django.urls import reverse_lazy, reverse
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView

from farm.models import Field, StoragePoint, Treatment
from farm.forms import FieldForm


class FieldListView(LoginRequiredMixin, ListView):
    """
    Parcelas agrupadas por casetilla (punto de reparto).

    Una parcela sin casetilla es independiente (el producto se deja en ella),
    así que se muestran en un bloque aparte. Sin paginación: una explotación tiene
    pocas parcelas y paginar partiría los grupos.
    """
    model = Field
    template_name = 'farm/fields/field_list.html'
    context_object_name = 'fields'

    def get_queryset(self):
        return (
            Field.ownership_objects.get_queryset_for_user(self.request.user)
            .select_related('storage_point')
            .order_by('-area', 'name')
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        fields = list(context['fields'])
        storage_points = StoragePoint.ownership_objects.get_queryset_for_user(self.request.user).order_by('name')

        groups = {sp.pk: {'storage_point': sp, 'fields': [], 'area': 0} for sp in storage_points}
        solo = []
        for f in fields:
            if f.storage_point_id in groups:
                groups[f.storage_point_id]['fields'].append(f)
                groups[f.storage_point_id]['area'] += f.area
            else:
                solo.append(f)

        for g in groups.values():
            g['area'] = round(g['area'], 2)  # evita 14,000000000000002 al sumar floats
        context['storage_point_groups'] = list(groups.values())
        context['solo_fields'] = solo
        context['solo_area'] = round(sum(f.area for f in solo), 2)
        context['total_fields'] = len(fields)
        context['total_area'] = round(sum(f.area for f in fields), 2)
        context['distribution_points_count'] = len(groups) + len(solo)
        context['crop_area_summary'] = self._build_crop_area_summary(fields)
        return context

    @staticmethod
    def _build_crop_area_summary(fields):
        """
        Returns area (ha) grouped by crop name (case-insensitive, stripped),
        sorted descending by area.
        """
        groups: dict = {}
        for field in fields:
            row = {'crop': field.crop, 'area': field.area}
            raw_crop = (row['crop'] or '').strip()
            key = raw_crop.lower()
            if not key:
                key = '(sin cultivo)'
                raw_crop = key
            if key not in groups:
                groups[key] = {'area': 0.0, 'count': 0, 'display': raw_crop.title()}
            groups[key]['area'] += row['area'] or 0
            groups[key]['count'] += 1

        palette = ['success', 'primary', 'info', 'warning', 'danger', 'secondary']
        sorted_groups = sorted(groups.values(), key=lambda x: -x['area'])
        total_area = sum(g['area'] for g in sorted_groups)

        result = []
        for i, g in enumerate(sorted_groups):
            area = round(g['area'], 2)
            pct = int(round(area / total_area * 100)) if total_area > 0 else 0
            result.append({
                'crop': g['display'],
                'area': area,
                'count': g['count'],
                'area_pct': pct,
                'color': palette[i % len(palette)],
            })
        return result


class FieldOrganizationQuerysetMixin:
    """Solo parcelas de la organización del usuario: con otro id en la URL, 404 en vez de la parcela ajena."""

    def get_queryset(self):
        return Field.ownership_objects.get_queryset_for_user(self.request.user)


class FieldDetailView(LoginRequiredMixin, FieldOrganizationQuerysetMixin, DetailView):
    model = Field
    template_name = 'farm/fields/field_detail.html'
    context_object_name = 'field'
    RECENT = 5  # filas por grupo (pendientes / hechos); el resto, en el listado de Tratamientos

    def get_queryset(self):
        return super().get_queryset().select_related('storage_point')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        field = self.object
        treatments = Treatment.objects.filter(field=field)
        counts = treatments.aggregate(
            total=Count('id'),
            pending=Count('id', filter=Q(status=Treatment.STATUS_PENDING)),
            delayed=Count('id', filter=Q(status=Treatment.STATUS_DELAYED)),
            completed=Count('id', filter=Q(status=Treatment.STATUS_COMPLETED)),
        )
        context['total_treatments'] = counts['total']
        context['pending_count'] = counts['pending']
        context['delayed_count'] = counts['delayed']
        context['completed_count'] = counts['completed']

        # Lo que falta por hacer (lo más urgente primero) y lo último hecho; las filas son las del listado
        rows = (
            treatments.select_related('field', 'machine')
            .prefetch_related('treatmentproduct_set__product__product_type')
        )
        # Mismo campo (status) que los contadores y los enlaces «Ver los N», para que cifras y filas coincidan
        open_statuses = (Treatment.STATUS_PENDING, Treatment.STATUS_DELAYED)
        context['pending_treatments'] = list(rows.filter(status__in=open_statuses).order_by('date', 'id')[:self.RECENT])
        context['done_treatments'] = list(rows.filter(status=Treatment.STATUS_COMPLETED).order_by('-finish_date', '-id')[:self.RECENT])
        # Contorno ya parseado para json_script (nunca texto crudo dentro de un <script>); si está dañado, sin mapa
        try:
            context['geometry_data'] = json.loads(field.geometry) if field.geometry else None
        except ValueError:
            context['geometry_data'] = None
        context['popup_data'] = {'name': field.name, 'crop': field.crop}
        context['pending_total'] = counts['pending'] + counts['delayed']
        return context


class FieldCreateView(LoginRequiredMixin, CreateView):
    model = Field
    form_class = FieldForm
    template_name = 'farm/fields/field_form.html'
    success_url = reverse_lazy('field-list')

    def form_valid(self, form):
        form.instance.organization = self.request.user.organization
        messages.success(self.request, 'Parcela creada con éxito.')
        return super().form_valid(form)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs


class FieldUpdateView(LoginRequiredMixin, FieldOrganizationQuerysetMixin, UpdateView):
    model = Field
    form_class = FieldForm
    template_name = 'farm/fields/field_form.html'

    def get_success_url(self):
        return reverse('field-detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        messages.success(self.request, 'Parcela actualizada con éxito.')
        return super().form_valid(form)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs


class FieldDeleteView(LoginRequiredMixin, FieldOrganizationQuerysetMixin, DeleteView):
    model = Field
    success_url = reverse_lazy('field-list')
    http_method_names = ['post']  # borrar es una acción: sin pantalla de confirmación propia, nada de GET

    def form_valid(self, form):
        # Los tratamientos, gastos y cosechas restringen el borrado: sin esta comprobación, un POST directo daba un 500.
        # (El mensaje de éxito va aquí: DeleteView ya no llama a delete() desde Django 4.)
        if not self.object.can_be_deleted():
            if Treatment.objects.filter(field=self.object).exists():
                messages.error(self.request, 'No se puede eliminar una parcela con tratamientos.')
            else:
                messages.error(self.request, 'No se puede eliminar: la parcela tiene tratamientos, gastos o cosechas.')
            return redirect('field-detail', pk=self.object.pk)
        try:
            response = super().form_valid(form)
        except (RestrictedError, ProtectedError):
            messages.error(self.request, 'No se puede eliminar: la parcela tiene tratamientos, gastos o cosechas.')
            return redirect('field-detail', pk=self.object.pk)
        messages.success(self.request, 'Parcela eliminada con éxito.')
        return response
