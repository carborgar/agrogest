"""calcular_dosis: cuánto producto hace falta, cuánto va a la máquina y cuánto cuesta."""
from decimal import Decimal

from assistant.tools.base import (
    ToolError, arg_choice, arg_decimal, arg_list, fmt_eur, fmt_num, make_table, register, result,
)
from assistant.tools.resolve import fields_label, norm, resolve_fields, resolve_products
from farm import dosing
from farm.models import Machine, Product, _round

# Convención de Carlos: «a la máquina» / «por máquina» = siempre 2.000 L,
# tenga la capacidad que tenga la máquina registrada (esa solo se usa para contar cargas).
MACHINE_LITRES = 2000

APPLICATION = {'pulverizacion': 'spraying', 'fertirrigacion': 'fertigation'}

# Unidades que acepta la herramienta (en español) → (tipo de dosis de Product, factor sobre el valor)
UNITS = {
    'l_por_1000l': ('l_per_1000l', Decimal(1)),
    'kg_por_1000l': ('kg_per_1000l', Decimal(1)),
    'l_por_ha': ('l_per_ha', Decimal(1)),
    'kg_por_ha': ('kg_per_ha', Decimal(1)),
    'porcentaje': ('pct', Decimal(1)),
    'l_por_maquina': ('l_per_1000l', Decimal(1000) / MACHINE_LITRES),
    'kg_por_maquina': ('kg_per_1000l', Decimal(1000) / MACHINE_LITRES),
}
DOSE_LABELS = dict(Product.ALL_DOSE_TYPE_CHOICES)


def _overrides(args, products):
    """dosis=[{producto, valor, unidad}] → {product.pk: (dosis, tipo, etiqueta)}."""
    raw = args.get('dosis') or []
    if not isinstance(raw, list):
        raise ToolError('«dosis» debe ser una lista de {producto, valor, unidad}.')
    out = {}
    for item in raw:
        if not isinstance(item, dict):
            raise ToolError('Cada dosis debe ser {producto, valor, unidad}.')
        key = norm(item.get('producto'))
        product = next((p for p in products if norm(p.name) == key), None) \
            or next((p for p in products if key and key in norm(p.name)), None)
        if product is None:
            raise ToolError(f'La dosis de «{item.get("producto")}» no corresponde a ningún producto pedido.')
        unit = item.get('unidad')
        if unit not in UNITS:
            raise ToolError(f'Unidad de dosis no válida: «{unit}». Usa una de: {", ".join(UNITS)}.')
        value = arg_decimal(item.get('valor'), 'valor')
        if value is None:
            raise ToolError(f'Falta el valor de la dosis de {product.name}.')
        dose_type, factor = UNITS[unit]
        label = f'{fmt_num(value, 3)} {"kg" if unit.startswith("kg") else "L"}/máquina' if unit.endswith('maquina') \
            else f'{fmt_num(value, 3)} {DOSE_LABELS[dose_type]}'
        out[product.pk] = (value * factor, dose_type, label, unit.endswith('maquina'))
    return out


def _loads_note(organization, area, water_per_ha, rows):
    machines = list(Machine.objects.filter(organization=organization))
    if len(machines) != 1 or machines[0].capacity <= 0:
        return 'Cargas: no las calculo porque hay varias máquinas registradas.' if machines else None
    machine = machines[0]
    loads = dosing.machine_loads(round(area * water_per_ha), machine.capacity)
    text = f'Cargas con {machine.name} ({fmt_num(machine.capacity, 0)} L, su capacidad real): {loads["full_loads"]} completas'
    if loads['partial_load']:
        text += f' + 1 de {fmt_num(loads["partial_water"], 0)} L'
    per_load = []
    for name, dose, dose_type, unit in rows:
        full = dosing.amount_for_water(dose, dose_type, machine.capacity, water_per_ha)
        if full is not None:
            part = ''
            if loads['partial_load']:
                partial = dosing.amount_for_water(dose, dose_type, loads['partial_water'], water_per_ha)
                part = f' (la última, {fmt_num(_round(partial, 3), 3)} {unit})'
            per_load.append(f'{name} {fmt_num(_round(full, 3), 3)} {unit} por carga{part}')
    return text + ('. ' + '; '.join(per_load) if per_load else '') + '.'


@register(
    'calcular_dosis',
    'Cantidad de producto para un tratamiento, cantidad por máquina (2.000 L), precio por unidad y coste '
    'por ha. Sin parcelas sirve de ficha rápida de un producto. Para comparar dosis o mojados, llámala '
    'varias veces a la vez.',
    {
        'productos': {'type': 'array', 'items': {'type': 'string'}, 'description': 'Nombres comerciales.'},
        'parcelas': {'type': 'array', 'items': {'type': 'string'}, 'description': 'Nombres de parcela.'},
        'cultivo': {'type': 'array', 'items': {'type': 'string'},
                    'description': 'Cultivo o variedad: todas las parcelas que lo tienen.'},
        'mojado_l_ha': {'type': 'number', 'description': 'Litros de caldo por ha.'},
        'tipo': {'type': 'string', 'enum': list(APPLICATION)},
        'dosis': {'type': 'array', 'description': 'Solo si el usuario da una dosis distinta de la normal.',
                  'items': {'type': 'object', 'properties': {
                      'producto': {'type': 'string'}, 'valor': {'type': 'number'},
                      'unidad': {'type': 'string', 'enum': list(UNITS)}},
                      'required': ['producto', 'valor', 'unidad']}},
    },
    required=('productos',),
)
def calcular_dosis(ctx, args):
    names = arg_list(args, 'productos')
    if not names:
        raise ToolError('Indica al menos un producto.')
    tipo = arg_choice(args, 'tipo', list(APPLICATION), 'pulverizacion')
    application = APPLICATION[tipo]
    spraying = application == 'spraying'
    water = arg_decimal(args.get('mojado_l_ha'), 'mojado_l_ha')
    products = resolve_products(ctx.organization, names)
    overrides = _overrides(args, products)

    field_names, crops = arg_list(args, 'parcelas'), arg_list(args, 'cultivo')
    fields = resolve_fields(ctx.organization, field_names, crops) if (field_names or crops) else []
    notes = []
    without_area = [f.name for f in fields if not f.area or f.area <= 0]
    if without_area:
        notes.append(f'Sin superficie registrada (no se cuentan): {", ".join(without_area)}.')
    fields = [f for f in fields if f.area and f.area > 0]
    area = sum((dosing._d(f.area) for f in fields), Decimal(0))

    computed, missing_dose, needs_water = [], [], []
    for product in products:
        if product.pk in overrides:
            dose, dose_type, label, per_machine = overrides[product.pk]
            if not spraying and (per_machine or dose_type not in dosing.PER_HA):
                raise ToolError('En fertirrigación la dosis va por ha (l_por_ha o kg_por_ha), no por máquina ni por caldo.')
        else:
            dose, dose_type = product.get_dose(application), product.get_dose_type(application)
            if not dose or not dose_type:
                missing_dose.append(product.name)
                continue
            label = f'{fmt_num(dose, 3)} {DOSE_LABELS.get(dose_type, dose_type)}'
        if dose_type not in dosing.PER_HA and not water:
            needs_water.append(product.name)
        computed.append((product, dosing._d(dose), dose_type, label))
    if needs_water:
        raise ToolError(f'Falta el mojado (L/ha): la dosis de {", ".join(needs_water)} depende del caldo. '
                        'Pregúntalo al usuario.')
    if missing_dose:
        notes.append(f'Sin dosis de {tipo} en AgroGest: {", ".join(missing_dose)}. Pide la dosis al usuario.')
    inactive = [p.name for p, *_ in computed if not p.is_active]
    if inactive:
        notes.append(f'Desactivado en AgroGest: {", ".join(inactive)}.')

    rows, load_rows = [], []
    for product, dose, dose_type, label in computed:
        unit = dosing.unit_for(dose_type)
        price = product.price if product.price and product.price > 0 else None
        per_ha = dosing.amount_per_ha(dose, dose_type, water)
        per_machine = dosing.amount_for_water(dose, dose_type, MACHINE_LITRES, water) if spraying else None
        machine_txt = f'{fmt_num(_round(per_machine, 3), 3)} {unit}' if per_machine is not None else '—'
        cost_ha = round(per_ha * price, 2) if price is not None else None
        if fields:
            total = _round(per_ha * area, 4)
            cost = round(total * price, 2) if price is not None else None
            rows.append([product.name, label, machine_txt, f'{fmt_num(total, 4)} {unit}', fmt_eur(cost)])
        else:
            price_txt = f'{fmt_eur(price)}/{unit}' if price is not None else 'sin precio'
            rows.append([product.name, label, machine_txt, price_txt, fmt_eur(cost_ha)])
        if price is None:
            notes.append(f'{product.name} no tiene precio en AgroGest.')
        load_rows.append((product.name, dose, dose_type, unit))

    understood = [', '.join(p.name for p, *_ in computed) or ', '.join(names)]
    if fields:
        understood.append(fields_label(fields))
    if water:
        understood.append(f'{fmt_num(water, 0)} L/ha')
    understood.append('Pulverización · máquina = 2.000 L' if spraying else 'Fertirrigación')

    if fields:
        columns = ['Producto', 'Dosis', 'Por máquina', 'Cantidad', 'Coste']
        title = f'Para {fmt_num(area, 2)} ha'
        if spraying and water:
            title += f' · {fmt_num(_round(area * water, 0), 0)} L de caldo'
            note = _loads_note(ctx.organization, area, water, load_rows)
            if note:
                notes.insert(0, note)
        notes.append('Es la cantidad necesaria: AgroGest no lleva existencias.')
    else:
        columns = ['Producto', 'Dosis', 'Por máquina', 'Precio', 'Coste/ha']
        title = 'Ficha de producto' + (f' · {fmt_num(water, 0)} L/ha' if water else '')
    table = make_table(title, columns, rows, notes, numeric=(2, 3, 4))
    return result(table, understood)
