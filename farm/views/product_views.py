from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Exists, OuterRef, Count
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy, reverse
from django.views.generic import ListView, UpdateView, DeleteView, View

from farm.forms import ProductForm, ProductTypeForm
from farm.mixins import OwnershipRequiredMixin, QuerysetFilterMixin, AuditableMixin
from farm.models import Product, ProductType, TreatmentProduct, ProductPriceHistory


class BaseSecureProductViewMixin(OwnershipRequiredMixin, QuerysetFilterMixin):
    """Mixin base que aplica control de acceso y filtrado para productos."""
    pass


class BaseSecureProductFormMixin(BaseSecureProductViewMixin, AuditableMixin):
    """Mixin para vistas de formularios de productos que incluye auditoría."""
    pass


class ProductListView(BaseSecureProductViewMixin, ListView):
    model = Product
    template_name = 'farm/products/product_list.html'
    context_object_name = 'products'
    paginate_by = 20
    ordering = ['name']

    def get_queryset(self):
        show_archived = self.request.GET.get('archived') == '1'
        qs = (
            super().get_queryset()
            .select_related("product_type")
            .annotate(
                has_treatments=Exists(TreatmentProduct.objects.filter(product=OuterRef('pk')))
            )
        )

        if not show_archived:
            qs = qs.filter(is_active=True)

        search = self.request.GET.get('search', '').strip()
        type_id = self.request.GET.get('type')
        application = self.request.GET.get('application')

        if search:
            qs = qs.filter(name__icontains=search)
        if type_id:
            qs = qs.filter(product_type_id=type_id)
        if application == 'spraying':
            qs = qs.filter(spraying_dose__isnull=False)
        elif application == 'fertigation':
            qs = qs.filter(fertigation_dose__isnull=False)

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['product_types'] = ProductType.ownership_objects.get_queryset_for_user(self.request.user)
        context['filter_params'] = self.request.GET.dict()
        context['search'] = self.request.GET.get('search', '')
        context['selected_type'] = self.request.GET.get('type', '')
        context['selected_application'] = self.request.GET.get('application', '')
        context['show_archived'] = self.request.GET.get('archived') == '1'

        # Productos sin precio (price = 0) – solo activos
        all_qs = (
            super().get_queryset()
            .select_related("product_type")
            .filter(is_active=True)
        )
        context['products_without_price'] = list(
            all_qs.filter(price__lte=0).order_by('name')
        )

        # Conteo de archivados para el toggle
        base_qs = super().get_queryset()
        context['archived_count'] = base_qs.filter(is_active=False).count()

        return context


class ProductFormView(BaseSecureProductFormMixin, SuccessMessageMixin, UpdateView):
    """Unified view for creating and editing products"""
    model = Product
    form_class = ProductForm
    template_name = 'farm/products/product_form.html'
    success_url = reverse_lazy('product-list')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.creating = False

    def get_object(self, queryset=None):
        """Return existing object for edit, or None for create"""
        if 'pk' in self.kwargs:
            return super().get_object(queryset)
        return None

    def get_success_message(self, cleaned_data):
        if self.object and self.creating:
            return 'Producto creado con éxito.'
        return 'Producto actualizado con éxito.'

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        # Filtrar tipos de producto por usuario
        form.fields['product_type'].queryset = ProductType.ownership_objects.get_queryset_for_user(self.request.user)
        return form

    def form_valid(self, form):
        self.creating = not form.instance.pk

        # Solo asignar la organización al crear; en edición el objeto ya la tiene de BD
        if self.creating:
            form.instance.organization = self.request.user.organization
            # En el alta el switch de archivado no se muestra; si no llega en POST,
            # mantenemos el valor por defecto (activo).
            if 'is_active' not in form.data:
                form.instance.is_active = True

        # Detectar cambio de precio para auto-registrar en historial
        old_price = None
        if not self.creating:
            try:
                old_price = Product.objects.get(pk=form.instance.pk).price
            except Product.DoesNotExist:
                pass

        response = super().form_valid(form)

        new_price = form.instance.price
        if (
            not self.creating
            and old_price is not None
            and new_price != old_price
            and new_price > 0
        ):
            ProductPriceHistory.objects.create(
                product=self.object,
                price=new_price,
                effective_date=form.instance.updated_at.date(),
                organization=self.object.organization,
            )

        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.object and self.object.pk:
            context['object'].has_treatments = TreatmentProduct.objects.filter(
                product=self.object
            ).exists()
            history = list(self.object.price_history.all())  # ordered: newest first
            context['price_history'] = history

            # ── Tendencias (newest-first list, compare each entry with the one after) ──
            history_with_trend = []
            for i, entry in enumerate(history):
                if i < len(history) - 1:
                    prev = history[i + 1]  # older entry
                    if entry.price > prev.price:
                        trend = 'up'
                    elif entry.price < prev.price:
                        trend = 'down'
                    else:
                        trend = 'neutral'
                else:
                    trend = 'initial'
                history_with_trend.append({'entry': entry, 'trend': trend})
            context['history_with_trend'] = history_with_trend

            # ── Min / Max ──────────────────────────────────────────────────────────────
            if history:
                max_entry = max(history, key=lambda e: e.price)
                min_entry = min(history, key=lambda e: e.price)
                context['price_max'] = max_entry
                context['price_min'] = min_entry

            # ── JSON seguro para el gráfico ────────────────────────────────────────────
            import json
            context['price_history_json'] = json.dumps([
                {'date': e.effective_date.strftime('%d/%m/%Y'), 'price': float(e.price)}
                for e in reversed(history)  # oldest first for chart X axis
            ])
        return context


class ProductDeleteView(BaseSecureProductViewMixin, DeleteView):
    model = Product
    success_url = reverse_lazy('product-list')

    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Producto eliminado con éxito.')
        return super().delete(request, *args, **kwargs)



class ProductPriceHistoryDeleteView(OwnershipRequiredMixin, View):
    """Elimina una entrada del historial de precios."""

    def post(self, request, pk):
        # Superusers no tienen organización asignada → no filtrar por org
        if request.user.is_superuser:
            entry = get_object_or_404(ProductPriceHistory, pk=pk)
        else:
            entry = get_object_or_404(
                ProductPriceHistory.objects.filter(organization=request.user.organization),
                pk=pk,
            )
        product_pk = entry.product_id
        entry.delete()
        messages.success(request, 'Entrada del historial eliminada.')
        return HttpResponseRedirect(reverse('product-edit', kwargs={'pk': product_pk}))


# ProductType CRUD Views
class ProductTypeListView(BaseSecureProductViewMixin, ListView):
    model = ProductType
    template_name = 'farm/products/product_type_list.html'
    context_object_name = 'product_types'
    ordering = ['name']

    def get_queryset(self):
        qs = super().get_queryset().order_by("name")
        qs = qs.annotate(
            has_products=Exists(Product.objects.filter(product_type=OuterRef('pk'))),
            product_count=Count('product'),
        )
        return qs


class ProductTypeFormView(BaseSecureProductFormMixin, SuccessMessageMixin, UpdateView):
    """Unified view for creating and editing product types"""
    model = ProductType
    form_class = ProductTypeForm
    template_name = 'farm/products/product_type_form.html'
    success_url = reverse_lazy('product-type-list')

    def get_object(self, queryset=None):
        """Return existing object for edit, or None for create"""
        if 'pk' in self.kwargs:
            return super().get_object(queryset)
        return None

    def get_success_message(self, cleaned_data):
        if self.object and self.object.pk:
            return 'Tipo de producto actualizado con éxito.'
        return 'Tipo de producto creado con éxito.'

    def form_valid(self, form):
        # Asignar la organización del usuario al tipo de producto
        form.instance.organization = self.request.user.organization
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.object and self.object.pk:
            context['object'].has_products = Product.objects.filter(
                product_type=self.object
            ).exists()
        return context


class ProductTypeDeleteView(BaseSecureProductViewMixin, DeleteView):
    model = ProductType
    success_url = reverse_lazy('product-type-list')

    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Tipo de producto eliminado con éxito.')
        return super().delete(request, *args, **kwargs)
