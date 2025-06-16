import pytest

from farm.tests.factories import *


@pytest.mark.django_db
class TestPriceCalculations:
    """
    Tests para verificar los cálculos de precios en TreatmentProduct.
    Usamos factories para control preciso de los valores numéricos.
    """

    def test_treatment_product_calculates_prices_correctly(self):
        # Given: Un producto de tratamiento con precio unitario conocido
        field = FieldFactory(area=5.0)
        treatment = TreatmentFactory(
            field=field,
            organization=field.organization
        )

        treatment_product = TreatmentProductFactory(
            treatment=treatment,
            product=ProductFactory(organization=field.organization),
            total_dose=Decimal('10.0'),
            total_dose_unit='L',
            unit_price=Decimal('25.50'),
            organization=field.organization
        )

        # When: Se calcula automáticamente en el save()
        # Then: Los precios deben estar correctos
        expected_total_price = Decimal('255.00')  # 10.0 * 25.50
        expected_price_per_ha = Decimal('51.00')  # 255.00 / 5.0

        assert treatment_product.total_price == expected_total_price
        assert treatment_product.price_per_ha == expected_price_per_ha

    def test_price_updates_when_total_dose_changes(self):
        # Given: Un producto de tratamiento existente
        field = FieldFactory(area=4.0)
        treatment = TreatmentFactory(
            field=field,
            organization=field.organization
        )

        treatment_product = TreatmentProductFactory(
            treatment=treatment,
            product=ProductFactory(organization=field.organization),
            total_dose=Decimal('8.0'),
            total_dose_unit='kg',
            unit_price=Decimal('30.00'),
            organization=field.organization
        )

        initial_total_price = treatment_product.total_price
        initial_price_per_ha = treatment_product.price_per_ha

        # When: Cambiamos la dosis total
        treatment_product.total_dose = Decimal('12.0')
        treatment_product.save()

        # Then: Los precios deben actualizarse
        assert treatment_product.total_price > initial_total_price
        assert treatment_product.price_per_ha > initial_price_per_ha
        assert treatment_product.total_price == Decimal('360.00')  # 12.0 * 30.00
        assert treatment_product.price_per_ha == Decimal('90.00')  # 360.00 / 4.0
