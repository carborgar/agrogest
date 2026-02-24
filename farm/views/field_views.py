from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView

from farm.models import Field, Treatment
from farm.views.field_forms import FieldForm


class FieldListView(LoginRequiredMixin, ListView):
    model = Field
    template_name = 'farm/fields/field_list.html'
    context_object_name = 'fields'
    paginate_by = 20

    def get_queryset(self):
        return (
            Field.objects.all()
            .annotate(
                pending_count=Count('treatment', filter=Q(treatment__status=Treatment.STATUS_PENDING)),
                delayed_count=Count('treatment', filter=Q(treatment__status=Treatment.STATUS_DELAYED)),
                completed_count=Count('treatment', filter=Q(treatment__status=Treatment.STATUS_COMPLETED)),
                total_treatments=Count('treatment'),
            )
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        fields = context['fields']
        from django.db.models import Sum
        context['total_area'] = round(fields.aggregate(Sum('area'))['area__sum'] or 0, 2)
        context['total_fields'] = fields.count()
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
