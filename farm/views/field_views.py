from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
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


class FieldDetailView(LoginRequiredMixin, DetailView):
    model = Field
    template_name = 'farm/fields/field_detail.html'
    context_object_name = 'field'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        field = self.object
        treatments = (
            Treatment.objects.filter(field=field)
            .order_by('-date')
            .select_related('machine')
            .prefetch_related('products')
        )
        context['treatments'] = treatments
        context['pending_count'] = treatments.filter(status=Treatment.STATUS_PENDING).count()
        context['delayed_count'] = treatments.filter(status=Treatment.STATUS_DELAYED).count()
        context['completed_count'] = treatments.filter(status=Treatment.STATUS_COMPLETED).count()
        context['total_treatments'] = treatments.count()
        context['recent_treatments'] = treatments[:6]
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


class FieldUpdateView(LoginRequiredMixin, UpdateView):
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


class FieldDeleteView(LoginRequiredMixin, DeleteView):
    model = Field
    success_url = reverse_lazy('field-list')

    def get_queryset(self):
        return Field.objects.all()

    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Parcela eliminada con éxito.')
        return super().delete(request, *args, **kwargs)
