import json

from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Exists, OuterRef, Count, Sum, Q, Prefetch, RestrictedError
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy, reverse
from django.utils import timezone
from django.views.generic import ListView, UpdateView, DeleteView, View, TemplateView, RedirectView

from farm.forms import ProductForm, ProductTypeForm
from farm.mixins import OwnershipRequiredMixin, QuerysetFilterMixin, AuditableMixin
from farm.models import Product, ProductType, Treatment, TreatmentProduct, ProductPriceHistory

# Máximo de productos que admite la comparativa (más no caben en pantalla)
COMPARISON_MAX_PRODUCTS = 12


class BaseSecureProductViewMixin(OwnershipRequiredMixin, QuerysetFilterMixin):
    """Mixin base que aplica control de acceso y filtrado para productos."""
    pass


class BaseSecureProductFormMixin(BaseSecureProductViewMixin, AuditableMixin):
    """Mixin para vistas de formularios de productos que incluye auditoría."""
    pass


def _price_trend(product):
    """
    Variación del precio respecto al anterior del historial. None si no hay
    dos precios que comparar (la mayoría de productos solo tiene uno).
    `product.price_history` viene precargado, del más reciente al más antiguo.
    """
    history = list(product.price_history.all())
    if len(history) < 2 or history[0].price != product.price:
        return None
    latest, previous = history[0], history[1]
    if not previous.price or previous.price == latest.price:
        return None
    change = (latest.price - previous.price) / previous.price * 100
    return {
        'up': latest.price > previous.price,
        'percent': abs(round(change)),
        'since': latest.effective_date,
        'previous_price': previous.price,
    }


class ProductListView(BaseSecureProductViewMixin, ListView):
    """
    Listado único de productos: tipos (chips), uso en el año, coste/ha y
    selección para la comparativa. Sin paginación: se filtra por tipo y la
    explotación tiene pocas decenas de productos.
    """
    model = Product
    template_name = 'farm/products/product_list.html'
    context_object_name = 'products'
    ordering = ['name']

    def _show_archived(self):
        return self.request.GET.get('archived') == '1'

    def get_queryset(self):
        year = timezone.localdate().year
        tp = 'treatmentproduct__treatment'
        # Gastado = tratamientos completados este año (por fecha de finalización).
        done_this_year = Q(**{f'{tp}__status': Treatment.STATUS_COMPLETED}) & (
            Q(**{f'{tp}__finish_date__year': year})
            | Q(**{f'{tp}__finish_date__isnull': True, f'{tp}__date__year': year})
        )
        # Previsto = los que aún no se han hecho (pendientes y atrasados).
        planned = Q(**{f'{tp}__status__in': [Treatment.STATUS_PENDING, Treatment.STATUS_DELAYED]})

        qs = (
            super().get_queryset()
            .select_related('product_type')
            .prefetch_related(Prefetch(
                'price_history',
                queryset=ProductPriceHistory.objects.order_by('-effective_date', '-created_at'),
            ))
            .annotate(
                has_treatments=Exists(TreatmentProduct.objects.filter(product=OuterRef('pk'))),
                done_count=Count('treatmentproduct', filter=done_this_year),
                spent=Sum('treatmentproduct__total_price', filter=done_this_year),
                planned_count=Count('treatmentproduct', filter=planned),
                planned_cost=Sum('treatmentproduct__total_price', filter=planned),
            )
        )

        if not self._show_archived():
            qs = qs.filter(is_active=True)

        # La búsqueda por nombre es del navegador (instantánea): aquí solo filtros de servidor.
        type_id = self.request.GET.get('type')
        application = self.request.GET.get('application')

        if type_id and type_id.isdigit():
            qs = qs.filter(product_type_id=type_id)
        if application == 'spraying':
            qs = qs.filter(spraying_dose__isnull=False)
        elif application == 'fertigation':
            qs = qs.filter(fertigation_dose__isnull=False)
        if self.request.GET.get('no_price') == '1':
            qs = qs.filter(price__lte=0)

        return qs.order_by('name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        show_archived = self._show_archived()

        # Atributos de presentación que no son columnas: se calculan una vez por producto
        products = list(context['products'])
        for product in products:
            product.cost_spraying = product.cost_per_ha('spraying')
            product.cost_fertigation = product.cost_per_ha('fertigation')
            product.price_trend = _price_trend(product)
        context['products'] = products

        # Chips de tipo: solo los que tienen productos visibles (los vacíos se ven al gestionar tipos)
        visible = Q(product__is_active=True) if not show_archived else Q()
        product_types = list(
            ProductType.ownership_objects.get_queryset_for_user(user)
            .annotate(
                visible_count=Count('product', filter=visible),
                product_count=Count('product'),
            )
            .order_by('name')
        )
        selected_type = self.request.GET.get('type', '')
        context['type_chips'] = [
            pt for pt in product_types
            if pt.visible_count or str(pt.pk) == selected_type
        ]
        context['product_types'] = product_types  # para «Gestionar tipos» (con todos)
        context['total_visible'] = sum(pt.visible_count for pt in product_types)

        base_qs = super().get_queryset()
        context['no_price_count'] = base_qs.filter(is_active=True, price__lte=0).count()
        context['archived_count'] = base_qs.filter(is_active=False).count()

        context['selected_type'] = selected_type
        context['selected_type_name'] = next(
            (pt.name for pt in product_types if str(pt.pk) == selected_type), '')
        context['selected_application'] = self.request.GET.get('application', '')
        context['show_archived'] = show_archived
        context['only_no_price'] = self.request.GET.get('no_price') == '1'
        context['reference_water'] = Product.REFERENCE_WATER_PER_HA
        context['current_year'] = timezone.localdate().year
        context['max_compare'] = COMPARISON_MAX_PRODUCTS
        context['has_filters'] = bool(
            selected_type or context['selected_application']
            or context['only_no_price'] or show_archived
        )
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
        today = timezone.localdate()

        if self.creating:
            # El precio de alta es el primero del historial: sin él no habría
            # con qué comparar cuando cambie (la tendencia necesita dos precios).
            if new_price and new_price > 0:
                ProductPriceHistory.objects.create(
                    product=self.object,
                    price=new_price,
                    effective_date=today,
                    organization=self.object.organization,
                )
        elif old_price is not None and new_price != old_price and new_price > 0:
            # Productos anteriores a este cambio: si no tienen historial, se guarda
            # primero el precio que tenían para poder mostrar la variación.
            if old_price > 0 and not self.object.price_history.exists():
                created = self.object.created_at.date() if self.object.created_at else None
                if created:
                    ProductPriceHistory.objects.create(
                        product=self.object,
                        price=old_price,
                        effective_date=created,
                        organization=self.object.organization,
                    )
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
            context['price_history_json'] = json.dumps([
                {'date': e.effective_date.strftime('%d/%m/%Y'), 'price': float(e.price)}
                for e in reversed(history)  # oldest first for chart X axis
            ])
        return context


class ProductDeleteView(BaseSecureProductViewMixin, DeleteView):
    model = Product
    success_url = reverse_lazy('product-list')

    def form_valid(self, form):
        # Django 5.1 ya no llama a delete() desde DeleteView: el mensaje va aquí.
        try:
            response = super().form_valid(form)
        except RestrictedError:
            messages.error(self.request, 'No se puede eliminar: el producto se ha usado en tratamientos. '
                                         'Archívalo desde su ficha.')
            return redirect('product-list')
        messages.success(self.request, 'Producto eliminado con éxito.')
        return response


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


# ── Tipos de producto ──────────────────────────────────────────────────────
# El listado vive dentro de Productos (chips + «Gestionar tipos»); aquí quedan
# las vistas de alta, edición y borrado.

class ProductTypeListRedirectView(RedirectView):
    """La antigua pantalla de tipos se ha integrado en Productos."""
    pattern_name = 'product-list'
    permanent = False


class ProductTypeFormView(BaseSecureProductFormMixin, SuccessMessageMixin, UpdateView):
    """Alta y edición de tipos. Con `X-Requested-With: XMLHttpRequest` responde JSON
    (alta rápida desde el formulario de producto)."""
    model = ProductType
    form_class = ProductTypeForm
    template_name = 'farm/products/product_type_form.html'
    success_url = reverse_lazy('product-list')

    def _is_ajax(self):
        return self.request.headers.get('x-requested-with') == 'XMLHttpRequest'

    def get_object(self, queryset=None):
        """Return existing object for edit, or None for create"""
        if 'pk' in self.kwargs:
            return super().get_object(queryset)
        return None

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        # La organización se fija antes de validar para que el formulario pueda
        # comprobar que el nombre no está repetido en ella.
        if kwargs.get('instance') is None:
            kwargs['instance'] = ProductType(organization=self.request.user.organization)
        return kwargs

    def get_success_message(self, cleaned_data):
        if self._is_ajax():
            return ''  # el mensaje saldría en la siguiente pantalla, ya sin sentido
        if self.object and self.object.pk and 'pk' in self.kwargs:
            return 'Tipo de producto actualizado con éxito.'
        return 'Tipo de producto creado con éxito.'

    def form_valid(self, form):
        response = super().form_valid(form)
        if self._is_ajax():
            return JsonResponse({'id': self.object.pk, 'name': self.object.name},
                                status=200 if 'pk' in self.kwargs else 201)
        return response

    def form_invalid(self, form):
        if self._is_ajax():
            errors = [e for errs in form.errors.values() for e in errs]
            return JsonResponse({'errors': errors}, status=400)
        return super().form_invalid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.object and self.object.pk:
            context['object'].has_products = Product.objects.filter(
                product_type=self.object
            ).exists()
        return context


class ProductComparisonView(BaseSecureProductViewMixin, TemplateView):
    """Calculadora para comparar el coste/ha de varios productos alternativos.
    Admite `?ids=1,2,3` (productos marcados en el listado) para abrirla ya cargada."""
    template_name = 'farm/products/product_comparison.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        requested = []
        for raw in self.request.GET.get('ids', '').split(','):
            raw = raw.strip()
            if raw.isdigit() and int(raw) not in requested:
                requested.append(int(raw))
        requested = requested[:COMPARISON_MAX_PRODUCTS]
        # Solo los del usuario: un id ajeno se ignora sin más
        allowed = set(
            Product.ownership_objects.get_queryset_for_user(self.request.user)
            .filter(pk__in=requested).values_list('pk', flat=True)
        )
        context['initial_ids'] = [pk for pk in requested if pk in allowed]
        context['max_products'] = COMPARISON_MAX_PRODUCTS
        context['reference_water'] = Product.REFERENCE_WATER_PER_HA
        return context


class ProductTypeDeleteView(BaseSecureProductViewMixin, DeleteView):
    model = ProductType
    success_url = reverse_lazy('product-list')

    def form_valid(self, form):
        # Django 5.1 ya no llama a delete() desde DeleteView: el mensaje va aquí.
        try:
            response = super().form_valid(form)
        except RestrictedError:
            messages.error(self.request, 'No se puede eliminar: hay productos de este tipo.')
            return redirect('product-list')
        messages.success(self.request, 'Tipo de producto eliminado con éxito.')
        return response
