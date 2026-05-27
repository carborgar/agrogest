from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Count, Exists, OuterRef
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.views.generic import ListView, UpdateView, DetailView, DeleteView

from farm.forms import StoragePointForm
from farm.mixins import BaseSecureViewMixin
from farm.models import Field, StoragePoint


class StoragePointListView(BaseSecureViewMixin, ListView):
    model = StoragePoint
    template_name = 'farm/storage_points/storage_point_list.html'
    context_object_name = 'storage_points'
    ordering = ['name']

    def get_queryset(self):
        return (
            super().get_queryset()
            .annotate(
                fields_count=Count('fields'),
                has_fields=Exists(Field.objects.filter(storage_point=OuterRef('pk'))),
            )
            .order_by('name')
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user_fields = Field.ownership_objects.get_queryset_for_user(self.request.user)
        context['unassigned_fields_count'] = user_fields.filter(storage_point__isnull=True).count()
        context['total_fields_count'] = user_fields.count()
        return context


class StoragePointFormView(BaseSecureViewMixin, SuccessMessageMixin, UpdateView):
    model = StoragePoint
    form_class = StoragePointForm
    template_name = 'farm/storage_points/storage_point_form.html'
    success_url = reverse_lazy('storage-point-list')

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
        fields = Field.ownership_objects.get_queryset_for_user(self.request.user).order_by('name')
        context['all_fields'] = fields
        context['assigned_field_ids'] = set(
            fields.filter(storage_point=self.object).values_list('id', flat=True)
        )
        context['assigned_count'] = len(context['assigned_field_ids'])
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
    success_url = reverse_lazy('storage-point-list')

    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Casetilla eliminada con exito.')
        return super().delete(request, *args, **kwargs)

