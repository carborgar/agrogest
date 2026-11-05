"""compra_pendiente: lo necesario para los tratamientos pendientes y atrasados (= «Preparar productos»)."""
from assistant.tools.base import arg_list, fmt_eur, fmt_num, make_table, register, result
from assistant.tools.resolve import resolve_fields
from farm.services import get_shopping_list


@register(
    'compra_pendiente',
    'Productos que hacen falta para los tratamientos pendientes y atrasados, con su coste y el reparto '
    'por casetilla. Son las mismas cifras que la pantalla «Preparar productos».',
    {
        'parcelas': {'type': 'array', 'items': {'type': 'string'}},
        'cultivo': {'type': 'array', 'items': {'type': 'string'}},
    },
)
def compra_pendiente(ctx, args):
    names, crops = arg_list(args, 'parcelas'), arg_list(args, 'cultivo')
    fields = resolve_fields(ctx.organization, names, crops) if (names or crops) else []
    data = get_shopping_list(ctx.user, field_ids=[f.pk for f in fields] or None, organization=ctx.organization)
    rows = []
    for item in data:
        split = '; '.join(
            f'{g["name"]}{" (sin casetilla asignada)" if g["is_manual"] else ""}: '
            f'{fmt_num(g["group_total"], 2)} {g["unit"]}'
            for g in item['distribution_groups'])
        rows.append([item['product_name'], f'{fmt_num(item["total_dose"], 2)} {item["unit"]}',
                     fmt_eur(item['total_price']), split])
    notes = ['No hay tratamientos pendientes.'] if not rows else ['AgroGest no lleva existencias: es lo necesario, no lo que falta.']
    table = make_table('Para lo pendiente', ['Producto', 'Cantidad', 'Coste', 'Reparto'], rows, notes,
                       numeric=(1, 2))
    understood = [', '.join(f.name for f in fields) if fields else 'Todas las parcelas', 'Pendientes y atrasados']
    return result(table, understood)
