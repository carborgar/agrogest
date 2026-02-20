from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Exists, OuterRef, Count
from django.urls import reverse_lazy
from django.views.generic import ListView, UpdateView, DeleteView

from farm.forms import ProductForm, ProductTypeForm
from farm.mixins import OwnershipRequiredMixin, QuerysetFilterMixin, AuditableMixin
from farm.models import Product, ProductType, TreatmentProduct


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
        qs = (
            super().get_queryset()
            .select_related("product_type")
            .annotate(
                has_treatments=Exists(TreatmentProduct.objects.filter(product=OuterRef('pk')))
            )
        )

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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.object and self.object.pk:
            context['object'].has_treatments = TreatmentProduct.objects.filter(
                product=self.object
            ).exists()
        return context


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
