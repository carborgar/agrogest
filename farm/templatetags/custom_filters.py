from django import template

from farm.models import Product

register = template.Library()


@register.filter
def get_item(dictionary, key):
    return dictionary.get(key, '')


@register.filter
def dose_type(type):
    return dict(Product.ALL_DOSE_TYPE_CHOICES).get(type, '')
