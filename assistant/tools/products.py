"""consumo_producto: cuánto se ha gastado de un producto y cómo ha ido su precio."""
from datetime import date
from decimal import Decimal

from django.db.models import Count, Sum

from assistant.tools.base import (
    ToolError, applied_in, arg_date, fmt_date, fmt_eur, fmt_num, make_table, register, result,
)
from assistant.tools.resolve import resolve_products
from farm import dosing
from farm.models import ProductPriceHistory, TreatmentProduct


@register(
    'consumo_producto',
    'Consumo de un producto en tratamientos aplicados (por parcela), su precio actual y los últimos '
    'cambios de precio. Por defecto, el año en curso.',
    {
        'nombre': {'type': 'string', 'description': 'Nombre comercial.'},
        'desde': {'type': 'string', 'description': 'AAAA-MM-DD'},
        'hasta': {'type': 'string', 'description': 'AAAA-MM-DD'},
    },
    required=('nombre',),
)
def consumo_producto(ctx, args):
    name = str(args.get('nombre') or '').strip()
    if not name:
        raise ToolError('Indica el producto.')
    product = resolve_products(ctx.organization, [name])[0]
    since = arg_date(args, 'desde', date(ctx.today.year, 1, 1))
    until = arg_date(args, 'hasta', ctx.today)
    rows_qs = (TreatmentProduct.objects
               .filter(applied_in(since, until), organization=ctx.organization, product=product)
               .values('treatment__field__name', 'total_dose_unit')
               .annotate(qty=Sum('total_dose'), cost=Sum('total_price'), n=Count('treatment', distinct=True))
               .order_by('treatment__field__name'))
    rows = [[r['treatment__field__name'], r['n'], f'{fmt_num(r["qty"], 3)} {r["total_dose_unit"]}',
             fmt_eur(r['cost'])] for r in rows_qs]

    unit = dosing.unit_for(product.spraying_dose_type or product.fertigation_dose_type)
    notes = [f'Precio actual: {fmt_eur(product.price)}/{unit}' if product.price else 'Sin precio en AgroGest.']
    history = list(ProductPriceHistory.objects.filter(product=product).order_by('-effective_date')[:4])
    if history:
        notes.append('Cambios de precio: ' + '; '.join(
            f'{fmt_date(h.effective_date)} {fmt_eur(h.price)}' for h in history) + '.')
    if not rows:
        notes.insert(0, 'No se ha aplicado en ese periodo.')
    table = make_table(f'{product.name}: consumo', ['Parcela', 'Tratamientos', 'Cantidad', 'Coste'],
                       rows, notes, numeric=(1, 2, 3))
    return result(table, [product.name, f'{fmt_date(since)} – {fmt_date(until)}', 'Solo aplicados'])
