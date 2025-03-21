import math

from django import template

register = template.Library()


@register.filter
def multiply(value, arg):
    """Multiplies the value by the argument"""
    return float(value) * float(arg)


@register.filter
def divide(value, arg):
    """Divides the value by the argument"""
    if float(arg) == 0:
        return 0
    return float(value) / float(arg)


@register.filter
def ceiling(value):
    """Returns the ceiling of the value"""
    return math.ceil(float(value))
