"""
Test diferencial: casos aleatorios (con semilla fija) calculados con el MODELO REAL de Django y guardados en
farm/tests/fixtures/treatment_calc_random.json; static/js/tests/treatment-calc-random.test.js comprueba que
treatment-calc.js da EXACTAMENTE los mismos valores (sin tolerancia).

Este test regenera los casos y falla si el fichero ya no coincide con lo que calcula hoy el backend
(es decir, si cambia una fórmula o un redondeo). Para actualizar el fichero:

    AGRO_REGEN_FIXTURES=1 DATABASE_URL=sqlite:////tmp/x.sqlite3 python3 -m pytest farm/tests/test_treatment_calc_differential.py

y después `npm run test:js` dirá si el JS sigue coincidiendo.

Los valores salen de rejillas decimales pequeñas a propósito: así hay muchísimos empates exactos a 4 y a 2
decimales (donde importa el modo de redondeo) y áreas «feas» como 1,9 o 6,1 (donde Decimal(float) fallaba).
No necesita base de datos: los objetos no se guardan.
"""
import json
import os
import random
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path

from farm.models import Field, Machine, Product, Treatment, TreatmentProduct

PATH = Path(__file__).parent / 'fixtures' / 'treatment_calc_random.json'
N_CASES = 700
SPRAY_TYPES = ['kg_per_1000l', 'l_per_1000l', 'kg_per_ha', 'l_per_ha', 'pct']
CAPACITIES = [None, 400, 600, 800, 1000, 1500, 2000, 2500, 3000]


def _decimal_text(rng, lo, hi, places):
    value = Decimal(rng.randint(int(lo * 10 ** places), int(hi * 10 ** places))) / Decimal(10 ** places)
    return str(value.quantize(Decimal(1).scaleb(-places)))


def generate(n=N_CASES, seed=20261027):
    rng = random.Random(seed)
    cases = []
    while len(cases) < n:
        spraying = rng.random() < 0.85
        dose_type = rng.choice(SPRAY_TYPES) if spraying else rng.choice(['kg_per_ha', 'l_per_ha'])
        area = round(rng.uniform(0.1, 30), rng.choice([1, 1, 2, 2, 3]))
        applied = round(area * rng.uniform(0.2, 0.9), rng.choice([1, 2])) if rng.random() < 0.25 else None
        if applied is not None and not 0 < applied < area:
            applied = None
        water = rng.choice([0] if not spraying else [200, 250, 300, 400, 500, 600, 800, 1000, 1200, 1500, 2000, rng.randint(150, 2500)])
        real_water = rng.choice([300, 700, 900, 1100, 1300]) if spraying and rng.random() < 0.15 else None
        capacity = rng.choice(CAPACITIES) if spraying else None
        pct = dose_type == 'pct'
        dose = _decimal_text(rng, 0.05 if pct else 0.01, 5 if pct else 50, rng.choice([1, 2, 3]))
        override = _decimal_text(rng, 0.1, 400, rng.choice([1, 2, 4])) if rng.random() < 0.25 else None
        if Decimal(dose) <= 0 or (override is not None and Decimal(override) <= 0):
            continue
        case = {
            'type': 'spraying' if spraying else 'fertigation', 'dose_type': dose_type, 'dose': dose,
            'area': area, 'applied_area': applied, 'water': water, 'real_water': real_water,
            'capacity': capacity, 'price': _decimal_text(rng, 0, 60, 2), 'total_override': override,
        }
        case['out'] = compute(case)
        cases.append(case)
    return cases


def compute(case):
    """Lo que guarda y enseña el backend real para este caso (cadenas decimales exactas)."""
    field = Field(area=case['area'])
    machine = Machine(capacity=case['capacity']) if case['capacity'] else None
    treatment = Treatment(field=field, machine=machine, type=case['type'], water_per_ha=case['water'],
                          real_water_per_ha=case['real_water'], applied_area=case['applied_area'])
    tp = TreatmentProduct(treatment=treatment, product=Product(price=Decimal(case['price'])),
                          dose=Decimal(case['dose']), dose_type=case['dose_type'], unit_price=Decimal(0),
                          total_dose=Decimal(case['total_override'] or 0))
    if case['total_override']:
        # Como TreatmentProduct.save con total a mano: el total se guarda a 2 decimales y la dosis se deriva de él
        tp.total_dose = tp.total_dose.quantize(Decimal('0.01'), rounding=ROUND_HALF_EVEN)
        tp.calculate_dose_from_total()
    else:
        tp.calculate_total_dose()
    tp.calculate_prices()
    out = {'total_dose': str(tp.total_dose), 'dose': str(tp.dose), 'total_price': str(tp.total_price),
           'price_per_ha': str(tp.price_per_ha)}
    if case['type'] == 'spraying':
        per_load = tp.get_dose_per_load()
        loads = treatment.calculate_machine_loads()
        out['dose_per_load'] = None if per_load is None else str(per_load)
        out['loads'] = loads
        out['partial_product'] = str(treatment.calculate_product_for_partial_load(tp))
    return out


def _dump(cases):
    return '[\n' + ',\n'.join(json.dumps(c, ensure_ascii=False, separators=(',', ':')) for c in cases) + '\n]\n'


def test_random_cases_file_matches_what_the_backend_computes():
    cases = generate()
    text = _dump(cases)
    if os.environ.get('AGRO_REGEN_FIXTURES') == '1':
        PATH.write_text(text, encoding='utf-8')
    assert PATH.read_text(encoding='utf-8') == text, (
        'treatment_calc_random.json no coincide con el backend: regenera con AGRO_REGEN_FIXTURES=1 y '
        'revisa con `npm run test:js` que treatment-calc.js sigue dando lo mismo')


def test_random_cases_cover_ties_and_both_types():
    cases = generate()
    assert sum(c['type'] == 'spraying' for c in cases) > 450
    assert sum(c['total_override'] is not None for c in cases) > 100
    assert sum(c['applied_area'] is not None for c in cases) > 80
    assert sum(c['out'].get('loads', {}) is not None and c['out'].get('loads', {}).get('partial_load', False) for c in cases) > 100
