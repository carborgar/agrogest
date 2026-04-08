"""
Capa de servicios para la lógica de negocio relacionada con tratamientos.

Las vistas llaman a estas funciones en lugar de mezclar lógica de negocio
con lógica HTTP. Así, si mañana añadimos bulk-create o clone, solo
necesitamos ampliar este módulo sin tocar las vistas.
"""
from django.db import transaction
from django.urls import reverse


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
        notify_org_users(
            event_type=Notification.EVENT_TREATMENT_CREATED,
            title=f'Nuevo tratamiento: {treatment.name}',
            body=f'Se ha creado el tratamiento "{treatment.name}" en la parcela {treatment.field.name}.',
            link=reverse('treatment-detail', kwargs={'pk': treatment.pk}),
            organization=treatment.organization,
        )

    return treatment


def get_shopping_list(user, field_ids=None):
    """
    Devuelve un listado agregado de productos necesarios para los
    tratamientos pendientes/atrasados del usuario.

    Parámetros
    ----------
    user       : usuario autenticado
    field_ids  : lista de IDs de parcela para filtrar (None = todas)

    Devuelve
    --------
    list[dict] ordenada por nombre de producto, con las claves:
        product, product_name, product_type, unit,
        total_dose, total_price, treatment_count, fields
    """
    from decimal import Decimal
    from .models import TreatmentProduct

    queryset = (
        TreatmentProduct.ownership_objects
        .get_queryset_for_user(user)
        .filter(treatment__status__in=['pending', 'delayed'])
        .select_related('product', 'product__product_type', 'treatment', 'treatment__field')
    )

    if field_ids:
        queryset = queryset.filter(treatment__field_id__in=field_ids)

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
            }
        product_totals[key]['total_dose'] += item.total_dose
        product_totals[key]['total_price'] += item.total_price
        product_totals[key]['treatment_count'] += 1
        product_totals[key]['fields'].add(item.treatment.field.name)

    result = []
    for data in product_totals.values():
        data['fields'] = ', '.join(sorted(data['fields']))
        data['total_dose'] = round(data['total_dose'], 2)
        data['total_price'] = round(data['total_price'], 2)
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


