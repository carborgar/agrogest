"""Herramientas del asistente: cifras, resolución de nombres y aislamiento entre organizaciones."""
import json
from datetime import date
from decimal import Decimal

import pytest

from assistant.tools import available_tools, run_tool
from farm.models import Expense, ExpenseType, Harvest
from farm.tests.factories import (
    FieldFactory, MachineFactory, OrganizationFactory, ProductFactory, ProductTypeFactory, TreatmentFactory,
    TreatmentProductFactory,
)

pytestmark = pytest.mark.django_db


def call(ctx, name, **args):
    tools = {t.name: t for t in available_tools()}
    return run_tool(tools, name, json.dumps(args), ctx)


@pytest.fixture
def farm(org):
    """Vegueta 2,1 ha + Injertos 1,4 ha (leanri), Cartuja 3 ha; Aliette 2,5 kg/1000 L a 28 €/kg."""
    fungicida = ProductTypeFactory(organization=org, name='Fungicidas')
    return {
        'vegueta': FieldFactory(organization=org, name='Vegueta', area=2.1, crop='Mandarina Leanri'),
        'injertos': FieldFactory(organization=org, name='Injertos', area=1.4, crop='Mandarina Leanri'),
        'cartuja': FieldFactory(organization=org, name='Cartuja', area=3.0, crop='Naranja'),
        'aliette': ProductFactory(organization=org, name='Aliette', product_type=fungicida, price=Decimal('28'),
                                  spraying_dose=Decimal('2.5'), spraying_dose_type='kg_per_1000l',
                                  fertigation_dose=None, fertigation_dose_type=None),
        'cabrio': ProductFactory(organization=org, name='Cabrio Top', product_type=fungicida,
                                 price=Decimal('40'), spraying_dose=Decimal('2'), spraying_dose_type='kg_per_ha',
                                 fertigation_dose=None, fertigation_dose_type=None),
    }


class TestCalcularDosis:
    def test_purchase_for_fields(self, ctx, farm):
        res = call(ctx, 'calcular_dosis', productos=['aliette'], parcelas=['vegueta', 'injertos'],
                   mojado_l_ha=1500)
        row = res.table['rows'][0]
        assert row[0] == 'Aliette'
        assert row[2] == '5 kg'           # por máquina de 2.000 L
        assert row[3] == '13,125 kg'      # 2,5 × 1500 × 3,5 / 1000
        assert row[4] == '367,50 €'
        assert 'Vegueta 2,1 ha + Injertos 1,4 ha' in res.understood
        assert '5.250 L de caldo' in res.table['title']

    def test_per_machine_dose(self, ctx, farm):
        res = call(ctx, 'calcular_dosis', productos=['aliette'], parcelas=['vegueta', 'injertos'],
                   mojado_l_ha=1500, dosis=[{'producto': 'aliette', 'valor': 2, 'unidad': 'kg_por_maquina'}])
        row = res.table['rows'][0]
        assert row[1] == '2 kg/máquina'
        assert row[2] == '2 kg'
        assert row[3] == '5,25 kg'
        assert row[4] == '147,00 €'

    def test_by_crop_takes_every_field(self, ctx, farm):
        res = call(ctx, 'calcular_dosis', productos=['aliette'], cultivo=['leanri'], mojado_l_ha=1000)
        assert res.table['title'].startswith('Para 3,5 ha')

    def test_product_sheet_without_fields(self, ctx, farm):
        res = call(ctx, 'calcular_dosis', productos=['cabrio'], mojado_l_ha=1500)
        row = res.table['rows'][0]
        assert row[2] == '2,667 kg'       # 2 kg/ha × 2.000 / 1.500
        assert row[3] == '40,00 €/kg'     # unidad real, aunque pregunten por el litro
        assert row[4] == '80,00 €'        # = Product.cost_per_ha
        assert farm['cabrio'].cost_per_ha('spraying', 1500) == Decimal('80.00')

    def test_missing_water_asks(self, ctx, farm):
        res = call(ctx, 'calcular_dosis', productos=['aliette'], parcelas=['vegueta'])
        assert res.text.startswith('ERROR: Falta el mojado')

    def test_per_ha_dose_needs_no_water_for_total(self, ctx, farm):
        res = call(ctx, 'calcular_dosis', productos=['cabrio'], parcelas=['cartuja'])
        assert res.table['rows'][0][3] == '6 kg'

    def test_loads_with_single_machine(self, ctx, farm, org):
        MachineFactory(organization=org, name='Atomizador', capacity=2000)
        res = call(ctx, 'calcular_dosis', productos=['aliette'], parcelas=['vegueta', 'injertos'],
                   mojado_l_ha=1500)
        assert res.table['notes'][0].startswith('Cargas con Atomizador (2.000 L, su capacidad real): 2 completas + 1 de 1.250 L')

    def test_fertigation_rejects_per_machine(self, ctx, farm):
        res = call(ctx, 'calcular_dosis', productos=['aliette'], tipo='fertirrigacion',
                   dosis=[{'producto': 'aliette', 'valor': 2, 'unidad': 'kg_por_maquina'}])
        assert 'fertirrigación' in res.text

    def test_ambiguous_name_returns_candidates(self, ctx, farm, org):
        FieldFactory(organization=org, name='Vegueta baja', area=1)
        res = call(ctx, 'calcular_dosis', productos=['aliette'], parcelas=['vegu'], mojado_l_ha=1000)
        assert res.candidates == ['Vegueta', 'Vegueta baja']

    def test_exact_name_wins_over_partial(self, ctx, farm, org):
        FieldFactory(organization=org, name='Vegueta baja', area=1)
        res = call(ctx, 'calcular_dosis', productos=['aliette'], parcelas=['VEGUETA'], mojado_l_ha=1000)
        assert res.table['title'].startswith('Para 2,1 ha')

    def test_other_organization_is_invisible(self, ctx, farm):
        other = OrganizationFactory(name='Ajena')
        ProductFactory(organization=other, name='Secreto')
        res = call(ctx, 'calcular_dosis', productos=['secreto'], mojado_l_ha=1000)
        assert res.text.startswith('ERROR') and 'Secreto' not in res.text


class TestHistorial:
    def test_last_per_field_with_or(self, ctx, farm, org):
        old = TreatmentFactory(field=farm['vegueta'], organization=org, date=date(2026, 9, 1),
                               finish_date=date(2026, 9, 1), name='Viejo')
        new = TreatmentFactory(field=farm['vegueta'], organization=org, date=date(2026, 10, 28),
                               finish_date=date(2026, 10, 28), name='Mildiu')
        for t in (old, new):
            TreatmentProductFactory(treatment=t, product=farm['aliette'], organization=org)
        res = call(ctx, 'historial_tratamientos', parcelas=['vegueta', 'cartuja'], tipo_producto=['fungicida'],
                   estado=['aplicado'], modo='ultimo_por_parcela')
        rows = res.table['rows']
        assert rows[0][:3] == ['Vegueta', '28 oct 2026', 'Mildiu']
        assert rows[1][0] == 'Cartuja' and rows[1][2] == 'Ninguno con esos filtros'

    def test_count(self, ctx, farm, org):
        for d in (date(2026, 3, 1), date(2026, 5, 1)):
            t = TreatmentFactory(field=farm['cartuja'], organization=org, date=d, finish_date=d)
            TreatmentProductFactory(treatment=t, product=farm['cabrio'], organization=org)
        res = call(ctx, 'historial_tratamientos', productos=['cabrio'], modo='contar')
        assert res.table['rows'] == [['Cartuja', '2']]


class TestCostes:
    def test_profitability_counts_only_applied(self, ctx, farm, org):
        done = TreatmentFactory(field=farm['vegueta'], organization=org, date=date(2026, 6, 1),
                                finish_date=date(2026, 6, 1))
        TreatmentProductFactory(treatment=done, product=farm['aliette'], organization=org)
        pending = TreatmentFactory(field=farm['vegueta'], organization=org, date=date(2026, 10, 20))
        TreatmentProductFactory(treatment=pending, product=farm['aliette'], organization=org)
        Expense.objects.create(organization=org, field=farm['vegueta'], amount=Decimal('100'),
                               expense_type=ExpenseType.objects.create(organization=org, name='Poda'),
                               payment_date=date(2026, 2, 1), description='poda')
        Harvest.objects.create(organization=org, field=farm['vegueta'], date=date(2026, 10, 1), amount=21000,
                               sale_price_per_kg=Decimal('0.50'))
        Harvest.objects.create(organization=org, field=farm['cartuja'], date=date(2026, 10, 1), amount=3000)
        done.refresh_from_db()
        spent = done.treatmentproduct_set.first().total_price + Decimal('100')

        res = call(ctx, 'costes', agrupar_por='parcela', incluir_ingresos=True)
        vegueta = next(r for r in res.table['rows'] if r[0] == 'Vegueta')
        assert vegueta[2] == '10.500,00 €'
        assert vegueta[1] == f'{spent:.2f} €'.replace('.', ',')
        assert vegueta[5] == '10.000'  # 21.000 kg / 2,1 ha
        assert any('Cartuja: 1 cosecha(s) sin precio' in n for n in res.table['notes'])
        assert any('pendientes' in n for n in res.table['notes'])


class TestOtras:
    def test_consumo_producto(self, ctx, farm, org):
        t = TreatmentFactory(field=farm['cartuja'], organization=org, date=date(2026, 4, 1),
                             finish_date=date(2026, 4, 1))
        TreatmentProductFactory(treatment=t, product=farm['cabrio'], organization=org)
        res = call(ctx, 'consumo_producto', nombre='cabrio')
        assert res.table['rows'][0][:2] == ['Cartuja', '1']
        assert 'Precio actual: 40,00 €/kg' in res.table['notes']

    def test_compra_pendiente(self, ctx, farm, org):
        t = TreatmentFactory(field=farm['vegueta'], organization=org, date=date(2030, 1, 1))
        TreatmentProductFactory(treatment=t, product=farm['aliette'], organization=org)
        res = call(ctx, 'compra_pendiente')
        assert res.table['rows'][0][0] == 'Aliette'
        assert 'sin casetilla asignada' in res.table['rows'][0][3]

    def test_unknown_tool_and_bad_json(self, ctx):
        assert run_tool({}, 'nada', '{}', ctx).text.startswith('ERROR')
        tools = {t.name: t for t in available_tools()}
        assert run_tool(tools, 'costes', '{no json', ctx).text.startswith('ERROR')

    def test_weather_tool_hidden_without_flag(self):
        assert 'ventana_tratamiento' not in {t.name for t in available_tools()}


class TestRevision:
    def test_completed_without_finish_date_uses_planned_date(self, ctx, farm, org):
        t = TreatmentFactory(field=farm['cartuja'], organization=org, date=date(2026, 4, 1),
                             finish_date=date(2026, 4, 1))
        TreatmentProductFactory(treatment=t, product=farm['cabrio'], organization=org)
        from farm.models import Treatment
        Treatment.objects.filter(pk=t.pk).update(finish_date=None)  # dato antiguo: completado sin fecha de fin
        res = call(ctx, 'consumo_producto', nombre='cabrio')
        assert res.table['rows'][0][:2] == ['Cartuja', '1']

    def test_nan_and_text_arguments(self, ctx, farm):
        res = call(ctx, 'calcular_dosis', productos=['aliette'], mojado_l_ha='NaN')
        assert 'número mayor que 0' in res.text
        res = call(ctx, 'historial_tratamientos', limite='muchos')
        assert not res.text.startswith('ERROR')

    def test_count_defaults_to_applied(self, ctx, farm, org):
        TreatmentFactory(field=farm['cartuja'], organization=org, date=date(2030, 1, 1))
        res = call(ctx, 'historial_tratamientos', modo='contar')
        assert res.table['rows'] == []

    def test_dates_reversed(self, ctx, farm):
        res = call(ctx, 'costes', desde='2026-10-01', hasta='2026-01-01')
        assert 'posterior' in res.text
