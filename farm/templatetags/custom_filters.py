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
