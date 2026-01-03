from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Exists, OuterRef
from django.urls import reverse_lazy
from django.utils.dateparse import parse_date
from django.views.generic import ListView, UpdateView, DeleteView

from farm.forms import ProductForm
from farm.mixins import OwnershipRequiredMixin, QuerysetFilterMixin, AuditableMixin
from farm.models import Product, Field, ProductType, TreatmentProduct


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
    ordering = ['-payment_date']

    def get_queryset(self):
        qs = (
            super().get_queryset()
            .select_related("product_type")
            .annotate(
                has_treatments=Exists(TreatmentProduct.objects.filter(product=OuterRef('pk')))
            )
        )

        field_id = self.request.GET.get('field')  # <select name="field">
        type_id = self.request.GET.get('type')  # <select name="type">
        date_from = self.request.GET.get('date_from')  # <input name="date_from">
        date_to = self.request.GET.get('date_to')  # <input name="date_to">

        if field_id:
            qs = qs.filter(field_id=field_id)
        if type_id:
            qs = qs.filter(product_type_id=type_id)
        if date_from:
            qs = qs.filter(payment_date__gte=parse_date(date_from))
        if date_to:
            qs = qs.filter(payment_date__lte=parse_date(date_to))

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # listas para los combos
        context['fields'] = Field.ownership_objects.get_queryset_for_user(self.request.user)
        context['product_types'] = ProductType.ownership_objects.get_queryset_for_user(self.request.user)

        # mantener los filtros marcados
        context['filter_params'] = self.request.GET.dict()

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
        # Asignar la organización del usuario al producto
        self.creating = not form.instance.pk
        form.instance.organization = self.request.user.organization
        return super().form_valid(form)


class ProductDeleteView(BaseSecureProductViewMixin, DeleteView):
    model = Product
    success_url = reverse_lazy('product-list')

    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Producto eliminado con éxito.')
        return super().delete(request, *args, **kwargs)


# ProductType CRUD Views
class ProductTypeListView(BaseSecureProductViewMixin, ListView):
    model = ProductType
    template_name = 'farm/products/product_type_list.html'
    context_object_name = 'product_types'
    ordering = ['name']

    def get_queryset(self):
        qs = super().get_queryset().order_by("name")
        qs = qs.annotate(
            has_products=Exists(Product.objects.filter(product_type=OuterRef('pk')))
        )
        return qs


class ProductTypeFormView(BaseSecureProductFormMixin, SuccessMessageMixin, UpdateView):
    """Unified view for creating and editing product types"""
    model = ProductType
    template_name = 'farm/products/product_type_form.html'
    fields = ['name', 'description']
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


class ProductTypeDeleteView(BaseSecureProductViewMixin, DeleteView):
    model = ProductType
    success_url = reverse_lazy('product-type-list')

    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Tipo de producto eliminado con éxito.')
        return super().delete(request, *args, **kwargs)
