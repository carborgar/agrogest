import logging
from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import ListView, DetailView, TemplateView
from django.views.generic.edit import UpdateView
from django.views.decorators.http import require_POST

from farm.forms import TreatmentForm, TreatmentProductFormSet
from farm.mixins import BaseSecureViewMixin
from farm.models import Field, Product, ProductType, Treatment, TreatmentProduct
from farm.services import save_treatment_with_products, get_shopping_list, clone_treatment

logger = logging.getLogger(__name__)


class TreatmentListView(BaseSecureViewMixin, ListView):
    model = Treatment
    template_name = 'farm/treatments/treatment_list.html'
    context_object_name = 'treatments'
    paginate_by = 6
    ordering = ['-date']

    def get_queryset(self):
        queryset = (
            super()
            .get_queryset()
            .select_related("field")
            .prefetch_related("treatmentproduct_set__product__product_type")
        )

        field_ids = self.request.GET.getlist('field')
        type_filters = self.request.GET.getlist('type')
        status_filters = self.request.GET.getlist('status') or [Treatment.STATUS_PENDING, Treatment.STATUS_DELAYED]
        product_ids = self.request.GET.getlist('products')
        date_from = self.request.GET.get('date_from')
        date_to = self.request.GET.get('date_to')
        product_type_filters = self.request.GET.getlist('product_types')
        search_query = self.request.GET.get('q', '').strip()
        sort = self.request.GET.get('sort', 'date_asc')

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
        if search_query:
            queryset = queryset.filter(name__icontains=search_query)

        sort_map = {
            'date_asc': 'date',
            'date_desc': '-date',
            'name_asc': 'name',
            'name_desc': '-name',
        }
        order_field = sort_map.get(sort, 'date')
        return queryset.order_by(order_field).distinct()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        selected_fields = self.request.GET.getlist('field')
        selected_types = self.request.GET.getlist('type')
        selected_statuses = self.request.GET.getlist('status') or [Treatment.STATUS_PENDING, Treatment.STATUS_DELAYED]
        selected_products = self.request.GET.getlist('products')
        selected_product_types = self.request.GET.getlist('product_types')
        date_from = self.request.GET.get('date_from')
        date_to = self.request.GET.get('date_to')
        search_query = self.request.GET.get('q', '').strip()
        sort = self.request.GET.get('sort', 'date_asc')

        context['fields'] = Field.ownership_objects.get_queryset_for_user(self.request.user)
        context['products'] = Product.ownership_objects.get_queryset_for_user(self.request.user)
        context['type_choices'] = Treatment.TYPE_CHOICES
        context['status_choices'] = Treatment.STATUS_CHOICES
        context['selected_fields'] = selected_fields
        context['selected_types'] = selected_types
        context['selected_statuses'] = selected_statuses
        context['selected_products'] = selected_products
        context['date_from'] = date_from
        context['date_to'] = date_to
        context['product_types'] = ProductType.ownership_objects.get_queryset_for_user(self.request.user)
        context['selected_product_types'] = selected_product_types
        context['total_count'] = self.get_queryset().count()
        context['available_fields'] = Field.ownership_objects.get_queryset_for_user(self.request.user)
        context['search_query'] = search_query
        context['sort'] = sort

        active_filter_count = (
            len(selected_fields)
            + len(selected_types)
            + len(selected_products)
            + len(selected_product_types)
            + (1 if date_from or date_to else 0)
            + (1 if search_query else 0)
            + (len(selected_statuses) if self.request.GET.getlist('status') else 0)
        )
        context['active_filter_count'] = active_filter_count

        query_params = self.request.GET.copy()
        if 'page' in query_params:
            del query_params['page']
        context['query_params'] = query_params.urlencode()

        return context


class TreatmentDetailView(BaseSecureViewMixin, DetailView):
    model = Treatment
    template_name = 'farm/treatments/treatment_detail.html'
    context_object_name = 'treatment'

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("field", "machine")
            .prefetch_related("treatmentproduct_set__product__product_type")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['status_choices'] = Treatment.STATUS_CHOICES

        products = self.object.treatmentproduct_set.all()
        context['products'] = products

        total_cost = sum(product.total_price for product in products)
        cost_per_ha = 0
        if self.object.field and self.object.field.area > 0:
            cost_per_ha = total_cost / Decimal(self.object.field.area)

        context['total_cost'] = total_cost
        context['cost_per_ha'] = cost_per_ha
        context['available_fields'] = (
            Field.ownership_objects
            .get_queryset_for_user(self.request.user)
            .exclude(pk=self.object.field_id)
        )

        return context


class TreatmentFormView(BaseSecureViewMixin, SuccessMessageMixin, UpdateView):
    model = Treatment
    form_class = TreatmentForm
    template_name = 'farm/treatments/treatment_form.html'

    def get_object(self, queryset=None):
        if 'pk' not in self.kwargs:
            return None
        return super().get_object(queryset)

    def get_success_url(self):
        return reverse('treatment-detail', kwargs={'pk': self.object.id})

    def get_success_message(self, cleaned_data):
        return f"Tratamiento '{cleaned_data['name']}' guardado exitosamente"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_edit'] = bool(self.object and self.object.pk)
        context['form_title'] = 'Editar tratamiento' if context['is_edit'] else 'Nuevo tratamiento'

        # Usar el formset ya validado (con errores) si existe; si no, crear uno nuevo.
        if hasattr(self, '_products_formset'):
            context['products_formset'] = self._products_formset
        elif self.request.POST:
            context['products_formset'] = TreatmentProductFormSet(self.request.POST, instance=self.object)
        else:
            context['products_formset'] = TreatmentProductFormSet(instance=self.object)

        # Indicar al template si hay errores en el formset para navegar al paso 2
        fs = context['products_formset']
        context['has_formset_errors'] = bool(
            any(fs.errors) or fs.non_form_errors()
        ) if hasattr(self, '_products_formset') else False

        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.get_form()
        # Guardar referencia al formset validado para reutilizarlo en get_context_data
        self._products_formset = TreatmentProductFormSet(request.POST, instance=self.object)
        if form.is_valid() and self._products_formset.is_valid():
            self.object = save_treatment_with_products(form, self._products_formset)
            return self.form_valid(form)
        return self.form_invalid(form)


class TreatmentCalendarView(BaseSecureViewMixin, TemplateView):
    template_name = 'farm/treatments/calendar.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['fields'] = Field.ownership_objects.get_queryset_for_user(self.request.user)
        context['treatment_types'] = Treatment.TYPE_CHOICES
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

        from accounts.models import Notification
        from accounts.notification_service import notify_org_users
        notify_org_users(
            event_type=Notification.EVENT_TREATMENT_FINISHED,
            title=f'Tratamiento finalizado: {treatment.name}',
            body=f'El tratamiento "{treatment.name}" en {treatment.field.name} ha sido marcado como completado.',
            link=reverse('treatment-detail', kwargs={'pk': treatment.pk}),
            organization=treatment.organization,
        )

        return JsonResponse({'success': True})


@method_decorator(require_POST, name='dispatch')
class DeleteTreatmentView(BaseSecureViewMixin, View):
    def post(self, request, pk):
        treatment = get_object_or_404(Treatment, pk=pk)
        treatment.delete()
        messages.success(request, f'Tratamiento "{treatment.name}" eliminado')
        return redirect('treatment-list')


class CloneTreatmentView(BaseSecureViewMixin, View):
    template_name = 'farm/treatments/treatment_clone.html'

    def get_treatment(self, pk):
        return get_object_or_404(Treatment, pk=pk)

    def get(self, request, pk):
        treatment = self.get_treatment(pk)
        available_fields = (
            Field.ownership_objects
            .get_queryset_for_user(request.user)
            .exclude(pk=treatment.field_id)
        )
        return render(request, self.template_name, {
            'treatment': treatment,
            'available_fields': available_fields,
        })

    def post(self, request, pk):
        treatment = self.get_treatment(pk)

        field_ids = request.POST.getlist('field_id')
        date_str = request.POST.get('date')

        if not field_ids:
            messages.error(request, 'Debes seleccionar al menos una parcela de destino.')
            return redirect('treatment-clone', pk=pk)

        cloned = []
        for field_id in field_ids:
            target_field = get_object_or_404(Field, pk=field_id, organization=request.user.organization)
            new_name = request.POST.get(f'name_{field_id}', '').strip() or None
            per_field_date = request.POST.get(f'date_{field_id}', '').strip()
            try:
                new_date = date.fromisoformat(per_field_date) if per_field_date else (
                    date.fromisoformat(date_str) if date_str else None
                )
            except ValueError:
                new_date = None
            cloned.append(clone_treatment(treatment, target_field, new_date, new_name))

        if len(cloned) == 1:
            messages.success(request, f'Tratamiento clonado en {cloned[0].field.name}.')
            return redirect('treatment-detail', pk=cloned[0].pk)
        else:
            field_names = ', '.join(t.field.name for t in cloned)
            messages.success(request, f'Tratamiento clonado en: {field_names}.')
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
        return context


class ShoppingListView(BaseSecureViewMixin, ListView):
    template_name = 'farm/treatments/shopping_list.html'
    context_object_name = 'product_items'

    def get_queryset(self):
        selected_fields = [fid for fid in self.request.GET.getlist('field') if fid.isdigit()]
        return get_shopping_list(self.request.user, field_ids=selected_fields or None)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['fields'] = Field.objects.filter(organization=self.request.user.organization)
        context['selected_fields'] = [fid for fid in self.request.GET.getlist('field') if fid.isdigit()]
        total_price = sum(item['total_price'] for item in self.object_list)
        context['total_price'] = round(total_price, 2)
        context['total_count'] = len(self.object_list)
        return context

