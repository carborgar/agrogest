import pytest

from farm.tests.mothers import *


@pytest.mark.django_db
class TestFieldCostCalculations:
    """
    Tests para verificar los cálculos de costos en Field
    """

    def test_field_calculates_total_treatment_costs_correctly(self):
        # Given: Un campo de 5 hectáreas con tratamientos con costos conocidos
        field = FieldMothers.small_olive_field()  # 5ha

        treatment1 = TreatmentFactory(
            field=field,
            date=date.today() - timedelta(days=30),
            organization=field.organization,
            water_per_ha=500  # 500L/ha * 5ha = 2500L total
        )
        treatment2 = TreatmentFactory(
            field=field,
            date=date.today() - timedelta(days=60),
            organization=field.organization,
            water_per_ha=400  # 400L/ha * 5ha = 2000L total
        )

        # Producto 1: total_dose=5L * 20€ = 100€
        TreatmentProductFactory(
            treatment=treatment1,
            product=ProductFactory(organization=field.organization, price=Decimal('20.00')),
            dose=Decimal('2.0'),  # 2L/1000L (coherente con 5L total)
            dose_type='l_per_1000l',
            total_dose=Decimal('5.0'),  # 5L total
            total_dose_unit='L',
            unit_price=Decimal('20.00'),
            organization=field.organization
        )

        # Producto 2: total_dose=15kg * 10€ = 150€
        TreatmentProductFactory(
            treatment=treatment1,
            product=ProductFactory(organization=field.organization, price=Decimal('10.00')),
            dose=Decimal('3.0'),  # 3kg/ha (coherente con 15kg total)
            dose_type='kg_per_ha',
            total_dose=Decimal('15.0'),  # 15kg total
            total_dose_unit='kg',
            unit_price=Decimal('10.00'),
            organization=field.organization
        )

        # Producto 3: total_dose=2L * 37.50€ = 75€
        TreatmentProductFactory(
            treatment=treatment2,
            product=ProductFactory(organization=field.organization, price=Decimal('37.50')),
            dose=Decimal('1.0'),  # 1L/1000L (coherente con 2L total)
            dose_type='l_per_1000l',
            total_dose=Decimal('2.0'),  # 2L total
            total_dose_unit='L',
            unit_price=Decimal('37.50'),
            organization=field.organization
        )

        # When: Calculamos el costo total de tratamientos
        total_cost = field.get_treatments_cost()

        # Then: El costo total debe ser la suma: 100€ + 150€ + 75€ = 325€
        assert total_cost == Decimal('325.00')

    def test_field_calculates_costs_within_date_range(self):
        # Given: Un campo con tratamientos en diferentes fechas
        field = FieldMothers.cost_analysis_field()  # 6ha para cálculos limpios

        # Tratamiento reciente: total_dose=10L * 10€ = 100€
        recent_treatment = TreatmentFactory(
            field=field,
            date=date.today() - timedelta(days=10),
            organization=field.organization
        )
        TreatmentProductFactory(
            treatment=recent_treatment,
            product=ProductFactory(organization=field.organization, price=Decimal('10.00')),
            dose=Decimal('2.5'),  # 2.5L/1000L (coherente con 10L total)
            dose_type='l_per_1000l',
            total_dose=Decimal('10.0'),  # 10L total
            total_dose_unit='L',
            unit_price=Decimal('10.00'),
            organization=field.organization
        )

        # Tratamiento antiguo: total_dose=40kg * 5€ = 200€
        old_treatment = TreatmentFactory(
            field=field,
            date=date.today() - timedelta(days=400),
            organization=field.organization
        )
        TreatmentProductFactory(
            treatment=old_treatment,
            product=ProductFactory(organization=field.organization, price=Decimal('5.00')),
            dose=Decimal('5.0'),  # 5kg/ha (coherente con 40kg total en 8ha)
            dose_type='kg_per_ha',
            total_dose=Decimal('40.0'),  # 40kg total
            total_dose_unit='kg',
            unit_price=Decimal('5.00'),
            organization=field.organization
        )

        # When: Calculamos costos para los últimos 30 días
        start_date = date.today() - timedelta(days=30)
        end_date = date.today()
        cost = field.get_treatments_cost(start_date, end_date)

        # Then: Solo debe incluir el tratamiento reciente (100€)
        assert cost == Decimal('100.00')

    def test_field_groups_costs_by_product_type(self):
        # Given: Un campo con productos de diferentes tipos usando mothers
        field = FieldMothers.medium_almond_field()  # 10ha
        treatment = TreatmentMothers.standard_spraying_400L(field)  # 400L/ha

        # Usamos mothers para productos con tipos claros
        herbicide_type = ProductTypeMothers.herbicide_type(field.organization)
        fertilizer_type = ProductTypeMothers.fertilizer_type(field.organization)

        herbicide = ProductMothers.standard_herbicide(field.organization)
        herbicide.product_type = herbicide_type
        herbicide.save()

        fertilizer = ProductMothers.premium_fertilizer(field.organization)
        fertilizer.product_type = fertilizer_type
        fertilizer.save()

        # Herbicida: 8L * 50€ = 400€
        TreatmentProductFactory(
            treatment=treatment,
            product=herbicide,
            dose=Decimal('2.0'),  # 2L/1000L
            dose_type='l_per_1000l',
            total_dose=Decimal('8.0'),  # 8L total (2L/1000L * 4000L)
            total_dose_unit='L',
            unit_price=Decimal('50.00'),
            organization=field.organization
        )

        # Fertilizante: 30kg * 25€ = 750€
        TreatmentProductFactory(
            treatment=treatment,
            product=fertilizer,
            dose=Decimal('3.0'),  # 3kg/ha
            dose_type='kg_per_ha',
            total_dose=Decimal('30.0'),  # 30kg total (3kg/ha * 10ha)
            total_dose_unit='kg',
            unit_price=Decimal('25.00'),
            organization=field.organization
        )

        # When: Obtenemos costos agrupados por tipo
        costs_by_type = field.get_cost_by_product_type()

        # Then: Debe agrupar correctamente por tipo de producto
        cost_dict = {item['product__product_type__name']: item['total']
                     for item in costs_by_type}

        assert cost_dict['Herbicida'] == Decimal('400.00')
        assert cost_dict['Fertilizante'] == Decimal('750.00')
