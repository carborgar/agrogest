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

    def test_product_price_change_updates_only_non_completed_treatments(self):
        field = FieldFactory(area=4.0)
        product = ProductFactory(organization=field.organization, price=Decimal('20.00'))

        pending_treatment = TreatmentFactory(
            field=field,
            organization=field.organization,
            date=date.today() + timedelta(days=1),
            finish_date=None,
        )
        completed_treatment = TreatmentFactory(
            field=field,
            organization=field.organization,
            date=date.today() - timedelta(days=2),
            finish_date=date.today() - timedelta(days=1),
        )

        pending_treatment_product = TreatmentProductFactory(
            treatment=pending_treatment,
            product=product,
            unit_price=Decimal('20.00'),
            organization=field.organization,
        )
        completed_treatment_product = TreatmentProductFactory(
            treatment=completed_treatment,
            product=product,
            unit_price=Decimal('20.00'),
            organization=field.organization,
        )

        original_completed_unit_price = completed_treatment_product.unit_price

        product.price = Decimal('35.00')
        product.save()

        pending_treatment_product.refresh_from_db()
        completed_treatment_product.refresh_from_db()

        assert pending_treatment_product.unit_price == Decimal('35.00')
        assert pending_treatment_product.total_price == Decimal('35.00') * pending_treatment_product.total_dose
        assert pending_treatment_product.price_per_ha == pending_treatment_product.total_price / Decimal('4.0')
        assert completed_treatment_product.unit_price == original_completed_unit_price
