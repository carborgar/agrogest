from django import template

register = template.Library()


@register.filter
def partial_load_product(product_item, treatment):
    """
    Filtro para calcular la cantidad de producto para la carga parcial
    """
    return treatment.calculate_product_for_partial_load(product_item)
