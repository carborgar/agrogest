from urllib.parse import urlencode

import time
from datetime import date

from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.generic import TemplateView

from farm.forms import (
    TreatmentCostProductForm,
    TreatmentCostRangeForm,
)
from farm.mixins import BaseSecureViewMixin
from farm.models import Product
from farm.services import estimate_treatment_cost_recalculation, recalculate_treatment_costs


class TreatmentCostRecalculationAdminView(BaseSecureViewMixin, TemplateView):
    template_name = 'farm/admin/treatment_cost_recalculation.html'

    def _product_queryset(self):
        return Product.ownership_objects.get_queryset_for_user(self.request.user).order_by('name')

    def _default_range_initial(self):
        current_year = date.today().year
        return {
            'start_date': f'{current_year}-01-01',
            'end_date': f'{current_year}-12-31',
        }

    def _build_forms(self, *, range_post_data=None, product_post_data=None):
        range_kwargs = {'data': range_post_data} if range_post_data is not None else {
            'initial': self._default_range_initial()
        }
        product_kwargs = {'data': product_post_data} if product_post_data is not None else {}

        context = {
            'range_form': TreatmentCostRangeForm(**range_kwargs),
            'product_form': TreatmentCostProductForm(
                product_queryset=self._product_queryset(),
                **product_kwargs,
            ),
        }
        return context

    def _build_preview_redirect(self, **params):
        return redirect(f"{reverse('treatment-cost-admin')}?{urlencode(params)}")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self._build_forms())
        context.setdefault('range_preview', None)
        context.setdefault('product_preview', None)
        return context

    def get(self, request, *args, **kwargs):
        preview = request.GET.get('preview', '')

        if preview == 'range':
            context = self._build_forms(range_post_data=request.GET)
            context['range_preview'] = None
            context['product_preview'] = None
            range_form = context['range_form']
            if range_form.is_valid():
                context['range_preview'] = estimate_treatment_cost_recalculation(
                    organization=self.request.user.organization,
                    start_date=range_form.cleaned_data['start_date'],
                    end_date=range_form.cleaned_data['end_date'],
                )
            return render(request, self.template_name, context)

        if preview == 'product':
            context = self._build_forms(product_post_data=request.GET)
            context['range_preview'] = None
            context['product_preview'] = None
            product_form = context['product_form']
            if product_form.is_valid():
                selected_product = product_form.cleaned_data['product']
                context['product_preview'] = {
                    'impact': estimate_treatment_cost_recalculation(
                        organization=self.request.user.organization,
                        product_id=selected_product.id,
                    ),
                    'product': selected_product,
                }
            return render(request, self.template_name, context)

        return render(request, self.template_name, self.get_context_data())

    def post(self, request, *args, **kwargs):
        action = request.POST.get('action', '')

        if action in {'preview_range', 'execute_range'}:
            context = self._build_forms(range_post_data=request.POST)
        elif action in {'preview_product', 'execute_product'}:
            context = self._build_forms(product_post_data=request.POST)
        else:
            context = self._build_forms()

        if action == 'preview_range':
            return self._preview_range(context)
        if action == 'execute_range':
            return self._execute_range(context)
        if action == 'preview_product':
            return self._preview_product(context)
        if action == 'execute_product':
            return self._execute_product(context)

        messages.error(request, 'Acción no válida.')
        return render(request, self.template_name, context)

    def _preview_range(self, context):
        range_form = context['range_form']
        if not range_form.is_valid():
            return render(self.request, self.template_name, context)

        return self._build_preview_redirect(
            preview='range',
            start_date=range_form.cleaned_data['start_date'].isoformat(),
            end_date=range_form.cleaned_data['end_date'].isoformat(),
        )

    def _execute_range(self, context):
        range_form = context['range_form']
        if not range_form.is_valid():
            return render(self.request, self.template_name, context)

        impact = estimate_treatment_cost_recalculation(
            organization=self.request.user.organization,
            start_date=range_form.cleaned_data['start_date'],
            end_date=range_form.cleaned_data['end_date'],
        )
        context['range_preview'] = impact

        if impact.total_treatment_products == 0:
            messages.warning(self.request, 'No hay tratamientos para recalcular con ese rango.')
            return redirect('treatment-cost-admin')

        start_time = time.monotonic()
        result = recalculate_treatment_costs(
            organization=self.request.user.organization,
            start_date=range_form.cleaned_data['start_date'],
            end_date=range_form.cleaned_data['end_date'],
        )
        duration = round(time.monotonic() - start_time, 2)
        messages.success(
            self.request,
            (
                f'Recálculo completado en {duration}s. '
                f'Tratamientos revisados: {result.scanned_treatments}. '
                f'Productos actualizados: {result.updated_treatment_products}. '
                f'Sin cambios: {result.unchanged_treatment_products}. '
                f'Errores: {result.failed_treatment_products}.'
            ),
        )
        return redirect('treatment-cost-admin')

    def _preview_product(self, context):
        product_form = context['product_form']
        if not product_form.is_valid():
            return render(self.request, self.template_name, context)

        selected_product = product_form.cleaned_data['product']
        return self._build_preview_redirect(
            preview='product',
            product=selected_product.id,
        )

    def _execute_product(self, context):
        product_form = context['product_form']
        if not product_form.is_valid():
            return render(self.request, self.template_name, context)

        selected_product = product_form.cleaned_data['product']
        impact = estimate_treatment_cost_recalculation(
            organization=self.request.user.organization,
            product_id=selected_product.id,
        )
        context['product_preview'] = {
            'impact': impact,
            'product': selected_product,
        }

        if impact.total_treatment_products == 0:
            messages.warning(self.request, 'No hay tratamientos que recalcular para ese producto.')
            return redirect('treatment-cost-admin')

        start_time = time.monotonic()
        result = recalculate_treatment_costs(
            organization=self.request.user.organization,
            product_id=selected_product.id,
        )
        duration = round(time.monotonic() - start_time, 2)

        messages.success(
            self.request,
            (
                f'Recálculo para {selected_product.name} completado en {duration}s. '
                f'Tratamientos revisados: {result.scanned_treatments}. '
                f'Productos actualizados: {result.updated_treatment_products}. '
                f'Sin cambios: {result.unchanged_treatment_products}. '
                f'Errores: {result.failed_treatment_products}.'
            ),
        )
        return redirect('treatment-cost-admin')

