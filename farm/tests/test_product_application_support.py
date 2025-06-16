import pytest

from farm.tests.factories import *


@pytest.mark.django_db
class TestProductApplicationSupport:
    """
    Tests para verificar el soporte de aplicaciones en Product.
    Usamos factories específicas para cada tipo de producto.
    """

    def test_product_supports_spraying_when_configured(self):
        # Given: Un producto configurado solo para pulverización
        product = SprayingProductFactory(
            spraying_dose=2.5,
            spraying_dose_type='l_per_1000l',
            fertigation_dose=None,
            fertigation_dose_type=None
        )

        # When & Then: Debe soportar pulverización pero no fertirrigación
        assert product.supports_spraying is True
        assert product.supports_fertigation is False
        assert product.supports_application_type('spraying') is True
        assert product.supports_application_type('fertigation') is False

    def test_product_supports_fertigation_when_configured(self):
        # Given: Un producto configurado solo para fertirrigación
        product = FertigationProductFactory(
            spraying_dose=None,
            spraying_dose_type=None,
            fertigation_dose=5.0,
            fertigation_dose_type='l_per_ha'
        )

        # When & Then: Debe soportar fertirrigación pero no pulverización
        assert product.supports_spraying is False
        assert product.supports_fertigation is True
        assert product.supports_application_type('spraying') is False
        assert product.supports_application_type('fertigation') is True

    def test_product_supports_both_applications(self):
        # Given: Un producto configurado para ambas aplicaciones
        product = ProductFactory(
            spraying_dose=2.5,
            spraying_dose_type='l_per_1000l',
            fertigation_dose=5.0,
            fertigation_dose_type='l_per_ha'
        )

        # When & Then: Debe soportar ambas aplicaciones
        assert product.supports_spraying is True
        assert product.supports_fertigation is True
        assert product.supports_application_type('spraying') is True
        assert product.supports_application_type('fertigation') is True
