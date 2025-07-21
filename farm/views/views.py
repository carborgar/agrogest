import json
import logging
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.messages.views import SuccessMessageMixin
from django.db import transaction
from django.db.models import Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.views.decorators.http import require_http_methods
from django.views.generic import ListView, DetailView
from django.views.generic import TemplateView
from django.views.generic.edit import CreateView, UpdateView

from farm.ai_queries import FarmFlowProcessor
from farm.forms import TreatmentForm, TreatmentProductFormSet
from farm.mixins import OwnershipRequiredMixin, QuerysetFilterMixin, AuditableMixin
from farm.models import Field, ProductType, TreatmentProduct
from farm.models import Product
from farm.models import Treatment

logger = logging.getLogger(__name__)


class BaseSecureViewMixin(OwnershipRequiredMixin, QuerysetFilterMixin, AuditableMixin):
    """Mixin base que aplica control de acceso, filtrado y auditoría."""
    pass


class FieldDashboardView(BaseSecureViewMixin, ListView):
    model = Field
    template_name = "farm/fields/field_dashboard.html"
    context_object_name = "fields"

    def get_queryset(self):
        return Field.ownership_objects.get_queryset_for_user(self.request.user)

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


class FieldCostView(BaseSecureViewMixin, ListView):
    model = Field
    template_name = "farm/fields/field_costs.html"
    context_object_name = "fields"

    def get_queryset(self):
        return Field.ownership_objects.get_queryset_for_user(self.request.user)


class TreatmentListView(BaseSecureViewMixin, ListView):
    model = Treatment
    template_name = 'farm/treatments/treatment_list.html'
    context_object_name = 'treatments'
    paginate_by = 6
    ordering = ['-date']

    def get_queryset(self):
        queryset = super().get_queryset()

        field_ids = self.request.GET.getlist('field')
        type_filters = self.request.GET.getlist('type')
        status_filters = self.request.GET.getlist('status') or [Treatment.STATUS_PENDING, Treatment.STATUS_DELAYED]
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

        return queryset.order_by(*self.ordering)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context['fields'] = Field.ownership_objects.get_queryset_for_user(self.request.user)
        context['products'] = Product.ownership_objects.get_queryset_for_user(self.request.user)
        context['type_choices'] = Treatment.TYPE_CHOICES
        context['status_choices'] = Treatment.STATUS_CHOICES
        context['selected_fields'] = self.request.GET.getlist('field')
        context['selected_types'] = self.request.GET.getlist('type')
        context['selected_statuses'] = self.request.GET.getlist('status') or [Treatment.STATUS_PENDING,
                                                                              Treatment.STATUS_DELAYED]
        context['selected_products'] = self.request.GET.getlist('products')
        context['date_from'] = self.request.GET.get('date_from')
        context['date_to'] = self.request.GET.get('date_to')
        context['product_types'] = ProductType.ownership_objects.get_queryset_for_user(self.request.user)
        context['selected_product_types'] = self.request.GET.getlist('product_types')
        context['total_count'] = self.get_queryset().count()

        query_params = self.request.GET.copy()
        if 'page' in query_params:
            del query_params['page']
        context['query_params'] = query_params.urlencode()

        return context


class TreatmentDetailView(BaseSecureViewMixin, DetailView):
    model = Treatment
    template_name = 'farm/treatments/treatment_detail.html'
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


class TreatmentFormView(BaseSecureViewMixin, SuccessMessageMixin, CreateView, UpdateView):
    model = Treatment
    form_class = TreatmentForm
    template_name = 'farm/treatments/treatment_form.html'

    def get_success_url(self):
        return reverse('treatment-detail', kwargs={'pk': self.object.id})

    def get_success_message(self, cleaned_data):
        return f"Tratamiento '{cleaned_data['name']}' creado exitosamente"

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


class TreatmentCalendarView(BaseSecureViewMixin, TemplateView):
    template_name = 'farm/treatments/calendar.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['fields'] = Field.ownership_objects.get_queryset_for_user(self.request.user)
        context['treatment_types'] = Treatment.TYPE_CHOICES
        context['type_map'] = {  # TODO: esto habría que hacerlo con los campos del modelo, o quitar el icono y listo
            'spraying': 'spray-can-sparkles',
            'fertigation': 'droplet',
        }
        return context


@method_decorator(require_POST, name='dispatch')
class FinishTreatmentView(BaseSecureViewMixin, View):
    def post(self, request, pk):
        treatment = get_object_or_404(Treatment, pk=pk)
        finish_date = request.POST.get('finish_date')
        real_water_used = request.POST.get('real_water_used')

        if not finish_date:
            return JsonResponse({'success': False}, status=400)

        treatment.finish_treatment(finish_date, real_water_used)

        return JsonResponse({'success': True})


@method_decorator(require_POST, name='dispatch')
class DeleteTreatmentView(BaseSecureViewMixin, View):
    def post(self, request, pk):
        treatment = get_object_or_404(Treatment, pk=pk)
        treatment.delete()
        messages.success(request, f'Tratamiento "{treatment.name}" eliminado')
        return redirect('treatment-list')


class TreatmentExportView(BaseSecureViewMixin, DetailView):
    model = Treatment
    template_name = 'farm/treatments/treatment_export.html'
    context_object_name = 'treatment'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['products'] = TreatmentProduct.ownership_objects.get_queryset_for_user(self.request.user).filter(
            treatment=self.object)
        context['now'] = timezone.now()

        if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            self.template_name = 'treatments/treatment_export.html'

        return context


class ShoppingListView(BaseSecureViewMixin, ListView):
    template_name = 'farm/treatments/shopping_list.html'
    context_object_name = 'product_items'

    def get_queryset(self):
        # Base queryset - get products from pending or delayed treatments
        queryset = TreatmentProduct.ownership_objects.get_queryset_for_user(self.request.user).filter(
            treatment__status__in=['pending', 'delayed']
        ).select_related('product', 'product__product_type', 'treatment', 'treatment__field')

        # Filter by field if specified
        selected_fields = self.request.GET.getlist('field')
        if selected_fields:
            queryset = queryset.filter(treatment__field_id__in=selected_fields)

        # Group by product, summing total_dose
        # Get the product ID from the aggregation (which will be our group key)
        product_totals = {}

        # We need to process the queryset in Python to properly group by product
        # and handle different units and fields
        for product_item in queryset:
            product_id = product_item.product_id

            # Create a key that includes product and unit
            key = (product_id, product_item.total_dose_unit)

            if key not in product_totals:
                product_totals[key] = {
                    'product': product_item.product,
                    'product_name': product_item.product.name,
                    'product_type': product_item.product.product_type.name,
                    'unit': product_item.total_dose_unit,
                    'total_dose': 0,
                    'total_price': 0,
                    'treatment_count': 0,
                    'fields': set(),  # Use a set to avoid duplicates
                }

            # Sum the dose and price
            product_totals[key]['total_dose'] += float(product_item.total_dose)
            product_totals[key]['total_price'] += float(product_item.total_price)
            product_totals[key]['treatment_count'] += 1
            product_totals[key]['fields'].add(product_item.treatment.field.name)

        # Convert to a list and format the fields as a string
        result = []
        for key, data in product_totals.items():
            data['fields'] = ", ".join(sorted(data['fields']))
            data['total_dose'] = round(data['total_dose'], 2)
            data['total_price'] = round(data['total_price'], 2)
            result.append(data)

        # Sort by product name
        result.sort(key=lambda x: x['product_name'])

        return result

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Add fields for filtering
        context['fields'] = Field.objects.filter(organization=self.request.user.organization)

        # Add selected filters to context
        context['selected_fields'] = self.request.GET.getlist('field')

        # Calculate totals
        total_price = sum(item['total_price'] for item in self.object_list)
        context['total_price'] = round(total_price, 2)
        context['total_count'] = len(self.object_list)

        return context


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def ai_query(request):
    """
    Endpoint para procesar pasos del flujo conversacional
    """
    try:
        data = json.loads(request.body)

        # Procesar paso usando el usuario autenticado
        processor = FarmFlowProcessor(request.user)
        response = processor.process_step(data)

        return JsonResponse(response)

    except Exception as e:
        return JsonResponse({
            'type': 'error',
            'message': f'Error interno: {str(e)}',
            'show_menu': True
        }, status=500)


@login_required
def ai_assistant_view(request):
    """Vista para mostrar la interfaz del asistente"""
    return render(request, 'farm/ai_assistant.html', {
        'user': request.user,
        'organization': request.user.organization
    })
