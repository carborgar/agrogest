"""costes: gasto, ingreso, margen y producción por parcela o por tipo."""
from datetime import date
from decimal import Decimal

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q, Sum

from assistant.tools.base import (
    ToolError, applied_in, arg_choice, arg_date, arg_list, fmt_date, fmt_eur, fmt_num, make_table, register,
    result,
)
from assistant.tools.resolve import resolve_fields
from farm.models import Expense, Field, Harvest, TreatmentProduct

GROUPS = ('parcela', 'tipo_producto', 'tipo_gasto')
ZERO = Decimal(0)


def _sum(qs, expr):
    return qs.aggregate(v=Sum(expr))['v'] or ZERO


@register(
    'costes',
    'Gasto (tratamientos aplicados + otros gastos), y con incluir_ingresos: ingreso de cosechas, margen y '
    'kg/ha. Por defecto, el año en curso. Para comparar años, llámala una vez por año.',
    {
        'parcelas': {'type': 'array', 'items': {'type': 'string'}},
        'cultivo': {'type': 'array', 'items': {'type': 'string'}},
        'desde': {'type': 'string', 'description': 'AAAA-MM-DD'},
        'hasta': {'type': 'string', 'description': 'AAAA-MM-DD'},
        'agrupar_por': {'type': 'string', 'enum': list(GROUPS)},
        'incluir_ingresos': {'type': 'boolean'},
    },
)
def costes(ctx, args):
    org = ctx.organization
    since = arg_date(args, 'desde', date(ctx.today.year, 1, 1))
    until = arg_date(args, 'hasta', ctx.today)
    if since > until:
        raise ToolError('«desde» es posterior a «hasta».')
    group = arg_choice(args, 'agrupar_por', GROUPS, 'parcela')
    income = bool(args.get('incluir_ingresos'))
    names, crops = arg_list(args, 'parcelas'), arg_list(args, 'cultivo')
    fields = resolve_fields(org, names, crops) if (names or crops) else \
        list(Field.objects.filter(organization=org).order_by('name'))

    # Solo lo aplicado cuenta como gasto; lo pendiente se da aparte.
    tps = TreatmentProduct.objects.filter(organization=org, treatment__field__in=fields)
    applied = tps.filter(applied_in(since, until))
    planned = tps.filter(treatment__status__in=('pending', 'delayed'), treatment__date__range=(since, until))
    expenses = Expense.objects.filter(organization=org, field__in=fields, payment_date__range=(since, until))
    harvests = Harvest.objects.filter(organization=org, field__in=fields, date__range=(since, until))

    understood = [', '.join(f.name for f in fields) if (names or crops) else 'Todas las parcelas',
                  f'{fmt_date(since)} – {fmt_date(until)}']
    notes = []
    planned_total = _sum(planned, 'total_price')
    if planned_total:
        notes.append(f'Solo cuento lo aplicado. Hay {fmt_eur(planned_total)} más en tratamientos pendientes.')

    if group == 'tipo_producto':
        rows = [[r['product__product_type__name'] or 'Sin tipo', fmt_eur(r['total'])]
                for r in applied.values('product__product_type__name').annotate(total=Sum('total_price'))
                .order_by('-total')]
        table = make_table('Gasto en productos por tipo', ['Tipo de producto', 'Gasto'], rows, notes, numeric=(1,))
        return result(table, understood + ['Por tipo de producto'])

    if group == 'tipo_gasto':
        rows = [['Productos (tratamientos)', fmt_eur(_sum(applied, 'total_price'))]]
        rows += [[r['expense_type__name'], fmt_eur(r['total'])]
                 for r in expenses.values('expense_type__name').annotate(total=Sum('amount')).order_by('-total')]
        table = make_table('Gasto por tipo', ['Tipo', 'Gasto'], rows, notes, numeric=(1,))
        return result(table, understood + ['Por tipo de gasto'])

    treat_by = {r['treatment__field']: r['t'] for r in
                applied.values('treatment__field').annotate(t=Sum('total_price'))}
    exp_by = {r['field']: r['t'] for r in expenses.values('field').annotate(t=Sum('amount'))}
    revenue = ExpressionWrapper(F('sale_price_per_kg') * F('amount'),
                                output_field=DecimalField(max_digits=14, decimal_places=2))
    harv_by = {r['field']: r for r in harvests.values('field').annotate(
        kg=Sum('amount'), income=Sum(revenue, filter=Q(sale_price_per_kg__isnull=False)),
        unpriced=Count('id', filter=Q(sale_price_per_kg__isnull=True)))}

    rows = []
    for f in fields:
        spent = (treat_by.get(f.pk) or ZERO) + (exp_by.get(f.pk) or ZERO)
        area = Decimal(str(f.area)) if f.area else None
        if not income:
            rows.append((spent / area if area else ZERO,
                         [f.name, fmt_eur(treat_by.get(f.pk) or ZERO), fmt_eur(exp_by.get(f.pk) or ZERO),
                          fmt_eur(spent), fmt_eur(spent / area) if area else '—']))
            continue
        h = harv_by.get(f.pk) or {}
        earned = h.get('income') or ZERO
        if h.get('unpriced'):
            notes.append(f'{f.name}: {h["unpriced"]} cosecha(s) sin precio de venta; no entran en el ingreso.')
        margin = earned - spent
        # kg/ha = kg de todas las cosechas / superficie de la parcela (una sola vez)
        kg_ha = Decimal(h['kg']) / area if h.get('kg') and area else None
        rows.append((margin / area if area else ZERO,
                     [f.name, fmt_eur(spent), fmt_eur(earned) if earned else 'sin ingresos', fmt_eur(margin),
                      fmt_eur(margin / area) if area else '—', fmt_num(kg_ha, 0) if kg_ha else '—']))
    rows.sort(key=lambda r: -r[0])
    if income:
        table = make_table('Rentabilidad por parcela',
                           ['Parcela', 'Gasto', 'Ingreso', 'Margen', 'Margen/ha', 'kg/ha'],
                           [r[1] for r in rows], notes, numeric=(1, 2, 3, 4, 5))
    else:
        table = make_table('Gasto por parcela', ['Parcela', 'Tratamientos', 'Otros gastos', 'Total', '€/ha'],
                           [r[1] for r in rows], notes, numeric=(1, 2, 3, 4))
    return result(table, understood)
