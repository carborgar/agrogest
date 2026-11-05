"""
Nombres → objetos de la organización, sin distinguir mayúsculas ni tildes.

1. Coincidencia exacta: un nombre de parcela da esa parcela; un cultivo da TODAS las que lo tienen.
2. Si no, por contenido. Más de una coincidencia (o ninguna) → ToolError con candidatos para preguntar.

Se filtra en Python: una explotación tiene pocas parcelas y productos, y así la comparación sin tildes
funciona igual en SQLite y en PostgreSQL.
"""
import unicodedata

from assistant.tools.base import ToolError
from farm.models import Field, Product, ProductType


def norm(text):
    text = unicodedata.normalize('NFKD', str(text or ''))
    return ''.join(c for c in text if not unicodedata.combining(c)).casefold().strip()


SINGULAR = {'parcelas': 'ninguna parcela', 'productos': 'ningún producto'}


def _pick(term, items, label):
    """Un objeto por nombre: exacto, o único por contenido."""
    key = norm(term)
    exact = [i for i in items if norm(i.name) == key]
    if exact:
        return exact[0]
    partial = [i for i in items if key and key in norm(i.name)]
    if len(partial) == 1:
        return partial[0]
    if partial:
        raise ToolError(f'«{term}» puede ser varias {label}.', [i.name for i in partial])
    raise ToolError(f'No hay {SINGULAR[label]} que se llame «{term}».', [i.name for i in items][:12])


def _dedupe(items):
    seen, out = set(), []
    for item in items:
        if item.pk not in seen:
            seen.add(item.pk)
            out.append(item)
    return out


def resolve_fields(organization, names=(), crops=()):
    fields = list(Field.objects.filter(organization=organization).order_by('name'))
    found = [_pick(name, fields, 'parcelas') for name in names]
    for crop in crops:
        key = norm(crop)
        matching = [f for f in fields if norm(f.crop) == key]
        if not matching:
            partial = [f for f in fields if key and key in norm(f.crop)]
            crops_found = sorted({f.crop for f in partial})
            if len(crops_found) > 1:
                raise ToolError(f'«{crop}» encaja con varios cultivos.', crops_found)
            matching = partial
        if not matching:
            raise ToolError(f'Ninguna parcela tiene el cultivo «{crop}».',
                            sorted({f.crop for f in fields if f.crop})[:12])
        found += matching
    return _dedupe(found)


def resolve_products(organization, names):
    products = list(Product.objects.filter(organization=organization).select_related('product_type'))
    return _dedupe([_pick(name, products, 'productos') for name in names])


def resolve_product_types(organization, names):
    """Tipos de producto: aquí sí vale más de uno por término («fungicida» → «Fungicidas»…)."""
    types = list(ProductType.objects.filter(organization=organization))
    found = []
    for name in names:
        key = norm(name).rstrip('s')
        matching = [t for t in types if key and key in norm(t.name)]
        if not matching:
            raise ToolError(f'No hay ningún tipo de producto «{name}».', [t.name for t in types][:12])
        found += matching
    return _dedupe(found)


def fields_label(fields):
    from assistant.tools.base import fmt_num
    return ' + '.join(f'{f.name} {fmt_num(f.area, 2)} ha' for f in fields)
