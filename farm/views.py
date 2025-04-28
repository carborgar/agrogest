from decimal import Decimal

from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.db import transaction
from django.db.models import Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import ListView, DetailView
from django.views.generic.edit import CreateView, UpdateView

from .forms import TreatmentForm, TreatmentProductFormSet
from .models import Field, ProductType, TreatmentProduct
from .models import Product
from .models import Treatment


class FieldListView(ListView):
    model = Field
    template_name = "fields/field_list.html"
    context_object_name = "fields"

    def get_queryset(self):
        return Field.objects.all()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        fields = context['fields']

        # Calcula el total de hectáreas
        total_area = fields.aggregate(Sum('area'))['area__sum']

        total_pending_treatments = sum(field.pending_treatments_count() for field in fields)
        total_delayed_treatments = sum(field.delayed_treatments_count() for field in fields)

        context['total_area'] = total_area
        context['pending_treatments_count'] = total_pending_treatments
        context['delayed_treatments_count'] = total_delayed_treatments

        treatment_types = Treatment.TYPE_CHOICES

        # Mapeo de iconos para tipos de tratamiento
        type_map = {
            'spraying': 'spray-can-sparkles',
            'fertigation': 'droplet',
        }

        context['treatment_types'] = treatment_types
        context['type_map'] = type_map

        # TODO: esto no se debe hacer así. Es mejor incluir la carga de valores en el API y cargarlo por JS

        return context


class FieldCostView(ListView):
    model = Field
    template_name = "fields/field_costs.html"
    context_object_name = "fields"

    def get_queryset(self):
        return Field.objects.all()


class TreatmentListView(ListView):
    model = Treatment
    template_name = 'treatments/treatment_list.html'
    context_object_name = 'treatments'
    paginate_by = 6
    ordering = ['-date']

    def get_queryset(self):
        queryset = super().get_queryset()

        field_ids = self.request.GET.getlist('field')
        type_filters = self.request.GET.getlist('type')
        status_filters = self.request.GET.getlist('status')
        product_ids = self.request.GET.getlist('products')
        date_from = self.request.GET.get('date_from')
        date_to = self.request.GET.get('date_to')
        product_type_filters = self.request.GET.getlist('product_type')

        if field_ids:
            queryset = queryset.filter(field__id__in=field_ids)
        if type_filters:
            queryset = queryset.filter(type__in=type_filters)
        if product_ids:
            queryset = queryset.filter(products__id__in=product_ids)
        if date_from:
            queryset = queryset.filter(date__gte=date_from)
        if date_to:
            queryset = queryset.filter(date__lte=date_to)
        if product_type_filters:
            queryset = queryset.filter(products__product_type__in=product_type_filters)
        if status_filters:
            queryset = queryset.filter(status__in=status_filters)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context['fields'] = Field.objects.all()
        context['products'] = Product.objects.all()
        context['type_choices'] = Treatment.TYPE_CHOICES
        context['status_choices'] = Treatment.STATUS_CHOICES
        context['selected_fields'] = self.request.GET.getlist('field')
        context['selected_types'] = self.request.GET.getlist('type')
        context['selected_statuses'] = self.request.GET.getlist('status')
        context['selected_products'] = self.request.GET.getlist('products')
        context['date_from'] = self.request.GET.get('date_from')
        context['date_to'] = self.request.GET.get('date_to')
        context['product_types'] = ProductType.objects.all()
        context['selected_product_types'] = self.request.GET.getlist('product_types')
        context['total_count'] = self.get_queryset().count()

        query_params = self.request.GET.copy()
        if 'page' in query_params:
            del query_params['page']
        context['query_params'] = query_params.urlencode()

        return context


class TreatmentDetailView(DetailView):
    model = Treatment
    template_name = 'treatments/treatment_detail.html'
    context_object_name = 'treatment'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['status_choices'] = Treatment.STATUS_CHOICES

        # Obtener productos
        products = self.object.treatmentproduct_set.all()
        context['products'] = products

        # Calcular costos - ahora es mucho más simple
        total_cost = sum(product.total_price for product in products)

        # Calcular costo por hectárea
        cost_per_ha = 0
        if self.object.field and self.object.field.area > 0:
            cost_per_ha = total_cost / Decimal(self.object.field.area)

        context['total_cost'] = total_cost
        context['cost_per_ha'] = cost_per_ha

        return context


class TreatmentFormView(SuccessMessageMixin, CreateView, UpdateView):
    model = Treatment
    form_class = TreatmentForm
    template_name = 'treatments/treatment_form.html'

    def get_success_url(self):
        return reverse('treatment-detail', kwargs={'pk': self.object.id})

    def get_success_message(self, cleaned_data):
        if self.object.pk is None or not hasattr(self, 'object') or self.object is None:
            return f"Tratamiento '{cleaned_data['name']}' creado exitosamente"
        else:
            return f"Tratamiento '{cleaned_data['name']}' actualizado exitosamente"

    def get_object(self, queryset=None):
        if 'pk' in self.kwargs:
            return super().get_object(queryset)
        return None

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        if self.request.POST:
            if self.object:  # Update operation
                context['products_formset'] = TreatmentProductFormSet(
                    self.request.POST, instance=self.object
                )
            else:  # Create operation
                context['products_formset'] = TreatmentProductFormSet(self.request.POST)
        else:
            if self.object:  # Update operation
                context['products_formset'] = TreatmentProductFormSet(instance=self.object)
            else:  # Create operation
                context['products_formset'] = TreatmentProductFormSet()

        return context

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.get_form()
        treatment_product_formset = TreatmentProductFormSet(request.POST, instance=self.object)

        if form.is_valid() and treatment_product_formset.is_valid():
            self.object = form.save()
            treatment_product_formset.instance = self.object
            treatment_product_formset.save()
            return self.form_valid(form)
        else:
            return self.form_invalid(form)


def treatment_calendar(request):
    """Vista para el calendario de tratamientos"""
    fields = Field.objects.all()
    treatment_types = Treatment.TYPE_CHOICES

    # Mapeo de iconos para tipos de tratamiento
    type_map = {  # TODO: esto habría que hacerlo con los campos del modelo, o quitar el icono y listo
        'spraying': 'spray-can-sparkles',
        'fertigation': 'droplet',
    }

    context = {
        'fields': fields,
        'treatment_types': treatment_types,
        'type_map': type_map
    }

    return render(request, 'treatments/calendar.html', context)


@require_POST
def finish_treatment(request, pk):
    treatment = get_object_or_404(Treatment, pk=pk)
    finish_date = request.POST.get('finish_date')
    real_water_used = request.POST.get('real_water_used')

    if not finish_date:
        return JsonResponse({'success': False}, status=400)

    if real_water_used:
        treatment.water_per_ha = int(real_water_used)

    treatment.finish_date = finish_date
    treatment.save()

    return JsonResponse({'success': True})


@require_POST
def delete_treatment(request, pk):
    treatment = get_object_or_404(Treatment, pk=pk)
    treatment.delete()
    messages.success(request, 'Tratamiento "{}" eliminado'.format(treatment.name))
    return redirect('treatment-list')


def treatment_export(request, pk):
    treatment = get_object_or_404(Treatment, pk=pk)
    products = TreatmentProduct.objects.filter(treatment=treatment)

    context = {
        'treatment': treatment,
        'products': products,
        'now': timezone.now(),
    }

    # Si es una solicitud AJAX, retornamos solo el HTML
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return render(request, 'treatments/treatment_export.html', context)

    # Para solicitudes normales, mostramos la vista completa
    return render(request, 'treatments/treatment_export.html', context)
