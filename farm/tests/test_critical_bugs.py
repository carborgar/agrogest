import pytest

from farm.tests.factories import *
from farm.tests.mothers import FieldMothers, ProductMothers


@pytest.mark.django_db
class TestCriticalBugScenarios:

    def test_complete_treatment_workflow_with_cost_tracking(self):
        """
        Test de integración completo usando mothers para el escenario base
        y factories para control preciso de los cálculos.
        """
        # Given: Un campo y productos configurados con mothers
        field = FieldMothers.cost_analysis_field()  # 6ha
        machine = MachineFactory(
            capacity=1000,
            organization=field.organization
        )

        herbicide = ProductMothers.standard_herbicide(field.organization)
        fertilizer = ProductMothers.premium_fertilizer(field.organization)

        # When: Creamos un tratamiento con múltiples productos
        treatment = SprayingTreatmentFactory(
            field=field,
            machine=machine,
            water_per_ha=500,  # 6ha * 500L/ha = 3000L total
            date=date.today() - timedelta(days=1),  # Ayer (atrasado)
            organization=field.organization
        )

        # Herbicida: 2L/1000L * 3000L = 6L * 45€ = 270€
        herbicide_treatment = TreatmentProductFactory(
            treatment=treatment,
            product=herbicide,
            dose=Decimal('2.0'),
            dose_type='l_per_1000l',
            total_dose=Decimal('6.0'),
            total_dose_unit='L',
            unit_price=Decimal('45.00'),
            organization=field.organization
        )

        # Fertilizante: 3kg/ha * 6ha = 18kg * 30€ = 540€
        fertilizer_treatment = TreatmentProductFactory(
            treatment=treatment,
            product=fertilizer,
            dose=Decimal('3.0'),
            dose_type='kg_per_ha',
            total_dose=Decimal('18.0'),
            total_dose_unit='kg',
            unit_price=Decimal('30.00'),
            organization=field.organization
        )

        # Then: Verificamos estado inicial
        assert treatment.is_delayed()
        initial_field_cost = field.get_treatments_cost()
        assert initial_field_cost == Decimal('810.00')  # 270€ + 540€

        # When: Completamos el tratamiento con mojado real diferente
        treatment.real_water_per_ha = 600  # Mayor que el planificado (500L)
        treatment.finish_date = date.today()
        treatment.save()

        # Refrescamos los objetos
        herbicide_treatment.refresh_from_db()
        fertilizer_treatment.refresh_from_db()

        # Then: El tratamiento debe estar completado
        assert treatment.is_completed()

        # And: Los costos deben haberse recalculado correctamente
        final_field_cost = field.get_treatments_cost()
        assert final_field_cost > initial_field_cost  # Más mojado = más costo

        # Herbicida con 600L/ha: 6ha * 600L/ha = 3600L, 2L/1000L = 7.2L * 45€ = 324€
        # Fertilizante no cambia: 18kg * 30€ = 540€
        # Total esperado: 324€ + 540€ = 864€
        assert final_field_cost == Decimal('864.00')

    def test_multi_treatment_field_cost_analysis(self):
        """
        Verifica que los análisis de costos funcionen correctamente
        con múltiples tratamientos usando mothers para claridad.
        """
        # Given: Un campo con tratamientos distribuidos en el tiempo
        field = FieldMothers.medium_almond_field()  # 10ha

        # Tratamiento hace 2 meses: 300€
        old_treatment = TreatmentFactory(
            field=field,
            date=date.today() - timedelta(days=60),
            finish_date=date.today() - timedelta(days=59),
            organization=field.organization
        )
        TreatmentProductFactory(
            treatment=old_treatment,
            product=ProductFactory(organization=field.organization),
            total_dose=Decimal('10.0'),
            total_dose_unit='L',
            unit_price=Decimal('30.00'),
            organization=field.organization
        )

        # Tratamiento hace 2 semanas: 450€
        recent_treatment = TreatmentFactory(
            field=field,
            date=date.today() - timedelta(days=14),
            finish_date=date.today() - timedelta(days=13),
            organization=field.organization
        )
        TreatmentProductFactory(
            treatment=recent_treatment,
            product=ProductFactory(organization=field.organization),
            total_dose=Decimal('15.0'),
            total_dose_unit='kg',
            unit_price=Decimal('30.00'),
            organization=field.organization
        )

        # Tratamiento pendiente: 200€
        future_treatment = TreatmentFactory(
            field=field,
            date=date.today() + timedelta(days=7),
            organization=field.organization
        )
        TreatmentProductFactory(
            treatment=future_treatment,
            product=ProductFactory(organization=field.organization),
            total_dose=Decimal('8.0'),
            total_dose_unit='L',
            unit_price=Decimal('25.00'),
            organization=field.organization
        )

        # When & Then: Análisis de costos por período
        total_cost = field.get_treatments_cost()
        assert total_cost == Decimal('950.00')  # 300€ + 450€ + 200€

        # Costos último mes
        last_month_start = date.today() - timedelta(days=30)
        last_month_cost = field.get_treatments_cost(last_month_start)
        assert last_month_cost == Decimal('650.00')  # 450€ + 200€

        # Costos solo completados
        completed_cost = field.get_treatments_cost(
            end_date=date.today() - timedelta(days=1)
        )
        assert completed_cost == Decimal('750.00')  # 300€ + 450€

    def test_fertigation_vs_spraying_cost_comparison(self):
        """
        Verifica que los cálculos de costos sean correctos y comparables
        entre tratamientos de fertirrigación y pulverización usando mothers.
        """
        # Given: Un campo con ambos tipos de tratamientos
        field = FieldMothers.medium_almond_field()  # 10ha

        # Tratamiento de pulverización usando mothers
        spraying_machine = MachineFactory(
            capacity=800,
            organization=field.organization
        )
        spray_product = ProductMothers.standard_herbicide(field.organization)

        spraying_treatment = SprayingTreatmentFactory(
            field=field,
            machine=spraying_machine,
            water_per_ha=400,  # 10ha * 400L/ha = 4000L
            organization=field.organization
        )

        # Herbicida: 2L/1000L * 4000L = 8L * 35€ = 280€
        spray_treatment_product = TreatmentProductFactory(
            treatment=spraying_treatment,
            product=spray_product,
            dose=Decimal('2.0'),
            dose_type='l_per_1000l',
            total_dose=Decimal('8.0'),
            total_dose_unit='L',
            unit_price=Decimal('35.00'),
            organization=field.organization
        )

        # Tratamiento de fertirrigación
        ferti_product = FertigationProductFactory(
            fertigation_dose=6.0,
            fertigation_dose_type='l_per_ha',
            price=Decimal('28.00'),
            organization=field.organization
        )

        fertigation_treatment = FertigationTreatmentFactory(
            field=field,
            organization=field.organization
        )

        # Fertilizante: 6L/ha * 10ha = 60L * 28€ = 1680€
        ferti_treatment_product = TreatmentProductFactory(
            treatment=fertigation_treatment,
            product=ferti_product,
            dose=Decimal('6.0'),
            dose_type='l_per_ha',
            total_dose=Decimal('60.0'),
            total_dose_unit='L',
            unit_price=Decimal('28.00'),
            organization=field.organization
        )

        # When & Then: Ambos tratamientos deben tener costos por hectárea válidos
        spray_cost_per_ha = spray_treatment_product.price_per_ha
        ferti_cost_per_ha = ferti_treatment_product.price_per_ha

        assert spray_cost_per_ha == Decimal('28.00')  # 280€ / 10ha
        assert ferti_cost_per_ha == Decimal('168.00')  # 1680€ / 10ha

        # El costo total del campo debe ser la suma de ambos
        total_field_cost = field.get_treatments_cost()
        expected_total = Decimal('1960.00')  # 280€ + 1680€
        assert total_field_cost == expected_total

        # Los costos por hectárea deben sumar correctamente
        total_cost_per_ha = total_field_cost / Decimal(field.area)
        sum_costs_per_ha = spray_cost_per_ha + ferti_cost_per_ha
        assert abs(total_cost_per_ha - sum_costs_per_ha) < Decimal('0.01')

    def test_machine_load_optimization_with_multiple_products(self):
        """
        Verifica que los cálculos de cargas de máquina funcionen correctamente
        cuando hay múltiples productos con diferentes tipos de dosis.
        Usa factories para control preciso de los cálculos matemáticos.
        """
        # Given: Un tratamiento complejo con múltiples productos
        field = FieldFactory(area=7.5)  # Área que generará cargas parciales
        machine = MachineFactory(
            capacity=1200,
            organization=field.organization
        )

        treatment = SprayingTreatmentFactory(
            field=field,
            machine=machine,
            water_per_ha=500,  # 7.5 * 500 = 3750L total
            organization=field.organization
        )

        # Productos con diferentes tipos de dosis
        products_data = [
            {
                'dose': 2.5,
                'dose_type': 'l_per_1000l',
                'total_dose': 9.375,  # 2.5 * 3750 / 1000
                'expected_per_load': 3.0  # 2.5 * 1200 / 1000
            },
            {
                'dose': 1.0,
                'dose_type': 'kg_per_ha',
                'total_dose': 7.5,  # 1.0 * 7.5ha
                'expected_per_load': 1.6  # 1.0 * (1200/500) hectáreas por carga
            },
            {
                'dose': 1.5,
                'dose_type': 'pct',
                'total_dose': 56.25,  # 1.5 * 3750 / 100
                'expected_per_load': 18.0  # 1.5 * 1200 / 100
            }
        ]

        # When: Creamos los productos de tratamiento
        treatment_products = []
        for product_data in products_data:
            product = SprayingProductFactory(
                spraying_dose=product_data['dose'],
                spraying_dose_type=product_data['dose_type'],
                organization=field.organization
            )

            treatment_product = TreatmentProductFactory(
                treatment=treatment,
                product=product,
                dose=Decimal(str(product_data['dose'])),
                dose_type=product_data['dose_type'],
                total_dose=Decimal(str(product_data['total_dose'])),
                total_dose_unit='L' if 'l_' in product_data['dose_type'] or 'pct' in product_data[
                    'dose_type'] else 'kg',
                unit_price=Decimal('20.00'),
                organization=field.organization
            )
            treatment_products.append(treatment_product)

        # Then: Verificamos los cálculos de cargas
        loads = treatment.calculate_machine_loads()
        assert loads['total_water'] == 3750
        assert loads['full_loads'] == 3  # 3 cargas de 1200L
        assert loads['partial_load'] is True
        assert loads['partial_water'] == 150  # 3750 - (3 * 1200)

        # And: Verificamos las dosis por carga para cada producto
        for i, (treatment_product, expected_data) in enumerate(
                zip(treatment_products, products_data)
        ):
            dose_per_load = treatment_product.get_dose_per_load()
            expected_dose = expected_data['expected_per_load']

            assert abs(dose_per_load - expected_dose) < 0.1, \
                f"Product {i}: expected {expected_dose}, got {dose_per_load}"
