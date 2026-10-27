"""
Casos «golden» de cálculo de tratamientos.

Comparten fichero con el módulo JS (static/js/tests/treatment-calc.test.js):
farm/tests/fixtures/treatment_calc_cases.json. Los valores esperados están
calculados a mano (plan, sección 2.1). Si cambia una fórmula en Python o en JS,
estos tests fallan.
"""
import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from farm.forms import TreatmentProductForm
from farm.models import Treatment, TreatmentProduct
from farm.tests.factories import (
    FieldFactory, MachineFactory, OrganizationFactory, ProductFactory, ProductTypeFactory,
)

CASES_PATH = Path(__file__).parent / 'fixtures' / 'treatment_calc_cases.json'
DATA = json.loads(CASES_PATH.read_text(encoding='utf-8'))

# Casos que hoy fallan por un error conocido del plan; se quita de aquí al arreglarlo.
KNOWN_FAILING = {}


def _params():
    params = []
    for case in DATA['cases']:
        marks = []
        if case['id'] in KNOWN_FAILING:
            marks.append(pytest.mark.xfail(strict=True, reason=KNOWN_FAILING[case['id']]))
        params.append(pytest.param(case, id=case['id'], marks=marks))
    return params


def build_case(inp):
    """Crea parcela, máquina, producto, tratamiento y línea a partir del input del caso."""
    org = OrganizationFactory()
    field = FieldFactory(organization=org, area=inp['field_area'])
    machine = (
        MachineFactory(organization=org, capacity=inp['capacity']) if inp['capacity'] else None
    )
    product_type = ProductTypeFactory(organization=org)
    prod_kwargs = dict(
        organization=org, product_type=product_type, price=Decimal(inp['price']),
        spraying_dose=None, spraying_dose_type=None, fertigation_dose=None, fertigation_dose_type=None,
    )
    if inp['type'] == 'spraying':
        prod_kwargs.update(spraying_dose=Decimal(inp['dose']), spraying_dose_type=inp['dose_type'])
    else:
        prod_kwargs.update(fertigation_dose=Decimal(inp['dose']), fertigation_dose_type=inp['dose_type'])
    product = ProductFactory(**prod_kwargs)

    today = date.today()
    treatment = Treatment.objects.create(
        organization=org, field=field, machine=machine, name='Caso', type=inp['type'],
        date=today - timedelta(days=3),
        finish_date=today if inp['finish_date'] else None,
        water_per_ha=inp['water_per_ha'], real_water_per_ha=inp['real_water_per_ha'],
        applied_area=inp['applied_area'],
    )
    override = inp['total_override']
    tp = TreatmentProduct.objects.create(
        organization=org, treatment=treatment, product=product,
        dose=Decimal(inp['dose']),
        total_dose=Decimal(override) if override else Decimal('0'),
        total_overridden=bool(override),
    )
    tp.refresh_from_db()
    treatment.refresh_from_db()
    return treatment, tp


@pytest.mark.django_db
@pytest.mark.parametrize('case', _params())
def test_golden_case(case):
    treatment, tp = build_case(case['input'])
    exp = case['expected']

    assert float(tp.total_dose) == pytest.approx(exp['total_dose'], abs=1e-4)
    assert float(tp.dose) == pytest.approx(exp['dose'], abs=1e-4)
    assert tp.total_dose_unit == exp['total_dose_unit']
    assert float(tp.total_price) == pytest.approx(exp['total_price'], abs=1e-2)
    assert float(tp.price_per_ha) == pytest.approx(exp['price_per_ha'], abs=1e-2)

    per_load = tp.get_dose_per_load()
    if exp['dose_per_load'] is None:
        assert per_load is None
    else:
        assert float(per_load) == pytest.approx(exp['dose_per_load'], abs=1e-4)

    loads = treatment.calculate_machine_loads()
    if exp['loads'] is None:
        assert loads is None
    else:
        assert loads == exp['loads']

    assert treatment.calculate_product_for_partial_load(tp) == pytest.approx(exp['partial_product'], abs=1e-4)


@pytest.mark.parametrize('item', DATA['rounding'], ids=lambda i: i['id'])
def test_dose_rounding_is_round_up_three_decimals(item):
    """Caso J: clean_dose redondea hacia arriba a 3 decimales."""
    form = TreatmentProductForm()
    form.cleaned_data = {'dose': Decimal(item['input'])}
    assert form.clean_dose() == Decimal(item['expected'])
