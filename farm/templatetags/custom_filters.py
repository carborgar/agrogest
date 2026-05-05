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


