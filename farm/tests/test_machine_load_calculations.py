import pytest

from farm.tests.factories import *


@pytest.mark.django_db
class TestMachineLoadCalculations:
    """
    Tests para verificar los cálculos de cargas de máquina.
    Usamos factories para control preciso de capacidades y volúmenes.
    """

    def test_machine_load_calculation_for_exact_loads(self):
        # Given: Un tratamiento que requiere exactamente 2 cargas completas
        field = FieldFactory(area=5.0)  # 5 hectáreas
        machine = MachineFactory(
            capacity=1000,  # 1000L de capacidad
            organization=field.organization
        )
        treatment = SprayingTreatmentFactory(
            field=field,
            machine=machine,
            water_per_ha=400,  # 400L/ha * 5ha = 2000L total = 2 cargas exactas
            organization=field.organization
        )

        # When: Calculamos las cargas necesarias
        loads = treatment.calculate_machine_loads()

        # Then: Debe requerir exactamente 2 cargas completas
        assert loads['total_water'] == 2000
        assert loads['full_loads'] == 2
        assert loads['partial_load'] is False
        assert loads['partial_water'] == 0

    def test_machine_load_calculation_with_partial_load(self):
        # Given: Un tratamiento que requiere cargas completas + una parcial
        field = FieldFactory(area=6.0)  # 6 hectáreas
        machine = MachineFactory(
            capacity=1000,  # 1000L de capacidad
            organization=field.organization
        )
        treatment = SprayingTreatmentFactory(
            field=field,
            machine=machine,
            water_per_ha=400,  # 400L/ha * 6ha = 2400L = 2 cargas + 400L parcial
            organization=field.organization
        )

        # When: Calculamos las cargas necesarias
        loads = treatment.calculate_machine_loads()

        # Then: Debe tener 2 cargas completas + 1 parcial
        assert loads['total_water'] == 2400
        assert loads['full_loads'] == 2
        assert loads['partial_load'] is True
        assert loads['partial_water'] == 400

    def test_product_calculation_for_partial_load(self):
        # Given: Un tratamiento con carga parcial y un producto
        field = FieldFactory(area=6.0)
        machine = MachineFactory(
            capacity=1000,
            organization=field.organization
        )
        treatment = SprayingTreatmentFactory(
            field=field,
            machine=machine,
            water_per_ha=400,  # Total: 2400L = 2 cargas + 400L parcial
            organization=field.organization
        )

        product = SprayingProductFactory(
            spraying_dose=3.0,
            spraying_dose_type='l_per_1000l',
            organization=field.organization
        )

        treatment_product = TreatmentProductFactory(
            treatment=treatment,
            product=product,
            dose=Decimal('3.0'),
            dose_type='l_per_1000l',
            total_dose=Decimal('7.2'),  # 3L/1000L * 2400L = 7.2L
            total_dose_unit='L',
            unit_price=Decimal('20.00'),
            organization=field.organization
        )

        # When: Calculamos el producto necesario para la carga parcial
        partial_product = treatment.calculate_product_for_partial_load(treatment_product)

        # Then: Debe calcular correctamente para 400L de agua parcial
        expected = 1.2  # 3.0 * 400 / 1000
        assert partial_product == expected
