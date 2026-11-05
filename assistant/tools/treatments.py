"""historial_tratamientos: qué se ha hecho, qué está pendiente, cuántas veces."""
from assistant.tools.base import (
    ToolError, arg_choice, arg_date, arg_int, arg_list, fmt_date, make_table, register, result,
)
from assistant.tools.resolve import resolve_fields, resolve_product_types, resolve_products
from django.db.models import F

from farm.models import Treatment

STATES = {'pendiente': 'pending', 'atrasado': 'delayed', 'aplicado': 'completed'}
STATE_LABELS = {v: k.capitalize() for k, v in STATES.items()}
MODES = ('lista', 'ultimo_por_parcela', 'contar')


@register(
    'historial_tratamientos',
    'Tratamientos de la organización con filtros. Valores dentro de un parámetro = «o»; '
    'entre parámetros = «y». modo: lista, ultimo_por_parcela (el último de cada parcela) o contar '
    '(nº por parcela). En ultimo_por_parcela y contar, sin estado, solo cuenta lo aplicado.',
    {
        'parcelas': {'type': 'array', 'items': {'type': 'string'}},
        'cultivo': {'type': 'array', 'items': {'type': 'string'}},
        'productos': {'type': 'array', 'items': {'type': 'string'}},
        'tipo_producto': {'type': 'array', 'items': {'type': 'string'}, 'description': 'Ej.: fungicida.'},
        'estado': {'type': 'array', 'items': {'type': 'string', 'enum': list(STATES)}},
        'desde': {'type': 'string', 'description': 'AAAA-MM-DD'},
        'hasta': {'type': 'string', 'description': 'AAAA-MM-DD'},
        'modo': {'type': 'string', 'enum': list(MODES)},
        'limite': {'type': 'integer', 'description': 'Solo en modo lista (máx. 20).'},
    },
)
def historial_tratamientos(ctx, args):
    org = ctx.organization
    states = [STATES[s] for s in arg_list(args, 'estado') if s in STATES]
    if arg_list(args, 'estado') and not states:
        raise ToolError(f'«estado» debe ser: {", ".join(STATES)}.')
    mode = arg_choice(args, 'modo', MODES, 'lista')
    if not states and mode != 'lista':
        states = ['completed']  # «la última vez» y «cuántas veces» hablan de lo hecho
    since, until = arg_date(args, 'desde'), arg_date(args, 'hasta')

    qs = Treatment.objects.filter(organization=org).select_related('field')
    understood = []
    field_names, crops = arg_list(args, 'parcelas'), arg_list(args, 'cultivo')
    fields = resolve_fields(org, field_names, crops) if (field_names or crops) else []
    if fields:
        qs = qs.filter(field__in=fields)
        understood.append(' o '.join(f.name for f in fields))
    products = resolve_products(org, arg_list(args, 'productos')) if arg_list(args, 'productos') else []
    if products:
        qs = qs.filter(treatmentproduct__product__in=products)
        understood.append(' o '.join(p.name for p in products))
    types = resolve_product_types(org, arg_list(args, 'tipo_producto')) if arg_list(args, 'tipo_producto') else []
    if types:
        qs = qs.filter(treatmentproduct__product__product_type__in=types)
        understood.append(' o '.join(t.name for t in types))
    if states:
        qs = qs.filter(status__in=states)
        understood.append(' o '.join(STATE_LABELS[s] for s in states))

    # Lo aplicado se fecha por cuándo se hizo de verdad; lo pendiente, por la fecha prevista.
    date_field = 'finish_date' if states == ['completed'] else 'date'
    if since:
        qs = qs.filter(**{f'{date_field}__gte': since})
    if until:
        qs = qs.filter(**{f'{date_field}__lte': until})
    if since or until:
        understood.append(f'{fmt_date(since) if since else "…"} – {fmt_date(until) if until else "hoy"}')
    order = F(date_field).desc(nulls_last=True)
    qs = qs.distinct().order_by(order, '-date').prefetch_related('treatmentproduct_set__product')

    if mode == 'contar':
        counts = {}
        for t in qs:
            counts[t.field.name] = counts.get(t.field.name, 0) + 1
        rows = [[name, n] for name, n in sorted(counts.items(), key=lambda x: -x[1])]
        table = make_table('Número de tratamientos', ['Parcela', 'Tratamientos'], rows,
                           [] if rows else ['Ninguno con esos filtros.'], numeric=(1,))
        return result(table, understood)

    if mode == 'ultimo_por_parcela':
        latest = {}
        for t in qs.iterator(chunk_size=200):
            latest.setdefault(t.field_id, t)
        treatments = list(latest.values())
        title = 'Último tratamiento por parcela'
    else:
        treatments = list(qs[:arg_int(args, 'limite', 10, 1, 20)])
        title = 'Tratamientos'

    wanted = {p.pk for p in products}
    rows = []
    for t in treatments:
        items = [tp for tp in t.treatmentproduct_set.all() if not wanted or tp.product_id in wanted]
        when = t.finish_date if t.status == 'completed' and t.finish_date else t.date
        rows.append([t.field.name, fmt_date(when), t.name, STATE_LABELS.get(t.status, t.status),
                     ', '.join(tp.product.name for tp in items) or '—'])
    if mode == 'ultimo_por_parcela' and fields:
        missing = [f.name for f in fields if f.pk not in {t.field_id for t in treatments}]
        for name in missing:
            rows.append([name, '—', 'Ninguno con esos filtros', '', ''])
    table = make_table(title, ['Parcela', 'Fecha', 'Tratamiento', 'Estado', 'Productos'], rows,
                       [] if rows else ['Ninguno con esos filtros.'])
    return result(table, understood)
