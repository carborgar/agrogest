"""farm/dosing.py: las fórmulas que comparten los modelos y el asistente."""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from farm import dosing
from farm.services import get_shopping_list
from farm.tests.factories import (
    FieldFactory, OrganizationFactory, ProductFactory, TreatmentFactory, TreatmentProductFactory,
)


class TestAmountPerHa:
    def test_per_1000l_uses_water(self):
        assert dosing.amount_per_ha(Decimal('2.5'), 'kg_per_1000l', 1500) == Decimal('3.75')

    def test_per_ha_ignores_water(self):
        assert dosing.amount_per_ha(Decimal('3'), 'l_per_ha', None) == Decimal('3')

    def test_pct(self):
        assert dosing.amount_per_ha(Decimal('0.5'), 'pct', 1000) == Decimal('5')

    def test_needs_water_returns_none(self):
        assert dosing.amount_per_ha(Decimal('1'), 'l_per_1000l', None) is None

    def test_unknown_type(self):
        assert dosing.amount_per_ha(Decimal('1'), 'raro', 1000) is None


class TestAmountForWater:
    def test_machine_of_2000_litres(self):
        assert dosing.amount_for_water(Decimal('2.5'), 'kg_per_1000l', 2000) == Decimal('5')

    def test_per_ha_split_by_water(self):
        # 3 L/ha mojando 1500 L/ha → 2.000 L cubren 1,333 ha
        value = dosing.amount_for_water(Decimal('3'), 'l_per_ha', 2000, 1500)
        assert round(value, 4) == Decimal('4.0000')

    def test_per_ha_without_water(self):
        assert dosing.amount_for_water(Decimal('3'), 'l_per_ha', 2000, None) is None

    def test_legacy_2000l(self):
        assert dosing.amount_for_water(Decimal('2'), 'l_per_2000l', 1000) == Decimal('1')


def test_machine_loads():
    assert dosing.machine_loads(5250, 2000) == {
        'total_water': 5250, 'full_loads': 2, 'partial_load': True, 'partial_water': 1250}
    assert dosing.machine_loads(4030, 2000)['partial_load'] is False  # 30 L no cuentan


def test_unit_for():
    assert dosing.unit_for('kg_per_ha') == 'kg'
    assert dosing.unit_for('pct') == 'L'
    assert dosing.unit_for(None) == 'L'


@pytest.mark.django_db
def test_shopping_list_organization_overrides_superuser():
    """Un superusuario lo ve todo; con `organization` solo se ve esa (lo usa el asistente)."""
    mine, other = OrganizationFactory(name='Mía'), OrganizationFactory(name='Ajena')
    for org in (mine, other):
        field = FieldFactory(organization=org)
        treatment = TreatmentFactory(field=field, organization=org, date=date.today() + timedelta(days=3))
        TreatmentProductFactory(treatment=treatment, product=ProductFactory(organization=org), organization=org)
    admin = get_user_model().objects.create_superuser('admin', 'a@example.com', 'x')

    assert len(get_shopping_list(admin)) == 2
    only_mine = get_shopping_list(admin, organization=mine)
    assert len(only_mine) == 1
    assert only_mine[0]['product'].organization == mine
