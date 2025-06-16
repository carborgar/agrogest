"""
Object Mothers para escenarios comunes de testing.
"""

from farm.tests.factories import *


class FieldMothers:
    """Mothers para diferentes tipos de campos"""

    @staticmethod
    def small_olive_field():
        """Campo pequeño de olivos (5ha) - ideal para cálculos simples"""
        return FieldFactory(
            area=5.0,
            crop="Olivo",
            name="Campo Pequeño Olivos"
        )

    @staticmethod
    def medium_almond_field():
        """Campo mediano de almendros (10ha) - para casos complejos"""
        return FieldFactory(
            area=10.0,
            crop="Almendro",
            name="Campo Mediano Almendros"
        )

    @staticmethod
    def cost_analysis_field():
        """Campo optimizado para análisis de costos (6ha)"""
        return FieldFactory(
            area=6.0,
            crop="Olivo",
            name="Campo Análisis Costos"
        )


class ProductTypeMothers:
    """Mothers para tipos de productos"""

    @staticmethod
    def herbicide_type(organization):
        return ProductTypeFactory(
            name="Herbicida",
            organization=organization,
            description="Productos para control de malas hierbas"
        )

    @staticmethod
    def fertilizer_type(organization):
        return ProductTypeFactory(
            name="Fertilizante",
            organization=organization,
            description="Productos para nutrición de cultivos"
        )

    @staticmethod
    def fungicide_type(organization):
        return ProductTypeFactory(
            name="Fungicida",
            organization=organization,
            description="Productos para control de hongos"
        )


class ProductMothers:
    """Mothers para productos con configuraciones realistas"""

    @staticmethod
    def standard_herbicide(organization):
        """Herbicida estándar: 2L/1000L, 50€/L"""
        herbicide_type = ProductTypeMothers.herbicide_type(organization)
        return SprayingProductFactory(
            name="Herbicida Estándar",
            product_type=herbicide_type,
            organization=organization,
            price=Decimal('50.00'),
            spraying_dose=2.0,
            spraying_dose_type='l_per_1000l'
        )

    @staticmethod
    def premium_fertilizer(organization):
        """Fertilizante premium: 3kg/ha, 25€/kg"""
        fertilizer_type = ProductTypeMothers.fertilizer_type(organization)
        return SprayingProductFactory(
            name="Fertilizante Premium",
            product_type=fertilizer_type,
            organization=organization,
            price=Decimal('25.00'),
            spraying_dose=3.0,
            spraying_dose_type='kg_per_ha'
        )

    @staticmethod
    def budget_fungicide(organization):
        """Fungicida económico: 1L/1000L, 37.50€/L"""
        fungicide_type = ProductTypeMothers.fungicide_type(organization)
        return SprayingProductFactory(
            name="Fungicida Económico",
            product_type=fungicide_type,
            organization=organization,
            price=Decimal('37.50'),
            spraying_dose=1.0,
            spraying_dose_type='l_per_1000l'
        )


class TreatmentMothers:
    """Mothers para tratamientos con configuraciones típicas"""

    @staticmethod
    def standard_spraying_400L(field):
        """Tratamiento de pulverización estándar: 400L/ha"""
        return SprayingTreatmentFactory(
            field=field,
            water_per_ha=400,
            name="Pulverización Estándar 400L",
            organization=field.organization
        )

    @staticmethod
    def high_volume_spraying_600L(field):
        """Tratamiento con alto volumen de agua: 600L/ha"""
        return SprayingTreatmentFactory(
            field=field,
            water_per_ha=600,
            name="Pulverización Alto Volumen 600L",
            organization=field.organization
        )

    @staticmethod
    def completed_treatment_last_month(field):
        """Tratamiento completado hace un mes"""
        return TreatmentFactory(
            field=field,
            date=date.today() - timedelta(days=30),
            finish_date=date.today() - timedelta(days=29),
            name="Tratamiento Completado",
            organization=field.organization
        )

    @staticmethod
    def old_treatment_last_year(field):
        """Tratamiento muy antiguo (hace 400 días)"""
        return TreatmentFactory(
            field=field,
            date=date.today() - timedelta(days=400),
            finish_date=date.today() - timedelta(days=399),
            name="Tratamiento Antiguo",
            organization=field.organization
        )

    @staticmethod
    def pending_treatment_with_changeable_water(field):
        """Tratamiento pendiente que puede cambiar su mojado real"""
        return SprayingTreatmentFactory(
            field=field,
            water_per_ha=400,  # Mojado planificado
            real_water_per_ha=None,  # Sin mojado real aún
            date=date.today() - timedelta(days=1),  # Ayer (atrasado)
            finish_date=None,  # Sin completar
            name="Tratamiento Pendiente Variable",
            organization=field.organization
        )


class TreatmentProductMothers:
    """Mothers para aplicaciones específicas con costos conocidos"""

    @staticmethod
    def herbicide_application_400_euros(treatment):
        """
        Aplicación de herbicida que cuesta 400€
        Campo 10ha, 400L/ha = 4000L total
        2L/1000L * 4000L = 8L * 50€/L = 400€
        """
        product = ProductMothers.standard_herbicide(treatment.organization)

        return TreatmentProductFactory(
            treatment=treatment,
            product=product,
            dose=Decimal('2.0'),
            dose_type='l_per_1000l',
            total_dose=Decimal('8.0'),  # 8L total
            total_dose_unit='L',
            unit_price=Decimal('50.00'),
            organization=treatment.organization
        )

    @staticmethod
    def fertilizer_application_750_euros(treatment):
        """
        Aplicación de fertilizante que cuesta 750€
        Campo 10ha
        3kg/ha * 10ha = 30kg * 25€/kg = 750€
        """
        product = ProductMothers.premium_fertilizer(treatment.organization)

        return TreatmentProductFactory(
            treatment=treatment,
            product=product,
            dose=Decimal('3.0'),
            dose_type='kg_per_ha',
            total_dose=Decimal('30.0'),  # 30kg total
            total_dose_unit='kg',
            unit_price=Decimal('25.00'),
            organization=treatment.organization
        )

    @staticmethod
    def fungicide_application_75_euros(treatment):
        """
        Aplicación de fungicida que cuesta 75€
        Campo 5ha, 400L/ha = 2000L total
        1L/1000L * 2000L = 2L * 37.50€/L = 75€
        """
        product = ProductMothers.budget_fungicide(treatment.organization)

        return TreatmentProductFactory(
            treatment=treatment,
            product=product,
            dose=Decimal('1.0'),
            dose_type='l_per_1000l',
            total_dose=Decimal('2.0'),  # 2L total
            total_dose_unit='L',
            unit_price=Decimal('37.50'),
            organization=treatment.organization
        )
