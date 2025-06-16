# tests/factories.py
"""
Factories para crear objetos de prueba fácilmente.
Una factory es como un molde que crea objetos con datos de prueba realistas.
"""

from datetime import date, timedelta
from decimal import Decimal

import factory

from accounts.models import Organization
from farm.models import Field, Machine, ProductType, Product, Treatment, TreatmentProduct


# Organización compartida para todos los tests
class OrganizationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Organization
        django_get_or_create = ('name',)  # Reutiliza si ya existe

    name = "Organización Test"


class FieldFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Field

    organization = factory.SubFactory(OrganizationFactory)
    name = factory.Sequence(lambda n: f"Campo Test {n}")
    area = 10.0
    crop = "Olivo"
    planting_year = 2020


class MachineFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Machine

    organization = factory.SubFactory(OrganizationFactory)
    name = factory.Sequence(lambda n: f"Máquina Test {n}")
    type = "Pulverizador"
    capacity = 1000


class ProductTypeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ProductType

    organization = factory.SubFactory(OrganizationFactory)
    name = factory.Sequence(lambda n: f"Tipo {n}")


class ProductFactory(factory.django.DjangoModelFactory):
    """Producto que funciona para ambos tipos (spray y fertirrigación)"""

    class Meta:
        model = Product

    organization = factory.SubFactory(OrganizationFactory)
    product_type = factory.SubFactory(ProductTypeFactory)
    name = factory.Sequence(lambda n: f"Producto Test {n}")
    price = Decimal('25.00')

    # Para spray
    spraying_dose = 2.5
    spraying_dose_type = 'l_per_1000l'

    # Para fertirrigación
    fertigation_dose = 5.0
    fertigation_dose_type = 'l_per_ha'


class SprayingProductFactory(ProductFactory):
    """Producto solo para pulverización"""
    name = factory.Sequence(lambda n: f"Producto Spray {n}")
    price = Decimal('30.00')

    spraying_dose = 2.0
    spraying_dose_type = 'l_per_1000l'

    fertigation_dose = None
    fertigation_dose_type = None


class FertigationProductFactory(ProductFactory):
    """Producto solo para fertirrigación"""
    name = factory.Sequence(lambda n: f"Producto Ferti {n}")
    price = Decimal('40.00')

    spraying_dose = None
    spraying_dose_type = None

    fertigation_dose = 8.0
    fertigation_dose_type = 'l_per_ha'


class TreatmentFactory(factory.django.DjangoModelFactory):
    """Tratamiento genérico"""

    class Meta:
        model = Treatment

    organization = factory.SubFactory(OrganizationFactory)
    field = factory.SubFactory(FieldFactory)
    machine = factory.SubFactory(MachineFactory)
    name = factory.Sequence(lambda n: f"Tratamiento Test {n}")
    type = 'spraying'
    date = factory.LazyFunction(lambda: date.today() - timedelta(days=5))  # ← EN EL PASADO
    water_per_ha = 400


class SprayingTreatmentFactory(TreatmentFactory):
    """Tratamiento de pulverización"""
    type = 'spraying'
    machine = factory.SubFactory(MachineFactory)
    water_per_ha = 500


class FertigationTreatmentFactory(TreatmentFactory):
    """Tratamiento de fertirrigación"""
    type = 'fertigation'
    machine = None
    water_per_ha = 0


class TreatmentProductFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TreatmentProduct

    treatment = factory.SubFactory(TreatmentFactory)
    product = factory.SubFactory(ProductFactory)

    # Valores básicos - el test los ajustará según necesite
    dose = Decimal('1.0')
    dose_type = 'l_per_1000l'
    total_dose = Decimal('1.0')
    total_dose_unit = 'L'
    unit_price = Decimal('10.00')


class SprayingTreatmentProductFactory(TreatmentProductFactory):
    treatment = factory.SubFactory(SprayingTreatmentFactory)
    product = factory.SubFactory(SprayingProductFactory)


class FertigationTreatmentProductFactory(TreatmentProductFactory):
    treatment = factory.SubFactory(FertigationTreatmentFactory)
    product = factory.SubFactory(FertigationProductFactory)
