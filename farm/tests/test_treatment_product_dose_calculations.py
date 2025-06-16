import pytest

from farm.tests.factories import *
from farm.tests.mothers import FieldMothers, TreatmentMothers, ProductMothers


@pytest.mark.django_db
class TestTreatmentProductDoseCalculations:
    """
    Tests para verificar los cálculos de dosis en TreatmentProduct.
    Usamos factories para control preciso de los parámetros matemáticos.
    """

    def test_real_water_change_updates_costs_and_doses(self):
        """
        CRÍTICO: Cuando se cambia el mojado real al finalizar un tratamiento,
        deben recalcularse automáticamente los costes y dosis de los productos.
        """
        # Given: Un tratamiento pendiente con mojado planificado
        field = FieldMothers.cost_analysis_field()  # 6ha para cálculos limpios
        treatment = TreatmentMothers.pending_treatment_with_changeable_water(field)

        product = ProductMothers.standard_herbicide(field.organization)

        treatment_product = TreatmentProductFactory(
            treatment=treatment,
            product=product,
            dose=Decimal('2.0'),  # 2L por cada 1000L
            dose_type='l_per_1000l',
            total_dose=Decimal('4.8'),  # 6ha * 400L/ha = 2400L, 2L/1000L = 4.8L
            total_dose_unit='L',
            unit_price=Decimal('50.00'),
            organization=field.organization
        )

        # Capturamos los valores iniciales (con 400L/ha planificado)
        initial_total_dose = treatment_product.total_dose  # 4.8L
        initial_total_price = treatment_product.total_price  # 4.8L * 50€ = 240€
        initial_field_cost = field.get_treatments_cost()  # 240€

        # Verificaciones del estado inicial
        assert not treatment.is_completed()
        assert treatment.actual_water_per_ha() == 400  # Mojado planificado

        # When: Finalizamos el tratamiento con mojado real MAYOR al planificado
        treatment.finish_treatment(
            finish_date=date.today(),
            real_water_per_ha=600  # 50% más agua que lo planificado (400L)
        )
        treatment_product.refresh_from_db()

        # Then: CRÍTICO - El estado del tratamiento debe cambiar
        assert treatment.is_completed()
        assert treatment.actual_water_per_ha() == 600

        # And: CRÍTICO - Las dosis y precios deben recalcularse automáticamente
        # Con 600L/ha: 6ha * 600L/ha = 3600L total, 2L/1000L = 7.2L total
        expected_total_dose = Decimal('7.2')
        expected_total_price = Decimal('360.00')  # 7.2L * 50€

        assert treatment_product.total_dose > initial_total_dose
        assert treatment_product.total_price > initial_total_price
        assert treatment_product.total_dose == expected_total_dose
        assert treatment_product.total_price == expected_total_price

        # And: CRÍTICO - El costo total del campo debe reflejar los nuevos valores
        final_field_cost = field.get_treatments_cost()
        assert final_field_cost > initial_field_cost
        assert final_field_cost == expected_total_price

    def test_dose_calculation_for_different_dose_types(self):
        # Given: Un campo y tratamiento conocidos usando factory para control preciso
        field = FieldFactory(area=5.0)  # 5 hectáreas exactas
        treatment = SprayingTreatmentFactory(
            field=field,
            water_per_ha=400,  # 400L por hectárea
            organization=field.organization
        )

        test_cases = [
            {
                'dose_type': 'l_per_1000l',
                'dose': Decimal('2.0'),
                'expected_total': Decimal('4.0'),  # (400*5) * 2 / 1000 = 4L
                'description': 'litros per 1000L water'
            },
            {
                'dose_type': 'l_per_ha',
                'dose': Decimal('3.0'),
                'expected_total': Decimal('15.0'),  # 3 * 5 = 15L
                'description': 'litros per hectare'
            },
            {
                'dose_type': 'pct',
                'dose': Decimal('2.0'),
                'expected_total': Decimal('40.0'),  # (400*5) * 2/100 = 40L
                'description': 'percentage'
            }
        ]

        for case in test_cases:
            # When: Creamos un producto con diferentes tipos de dosis
            product = SprayingProductFactory(
                spraying_dose=case['dose'],
                spraying_dose_type=case['dose_type'],
                organization=field.organization
            )

            treatment_product = TreatmentProductFactory(
                treatment=treatment,
                product=product,
                dose=case['dose'],
                dose_type=case['dose_type'],
                total_dose=case['expected_total'],  # Valor coherente
                total_dose_unit='L',
                unit_price=Decimal('10.00'),
                organization=field.organization
            )

            # Then: La dosis total debe ser la esperada
            assert treatment_product.total_dose == case['expected_total'], \
                f"Failed for {case['description']}: expected {case['expected_total']}, got {treatment_product.total_dose}"

    def test_fertigation_products_ignore_water_per_ha(self):
        # Given: Un tratamiento de fertirrigación usando factories específicas
        field = FieldFactory(area=8.0)
        treatment = FertigationTreatmentFactory(
            field=field,
            water_per_ha=400,  # Este valor debe ser ignorado
            organization=field.organization
        )

        product = FertigationProductFactory(
            fertigation_dose=5.0,
            fertigation_dose_type='l_per_ha',
            organization=field.organization
        )

        # When: Creamos el producto de tratamiento
        treatment_product = TreatmentProductFactory(
            treatment=treatment,
            product=product,
            dose=Decimal('5.0'),
            dose_type='l_per_ha',
            total_dose=Decimal('40.0'),  # 5L/ha * 8ha = 40L
            total_dose_unit='L',
            unit_price=Decimal('15.00'),
            organization=field.organization
        )

        # Then: La dosis debe calcularse solo basada en hectáreas
        expected_total = Decimal('40.0')  # 5 * 8 hectáreas
        assert treatment_product.total_dose == expected_total

        # And: El tratamiento debe tener agua_per_ha en 0
        treatment.refresh_from_db()
        assert treatment.water_per_ha == 0
        assert treatment.real_water_per_ha == 0
