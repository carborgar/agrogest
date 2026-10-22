from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.views.generic import RedirectView, UpdateView, DetailView, DeleteView

from farm.forms import StoragePointForm
from farm.mixins import BaseSecureViewMixin
from farm.models import Field, StoragePoint


class StoragePointListView(RedirectView):
    """Las casetillas se gestionan desde el listado de parcelas (agrupado por casetilla)."""
    pattern_name = 'field-list'
    permanent = False


class StoragePointFormView(BaseSecureViewMixin, SuccessMessageMixin, UpdateView):
    model = StoragePoint
    form_class = StoragePointForm
    template_name = 'farm/storage_points/storage_point_form.html'
    success_url = reverse_lazy('field-list')

    def get_object(self, queryset=None):
        if 'pk' in self.kwargs:
            return super().get_object(queryset)
        return None

    def get_success_message(self, cleaned_data):
        if self.object and self.object.pk and 'pk' in self.kwargs:
            return 'Casetilla actualizada con exito.'
        return 'Casetilla creada con exito.'

    def form_valid(self, form):
        if not form.instance.pk:
            form.instance.organization = self.request.user.organization
        return super().form_valid(form)


class StoragePointDetailView(BaseSecureViewMixin, DetailView):
    model = StoragePoint
    template_name = 'farm/storage_points/storage_point_detail.html'
    context_object_name = 'storage_point'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        fields = (
            Field.ownership_objects.get_queryset_for_user(self.request.user)
            .select_related('storage_point')
            .order_by('name')
        )
        # Primero las de esta casetilla, luego las sueltas y al final las de otras casetillas
        # (marcarlas las cambia de casetilla, así que van al final y avisadas).
        def rank(f):
            if f.storage_point_id == self.object.pk:
                return 0
            return 1 if f.storage_point_id is None else 2
        context['all_fields'] = sorted(fields, key=rank)
        assigned = [f for f in context['all_fields'] if f.storage_point_id == self.object.pk]
        context['assigned_field_ids'] = {f.id for f in assigned}
        context['assigned_count'] = len(assigned)
        context['assigned_area'] = round(sum(f.area for f in assigned), 2)
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        selected_ids = [fid for fid in request.POST.getlist('field_ids') if fid.isdigit()]

        base_fields = Field.ownership_objects.get_queryset_for_user(request.user)
        allowed_ids = set(base_fields.filter(pk__in=selected_ids).values_list('id', flat=True))

        base_fields.filter(storage_point=self.object).exclude(pk__in=allowed_ids).update(storage_point=None)
        if allowed_ids:
            base_fields.filter(pk__in=allowed_ids).update(storage_point=self.object)

        messages.success(request, 'Parcelas actualizadas para la casetilla.')
        return redirect(reverse('storage-point-detail', kwargs={'pk': self.object.pk}))


class StoragePointDeleteView(BaseSecureViewMixin, DeleteView):
    model = StoragePoint
    success_url = reverse_lazy('field-list')

    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Casetilla eliminada con exito.')
        return super().delete(request, *args, **kwargs)

