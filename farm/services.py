"""
Capa de servicios para la lógica de negocio relacionada con tratamientos.

Las vistas llaman a estas funciones en lugar de mezclar lógica de negocio
con lógica HTTP. Así, si mañana añadimos bulk-create o clone, solo
necesitamos ampliar este módulo sin tocar las vistas.
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import F, OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce
from django.urls import reverse
from django.utils.timezone import now

from .models import Product, ProductPriceHistory, TreatmentProduct


# ── Utilidades de email ────────────────────────────────────────────────────────

_DOSE_TYPE_LABELS = dict(Product.ALL_DOSE_TYPE_CHOICES)

_ROW_STYLE = 'padding:6px 10px;border-bottom:1px solid #e2e8f0;'
_HEADER_STYLE = (
    'padding:6px 10px;background:#f1f5f9;font-weight:600;'
    'font-size:.8rem;color:#64748b;text-transform:uppercase;letter-spacing:.04em;'
)


def build_treatment_email_html(treatment, extra_rows=None):
    """
    Construye el bloque HTML de detalle de un tratamiento para emails.

    Incluye: parcela, tipo, fecha, mojado (si procede) y tabla de productos.

    Parámetros
    ----------
    treatment  : instancia de Treatment (con treatmentproduct_set disponible)
    extra_rows : lista de tuplas (etiqueta, valor) adicionales a incluir antes
                 del bloque de productos, o None.

    Devuelve
    --------
    str con el HTML del bloque de detalle.
    """
    # ── Filas de metadatos ────────────────────────────────────────────────────
    meta_rows = [
        ('Parcela', f"{treatment.field.name} ({treatment.effective_area} ha)"),
        ('Tipo', treatment.get_type_display()),
        ('Fecha planificada', treatment.date.strftime('%d/%m/%Y')),
    ]
    if treatment.is_spraying() and treatment.water_per_ha:
        meta_rows.append(('Mojado', f"{treatment.water_per_ha} L/ha"))
    if extra_rows:
        meta_rows.extend(extra_rows)

    meta_html = ''.join(
        f'<tr>'
        f'<td style="{_ROW_STYLE}font-weight:600;width:40%;color:#1a2332;">{label}</td>'
        f'<td style="{_ROW_STYLE}color:#475569;">{value}</td>'
        f'</tr>'
        for label, value in meta_rows
    )

    # ── Tabla de productos ────────────────────────────────────────────────────
    products = list(
        treatment.treatmentproduct_set.select_related('product').order_by('position')
    )

    if products:
        product_rows = ''.join(
            f'<tr>'
            f'<td style="{_ROW_STYLE}color:#1a2332;">{tp.product.name}</td>'
            f'<td style="{_ROW_STYLE}color:#475569;text-align:right;">'
            f'{float(tp.dose):g} {_DOSE_TYPE_LABELS.get(tp.dose_type, tp.dose_type)}'
            f'</td>'
            f'<td style="{_ROW_STYLE}color:#475569;text-align:right;">'
            f'{float(tp.total_dose):g} {tp.total_dose_unit}'
            f'</td>'
            f'</tr>'
            for tp in products
        )
        products_block = (
            f'<p style="margin:16px 0 6px;font-weight:600;font-size:.9rem;">Productos</p>'
            f'<table style="width:100%;border-collapse:collapse;font-size:.875rem;">'
            f'<thead><tr>'
            f'<th style="{_HEADER_STYLE}text-align:left;">Producto</th>'
            f'<th style="{_HEADER_STYLE}text-align:right;">Dosis</th>'
            f'<th style="{_HEADER_STYLE}text-align:right;">Total</th>'
            f'</tr></thead>'
            f'<tbody>{product_rows}</tbody>'
            f'</table>'
        )
    else:
        products_block = ''

    return (
        f'<table style="width:100%;border-collapse:collapse;font-size:.875rem;margin-bottom:4px;">'
        f'<tbody>{meta_html}</tbody>'
        f'</table>'
        f'{products_block}'
    )


@dataclass
class TreatmentCostRecalculationImpact:
    total_treatment_products: int
    total_treatments: int


@dataclass
class TreatmentCostRecalculationResult:
    scanned_treatment_products: int
    scanned_treatments: int
    updated_treatment_products: int
    unchanged_treatment_products: int
    failed_treatment_products: int


def _latest_price_subquery(as_of_date):
    return ProductPriceHistory.objects.filter(
        product_id=OuterRef('product_id'),
        effective_date__lte=as_of_date,
    ).order_by('-effective_date', '-created_at').values('price')[:1]


def _treatment_product_queryset(*, organization=None, start_date=None, end_date=None, product_id=None):
    filters = Q()
    if organization is not None:
        filters &= Q(organization=organization)
    if start_date is not None:
        filters &= Q(treatment__date__gte=start_date)
    if end_date is not None:
        filters &= Q(treatment__date__lte=end_date)
    if product_id is not None:
        filters &= Q(product_id=product_id)

    return TreatmentProduct.objects.filter(filters)


def estimate_treatment_cost_recalculation(
        *,
        organization=None,
        start_date=None,
        end_date=None,
        product_id=None,
):
    queryset = _treatment_product_queryset(
        organization=organization,
        start_date=start_date,
        end_date=end_date,
        product_id=product_id,
    )
    return TreatmentCostRecalculationImpact(
        total_treatment_products=queryset.count(),
        total_treatments=queryset.values('treatment_id').distinct().count(),
    )


def recalculate_treatment_costs(
        *,
        organization=None,
        start_date=None,
        end_date=None,
        product_id=None,
        as_of_date=None,
        dry_run=False,
        batch_size=500,
):
    as_of_date = as_of_date or date.today()
    queryset = _treatment_product_queryset(
        organization=organization,
        start_date=start_date,
        end_date=end_date,
        product_id=product_id,
    )

    annotated_queryset = (
        queryset
        .select_related('treatment__field')
        .annotate(
            latest_price=Coalesce(
                Subquery(_latest_price_subquery(as_of_date)),
                F('product__price'),
                Value(Decimal('0.00')),
            )
        )
    )

    updated = 0
    unchanged = 0
    failed = 0
    to_update = []
    update_timestamp = now()

    for treatment_product in annotated_queryset.iterator(chunk_size=batch_size):
        try:
            latest_price = treatment_product.latest_price or Decimal('0.00')
            if treatment_product.unit_price == latest_price:
                unchanged += 1
                continue

            treatment_product.unit_price = latest_price
            treatment_product.total_price = latest_price * treatment_product.total_dose

            field_area = Decimal(str(treatment_product.treatment.effective_area or 0))
            if field_area > 0:
                treatment_product.price_per_ha = treatment_product.total_price / field_area
            else:
                treatment_product.price_per_ha = Decimal('0.00')

            treatment_product.updated_at = update_timestamp
            to_update.append(treatment_product)

            if len(to_update) >= batch_size:
                if not dry_run:
                    TreatmentProduct.objects.bulk_update(
                        to_update,
                        ['unit_price', 'total_price', 'price_per_ha', 'updated_at'],
                        batch_size=batch_size,
                    )
                updated += len(to_update)
                to_update.clear()
        except Exception:
            failed += 1

    if to_update:
        if not dry_run:
            TreatmentProduct.objects.bulk_update(
                to_update,
                ['unit_price', 'total_price', 'price_per_ha', 'updated_at'],
                batch_size=batch_size,
            )
        updated += len(to_update)

    impact = estimate_treatment_cost_recalculation(
        organization=organization,
        start_date=start_date,
        end_date=end_date,
        product_id=product_id,
    )

    return TreatmentCostRecalculationResult(
        scanned_treatment_products=impact.total_treatment_products,
        scanned_treatments=impact.total_treatments,
        updated_treatment_products=updated,
        unchanged_treatment_products=unchanged,
        failed_treatment_products=failed,
    )


@transaction.atomic
def save_treatment_with_products(treatment_form, products_formset):
    """
    Guarda (crea o actualiza) un tratamiento junto con su formset de
    productos en una transacción atómica. Funciona tanto para nuevos
    tratamientos como para ediciones — la distinción la hace el propio
    ModelForm según tenga o no instance.

    Parámetros
    ----------
    treatment_form    : TreatmentForm ya validado (is_valid() == True)
    products_formset  : TreatmentProductFormSet ya validado

    Devuelve
    --------
    El Treatment creado o actualizado.
    """
    is_new = treatment_form.instance.pk is None
    treatment = treatment_form.save()
    products_formset.instance = treatment
    products_formset.save()

    if is_new:
        from accounts.models import Notification
        from accounts.notification_service import notify_org_users
        products = list(treatment.treatmentproduct_set.select_related('product').order_by('position'))
        product_names = ', '.join(tp.product.name for tp in products) if products else 'Sin productos'
        notify_org_users(
            event_type=Notification.EVENT_TREATMENT_CREATED,
            title=f'Nuevo tratamiento: {treatment.name}',
            body=(
                f'Se ha creado el tratamiento "{treatment.name}" en la parcela {treatment.field.name}.'
                + (f' Productos: {product_names}.' if products else '')
            ),
            link=reverse('treatment-detail', kwargs={'pk': treatment.pk}),
            organization=treatment.organization,
            html_body=build_treatment_email_html(treatment),
        )

    return treatment


def get_shopping_list(user, field_ids=None, treatment_ids=None):
    """
    Devuelve un listado agregado de productos necesarios para los
    tratamientos pendientes/atrasados del usuario.

    Parámetros
    ----------
    user           : usuario autenticado
    field_ids      : lista de IDs de parcela para filtrar (None = todas)
    treatment_ids  : lista de IDs de tratamiento para filtrar (None = todos)

    Devuelve
    --------
    list[dict] ordenada por nombre de producto, con las claves:
        product, product_name, product_type, unit,
        total_dose, total_price, treatment_count, fields,
        breakdown: list[{field, treatment, dose, unit}],
        distribution_groups: list[{name, is_manual, group_total, unit, fields}]
    """

    queryset = (
        TreatmentProduct.ownership_objects
        .get_queryset_for_user(user)
        .filter(treatment__status__in=['pending', 'delayed'])
        .select_related('product', 'product__product_type', 'treatment', 'treatment__field', 'treatment__field__storage_point')
        .order_by('treatment__field__name', 'treatment__date')
    )

    if field_ids:
        queryset = queryset.filter(treatment__field_id__in=field_ids)

    if treatment_ids:
        queryset = queryset.filter(treatment_id__in=treatment_ids)

    product_totals = {}
    for item in queryset:
        key = (item.product_id, item.total_dose_unit)
        if key not in product_totals:
            product_totals[key] = {
                'product': item.product,
                'product_name': item.product.name,
                'product_type': item.product.product_type.name,
                'unit': item.total_dose_unit,
                'total_dose': Decimal('0'),
                'total_price': Decimal('0'),
                'treatment_count': 0,
                'fields': set(),
                'breakdown': [],
            }
        product_totals[key]['total_dose'] += item.total_dose
        product_totals[key]['total_price'] += item.total_price
        product_totals[key]['treatment_count'] += 1
        product_totals[key]['fields'].add(item.treatment.field.name)
        product_totals[key]['breakdown'].append({
            'field_id': item.treatment.field.id,
            'field': item.treatment.field.name,
            'field_area': Decimal(str(item.treatment.field.area)) if item.treatment.field.area else Decimal('0'),
            'storage_point_id': item.treatment.field.storage_point_id,
            'storage_point_name': item.treatment.field.storage_point.name if item.treatment.field.storage_point_id else None,
            'treatment': item.treatment.name,
            'dose': round(item.total_dose, 2),
            'unit': item.total_dose_unit,
            'price': item.total_price,
        })

    result = []
    for data in product_totals.values():
        data['fields'] = ', '.join(sorted(data['fields']))
        data['total_dose'] = round(data['total_dose'], 2)
        data['total_price'] = round(data['total_price'], 2)

        # Agrupar breakdown por parcela (para mostrar total por parcela + detalle)
        field_groups: dict = {}
        for b in data['breakdown']:
            fn = b['field']
            if fn not in field_groups:
                field_groups[fn] = {
                    'field_id': b['field_id'],
                    'field': fn,
                    'field_total': Decimal('0'),
                    'field_price': Decimal('0'),
                    'field_area': b['field_area'],
                    'storage_point_id': b['storage_point_id'],
                    'storage_point_name': b['storage_point_name'],
                    'unit': b['unit'],
                    'treatments': [],
                }
            field_groups[fn]['field_total'] += b['dose']
            field_groups[fn]['field_price'] += b.get('price', Decimal('0'))
            field_groups[fn]['treatments'].append({
                'treatment': b['treatment'],
                'dose': b['dose'],
            })

        # Calcular €/ha del producto: precio total / suma de ha únicas involucradas
        unique_ha = sum(
            fg['field_area'] for fg in field_groups.values() if fg['field_area']
        )
        data['total_price_per_ha'] = (
            round(data['total_price'] / unique_ha, 2) if unique_ha else Decimal('0')
        )

        data['breakdown_by_field'] = sorted(
            [
                {
                    **fg,
                    'field_total': round(fg['field_total'], 2),
                    'field_price': round(fg['field_price'], 2),
                    'price_per_ha': round(fg['field_price'] / fg['field_area'], 2)
                    if fg['field_area'] else Decimal('0'),
                }
                for fg in field_groups.values()
            ],
            key=lambda x: x['field'],
        )

        # Agrupar por casetilla para facilitar el reparto.
        # Las parcelas sin casetilla se dejan como grupo manual individual.
        distribution_groups: dict = {}
        for field_group in data['breakdown_by_field']:
            if field_group.get('storage_point_id'):
                group_key = f"sp-{field_group['storage_point_id']}"
                if group_key not in distribution_groups:
                    distribution_groups[group_key] = {
                        'name': field_group['storage_point_name'],
                        'is_manual': False,
                        'group_total': Decimal('0'),
                        'group_price': Decimal('0'),
                        'unit': field_group['unit'],
                        'fields': [],
                    }
            else:
                group_key = f"field-{field_group['field_id']}"
                distribution_groups[group_key] = {
                    'name': field_group['field'],
                    'is_manual': True,
                    'group_total': field_group['field_total'],
                    'group_price': field_group['field_price'],
                    'unit': field_group['unit'],
                    'fields': [field_group],
                }

            if not distribution_groups[group_key]['is_manual']:
                distribution_groups[group_key]['group_total'] += field_group['field_total']
                distribution_groups[group_key]['group_price'] += field_group['field_price']
                distribution_groups[group_key]['fields'].append(field_group)

        data['distribution_groups'] = sorted(
            [
                {
                    **group,
                    'group_total': round(group['group_total'], 2),
                    'group_price': round(group['group_price'], 2),
                }
                for group in distribution_groups.values()
            ],
            key=lambda g: (g['is_manual'], g['name'].lower()),
        )

        result.append(data)

    result.sort(key=lambda x: x['product_name'])
    return result


def clone_treatment(treatment, target_field, new_date=None, new_name=None):
    """
    Clona un tratamiento a otra parcela recalculando las dosis totales
    según el área de la nueva parcela.

    Parámetros
    ----------
    treatment    : Treatment a clonar
    target_field : Field de destino
    new_date     : date opcional; si no se pasa, se conserva la fecha original
    new_name     : str opcional; si no se pasa, se conserva el nombre original

    Devuelve
    --------
    El nuevo Treatment creado.
    """
    return treatment.clone_to_field(target_field, new_date, new_name)
