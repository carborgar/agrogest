from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView

from farm.models import Field
from farm.views.field_forms import FieldForm


class FieldListView(LoginRequiredMixin, ListView):
    model = Field
    template_name = 'farm/fields/field_list.html'
    context_object_name = 'fields'
    paginate_by = 20

    def get_queryset(self):
        return Field.objects.all()


class FieldCreateView(LoginRequiredMixin, CreateView):
    model = Field
    form_class = FieldForm
    template_name = 'farm/fields/field_form.html'
    success_url = reverse_lazy('field-list')

    def form_valid(self, form):
        form.instance.organization = self.request.user.organization
        messages.success(self.request, 'Parcela creada con éxito.')
        return super().form_valid(form)


class FieldUpdateView(LoginRequiredMixin, UpdateView):
    model = Field
    form_class = FieldForm
    template_name = 'farm/fields/field_form.html'
    success_url = reverse_lazy('field-list')

    def form_valid(self, form):
        messages.success(self.request, 'Parcela actualizada con éxito.')
        return super().form_valid(form)


class FieldDeleteView(LoginRequiredMixin, DeleteView):
    model = Field
    success_url = reverse_lazy('field-list')

    def get_queryset(self):
        return Field.objects.all()

    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Parcela eliminada con éxito.')
        return super().delete(request, *args, **kwargs)
