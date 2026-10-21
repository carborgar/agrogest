from datetime import date

from django import template

from farm.models import Product

register = template.Library()


@register.filter
def get_item(dictionary, key):
    return dictionary.get(key, '')


@register.filter
def dose_type(type):
    return dict(Product.ALL_DOSE_TYPE_CHOICES).get(type, '')


# ---------------------------------------------------------------------------
# Presentación de tratamientos
# ---------------------------------------------------------------------------

_STATUS_CLASS = {
    'pending': 'warning',
    'completed': 'success',
    'delayed': 'danger',
}

_TYPE_ICON = {
    'spraying': 'spray-can-sparkles',
    'fertigation': 'droplet',
}


@register.filter
def treatment_state_class(treatment):
    """Devuelve la clase Bootstrap de color para el estado del tratamiento."""
    return _STATUS_CLASS.get(treatment.status, 'secondary')


@register.filter
def treatment_type_icon(treatment):
    """Devuelve el nombre del icono FontAwesome para el tipo de tratamiento."""
    return _TYPE_ICON.get(treatment.type, 'flask')


@register.filter
def type_icon(type_value):
    """Devuelve el nombre del icono FontAwesome para un valor de tipo (string)."""
    return _TYPE_ICON.get(type_value, 'flask')


@register.filter
def fmt_dose(value):
    """Formatea una dosis eliminando ceros finales (hasta 4 decimales).
    Funciona correctamente con objetos Decimal que tienen ceros significativos
    (ej: Decimal('0.0750') → '0,075').
    """
    if value is None:
        return ''
    try:
        from decimal import Decimal
        from django.utils.formats import number_format
        # Normalizar: quitar ceros finales usando str formatting
        formatted = f'{Decimal(str(value)):.4f}'.rstrip('0').rstrip('.')
        # Volver a Decimal para que number_format aplique el separador decimal del locale
        return number_format(Decimal(formatted), decimal_pos=len(formatted.split('.')[-1]) if '.' in formatted else 0)
    except Exception:
        return value




# ---------------------------------------------------------------------------
# Listado de tratamientos (modo lista)
# Las plantillas no pueden llamar a métodos con argumentos, de ahí estos filtros.
# ---------------------------------------------------------------------------

_URGENCY_LABEL = {0: 'Atrasados', 1: 'Próximos 15 días', 2: 'Más adelante', 3: 'Completados'}
_URGENCY_CLASS = {0: 'danger', 1: 'warning', 2: 'secondary', 3: 'success'}


@register.filter
def partial_load_dose(treatment_product):
    """Dosis de producto para la última cuba (parcial) del tratamiento."""
    return treatment_product.treatment.calculate_product_for_partial_load(treatment_product)


@register.filter
def treatment_total_cost(treatment):
    """Coste total de los productos del tratamiento (usa el prefetch, sin consultas extra)."""
    return sum(tp.total_price for tp in treatment.treatmentproduct_set.all())


@register.filter
def relative_days(value):
    """Texto relativo a hoy: 'hoy', 'mañana', 'en N d' o 'hace N d'."""
    if not value:
        return ''
    delta = (value - date.today()).days
    if delta == 0:
        return 'hoy'
    if delta == 1:
        return 'mañana'
    if delta > 0:
        return f'en {delta} d'
    return f'hace {-delta} d'


@register.filter
def urgency_label(group):
    """Etiqueta del grupo de urgencia (0-3)."""
    return _URGENCY_LABEL.get(group, '')


@register.filter
def urgency_class(group):
    """Clase Bootstrap de color del grupo de urgencia (0-3)."""
    return _URGENCY_CLASS.get(group, 'secondary')


@register.filter
def treatment_cost_per_ha(treatment):
    """Coste por hectárea del tratamiento (suma de price_per_ha de sus productos)."""
    return sum(tp.price_per_ha for tp in treatment.treatmentproduct_set.all())


@register.filter
def days_from_today(value):
    """Días desde hoy hasta la fecha: positivo = futuro, negativo = pasado (retraso)."""
    if not value:
        return 0
    return (value - date.today()).days


@register.filter
def treatment_tone(treatment):
    """Tono de urgencia (0 atrasado · 1 próximos · 2 más adelante · 3 completado), calculado por fechas
    y no por `status`, que puede estar desfasado. Mismo criterio que los grupos del listado."""
    from datetime import timedelta
    from farm.models import Treatment
    if treatment.finish_date:
        return 3
    today = date.today()
    if treatment.date < today:
        return 0
    if treatment.date <= today + timedelta(days=Treatment.UPCOMING_DAYS):
        return 1
    return 2
