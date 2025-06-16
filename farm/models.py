from datetime import datetime
from decimal import Decimal

from django.db import models
from softdelete.models import SoftDeleteObject

from .managers import OwnershipManager


class OrganizationOwnedModel(models.Model):
    """
    Modelo base abstracto que implementa la relación con una organización.
    """
    organization = models.ForeignKey('accounts.Organization', on_delete=models.RESTRICT, related_name="%(class)ss")
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = models.Manager()  # Manager predeterminado
    ownership_objects = OwnershipManager()  # Manager personalizado

    class Meta:
        abstract = True


class Field(OrganizationOwnedModel):
    name = models.CharField(max_length=100)
    area = models.FloatField()  # en hectáreas
    crop = models.CharField(max_length=100)
    planting_year = models.IntegerField()
    location = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return self.name

    def pending_treatments_count(self):
        # Cuenta los tratamientos pendientes para este campo
        objs = Treatment.objects.filter(field=self, status='pending')
        return objs.count()

    def completed_treatments_count(self):
        # Cuenta los tratamientos completados para este campo
        return Treatment.objects.filter(field=self, status='completed').count()

    def delayed_treatments_count(self):
        # Cuenta los tratamientos atrasados para este campo
        return Treatment.objects.filter(field=self, status='delayed').count()

    def get_treatments_cost(self, start_date=None, end_date=None):
        """
        Calcula el costo total de tratamientos para esta parcela en un rango de fechas.
        Si no se especifican fechas, devuelve el costo total de todos los tratamientos.
        """
        from django.db.models import Sum
        from datetime import datetime, timedelta

        # Si no se proporcionan fechas, usar último año por defecto
        if not start_date:
            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=365)

        treatments = Treatment.objects.filter(field=self)
        if start_date:
            treatments = treatments.filter(date__gte=start_date)
        if end_date:
            treatments = treatments.filter(date__lte=end_date)

        # Sumar todos los costos de productos asociados a estos tratamientos
        cost_sum = treatments.annotate(
            treatment_cost=Sum('treatmentproduct__total_price')
        ).aggregate(total_cost=Sum('treatment_cost'))

        return cost_sum['total_cost'] or 0

    def get_cost_by_product_type(self, start_date=None, end_date=None):
        """
        Devuelve un diccionario con el costo agrupado por tipo de producto
        """
        from datetime import datetime, timedelta

        # Si no se proporcionan fechas, usar último año por defecto
        if not start_date:
            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=365)

        treatments = Treatment.objects.filter(field=self)
        if start_date:
            treatments = treatments.filter(date__gte=start_date)
        if end_date:
            treatments = treatments.filter(date__lte=end_date)

        treatment_ids = treatments.values_list('id', flat=True)

        # Agrupar por tipo de producto
        from django.db.models import Sum
        cost_by_type = TreatmentProduct.objects.filter(
            treatment_id__in=treatment_ids
        ).values(
            'product__product_type__name'
        ).annotate(
            total=Sum('total_price')
        ).order_by('-total')

        return cost_by_type

    def can_be_deleted(self):
        return not Treatment.objects.filter(field=self).exists()


class Machine(OrganizationOwnedModel):
    name = models.CharField(max_length=100)
    type = models.CharField(max_length=50)  # Ej. Pulverizador
    capacity = models.IntegerField()  # Capacidad en litros

    def __str__(self):
        return f"{self.name}"


class ProductType(OrganizationOwnedModel):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name


class Product(OrganizationOwnedModel):
    # Separate choices for each application method
    SPRAYING_DOSE_TYPE_CHOICES = [
        ('l_per_1000l', 'L/1000L agua'),
        ('kg_per_1000l', 'kg/1000L agua'),
        ('kg_per_ha', 'kg/ha'),
        ('l_per_ha', 'L/ha'),
        ('pct', '%'),
    ]

    FERTIGATION_DOSE_TYPE_CHOICES = [
        ('l_per_ha', 'L/ha'),
        ('kg_per_ha', 'kg/ha'),
    ]

    ALL_DOSE_TYPE_CHOICES = SPRAYING_DOSE_TYPE_CHOICES + FERTIGATION_DOSE_TYPE_CHOICES

    name = models.CharField(max_length=100)
    product_type = models.ForeignKey(ProductType, on_delete=models.RESTRICT)

    # Spraying-specific dose fields
    spraying_dose = models.FloatField(null=True, blank=True)
    spraying_dose_type = models.CharField(max_length=20, choices=SPRAYING_DOSE_TYPE_CHOICES, null=True, blank=True)

    # Fertigation-specific dose fields
    fertigation_dose = models.FloatField(null=True, blank=True)
    fertigation_dose_type = models.CharField(max_length=20, choices=FERTIGATION_DOSE_TYPE_CHOICES, null=True,
                                             blank=True)

    comments = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def get_dose_for_application(self, application_type):
        if application_type == 'spraying':
            return self.spraying_dose_type
        elif application_type == 'fertigation':
            return self.fertigation_dose_type
        return None, None

    def supports_application_type(self, application_type):
        if application_type == 'spraying':
            return self.supports_spraying
        elif application_type == 'fertigation':
            return self.supports_fertigation

    @property
    def supports_spraying(self):
        return self.spraying_dose is not None and self.spraying_dose_type is not None

    @property
    def supports_fertigation(self):
        return self.fertigation_dose is not None and self.fertigation_dose_type is not None

    def __str__(self):
        return self.name

    def get_dose_type_name(self, application_type):
        dose_type = self.get_dose_type(application_type)
        return dict(self.ALL_DOSE_TYPE_CHOICES).get(dose_type)

    def get_dose_type(self, application_type):
        if application_type == 'spraying':
            return self.spraying_dose_type
        elif application_type == 'fertigation':
            return self.fertigation_dose_type

    def get_dose(self, application_type):
        if application_type == 'spraying':
            return self.spraying_dose
        elif application_type == 'fertigation':
            return self.fertigation_dose
        return None


class Treatment(OrganizationOwnedModel, SoftDeleteObject):
    TYPE_CHOICES = [
        ('spraying', 'Pulverización'),
        ('fertigation', 'Fertirrigación'),
    ]

    STATUS_PENDING = 'pending'
    STATUS_COMPLETED = 'completed'
    STATUS_DELAYED = 'delayed'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pendiente'),
        (STATUS_COMPLETED, 'Completado'),
        (STATUS_DELAYED, 'Atrasado'),
    ]

    name = models.CharField(max_length=100)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    creation_timestamp = models.DateTimeField(auto_now_add=True)
    update_timestamp = models.DateTimeField(auto_now=True)
    date = models.DateField()
    finish_date = models.DateField(null=True, blank=True)
    field = models.ForeignKey('farm.Field', on_delete=models.RESTRICT)
    machine = models.ForeignKey('farm.Machine', on_delete=models.SET_NULL, null=True, blank=True)
    products = models.ManyToManyField('farm.Product', through='TreatmentProduct')
    water_per_ha = models.IntegerField(help_text="Litros de agua por hectárea", null=True, blank=True)
    real_water_per_ha = models.IntegerField(help_text="Mojado real usado por hectárea (en litros)", null=True,
                                            blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    def __str__(self):
        return f"{self.name} - {self.date}"

    def save(self, *args, **kwargs):
        self.organization = self.field.organization  # Asignar la organización de la parcela

        # Determinamos si es un nuevo objeto o uno existente
        is_new = self.pk is None

        # Si no es nuevo, obtenemos el objeto antiguo para comparar
        if not is_new:
            old_obj = Treatment.objects.get(pk=self.pk)
            needs_recalculation = (
                    old_obj.actual_water_per_ha() != self.actual_water_per_ha() or
                    old_obj.real_water_per_ha != self.real_water_per_ha or
                    old_obj.field_id != self.field_id
            )
        else:
            needs_recalculation = True

        if self.is_fertigation():
            self.water_per_ha = self.real_water_per_ha = 0

        # Actualizamos el estado
        self.update_status()

        # Guardamos el objeto
        super().save(*args, **kwargs)

        # Solo recalculamos si es necesario
        if needs_recalculation:
            self.recalculate_product_doses()

    def recalculate_product_doses(self):
        """
        Recalcula las dosis totales de todos los productos asociados a este tratamiento.
        """
        for treatment_product in self.treatmentproduct_set.all():
            treatment_product.save()  # Esto activará el cálculo en el save() de TreatmentProduct

    def update_status(self):
        """Actualiza el campo status basado en las fechas y condiciones actuales"""
        if self.finish_date is not None:
            self.status = 'completed'
        elif self.date < datetime.now().date():
            self.status = 'delayed'
        else:
            self.status = 'pending'

    # Los métodos existentes pueden mantenerse para compatibilidad
    def is_pending(self):
        return self.status == 'pending'

    def is_completed(self):
        return self.status == 'completed'

    def is_delayed(self):
        return self.status == 'delayed'

    # métodos para mostrar en el template
    def status_display(self):
        # Devuelve el valor legible para el template
        status_map = {
            'pending': 'Pendiente',
            'completed': 'Completado',
            'delayed': 'Atrasado',
        }
        return status_map.get(self.status, 'Desconocido')

    def state_class(self):
        status_map = {
            'pending': 'warning',
            'completed': 'success',
            'delayed': 'danger',
        }
        return status_map.get(self.status, 'secondary')  # 'secondary' como fallback

    def type_class(self):
        type_map = {
            'spraying': 'spray-can-sparkles',
            'fertigation': 'droplet',
        }
        return type_map.get(self.type, 'secondary')  # 'secondary' como fallback

    def calculate_machine_loads(self):
        """
        Calcula el número de máquinas completas y parciales necesarias para el tratamiento.
        """
        if not self.machine or not self.actual_water_per_ha() or self.type != 'spraying':
            return None

        field_area = self.field.area
        water_per_ha = self.actual_water_per_ha()
        machine_capacity = self.machine.capacity

        # Total de agua necesaria
        total_water = int(round(field_area * water_per_ha, 0))

        # Número de máquinas completas
        full_loads = int(total_water // machine_capacity)

        # Información sobre carga parcial
        partial_water = int(total_water % machine_capacity)

        partial_load = partial_water > 50  # consideramos carga parcial si queda más de 50L

        return {
            'total_water': total_water,
            'full_loads': full_loads,
            'partial_load': partial_load,
            'partial_water': partial_water,
        }

    def calculate_product_for_partial_load(self, product_item):
        load_info = self.calculate_machine_loads()
        if not load_info or not load_info['partial_load']:
            return 0

        partial_water = load_info['partial_water']
        dose_type = product_item.dose_type
        dose = product_item.dose

        result = 0
        if 'ha' in dose_type:
            area_covered = partial_water / self.actual_water_per_ha()
            result = float(dose) * area_covered
        elif '1000l' in dose_type:
            result = float(dose) * partial_water / 1000
        elif '2000l' in dose_type:
            result = float(dose) * partial_water / 2000
        elif 'pct' in dose_type:
            result = float(dose) * partial_water / 100

        return round(result, 1)

    def is_fertigation(self):
        return self.type == 'fertigation'

    def is_spraying(self):
        return self.type == 'spraying'

    def actual_water_per_ha(self):
        """
        Devuelve el agua real por hectárea utilizada en el tratamiento.
        Si no se ha especificado, devuelve el valor por defecto.
        """
        return self.real_water_per_ha if self.real_water_per_ha else self.water_per_ha

    def water_per_ha_changed(self):
        return self.water_per_ha != self.actual_water_per_ha()

    def finish_treatment(self, finish_date, real_water_per_ha=None):
        """
        Finaliza el tratamiento actualizando todos los campos relacionados.
        Domain logic: aquí está toda la lógica de negocio.
        """
        self.finish_date = finish_date

        if real_water_per_ha is not None:
            self.real_water_per_ha = int(real_water_per_ha)

        self.save()


class TreatmentProduct(OrganizationOwnedModel, SoftDeleteObject):
    treatment = models.ForeignKey("Treatment", on_delete=models.CASCADE)
    product = models.ForeignKey("Product", on_delete=models.RESTRICT)
    dose = models.DecimalField(max_digits=10, decimal_places=1)
    dose_type = models.CharField(max_length=20)
    total_dose = models.DecimalField(max_digits=10, decimal_places=1)
    total_dose_unit = models.CharField(max_length=10, choices=[('L', 'Litros'), ('kg', 'Kilogramos')])

    # Nuevos campos de precio
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)  # Precio por L o kg
    total_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)  # Precio total
    price_per_ha = models.DecimalField(max_digits=10, decimal_places=2, default=0)  # Precio por hectárea

    class Meta:
        unique_together = ('treatment', 'product')  # Evita duplicados

    def __str__(self):
        return f"{self.product.name} en {self.treatment} - {self.dose}"

    def set_dose_units(self):
        # Get the appropriate dose and dose type for the treatment's application method
        treatment_type = self.treatment.type
        product_dose_type = self.product.get_dose_for_application(treatment_type)

        # Almacenar el tipo de dosis apropiado
        self.dose_type = product_dose_type

        # Determinar la unidad de medida
        if self.dose_type in ['kg_per_1000l', 'kg_per_ha']:
            self.total_dose_unit = 'kg'
        else:
            self.total_dose_unit = 'L'

    def get_dose_per_load(self):
        """
        Calcula la dosis de producto por carga de máquina, redondeada a 2 decimales.
        Si el tratamiento es de fertirrigación, devuelve la dosis completa para toda la parcela
        """
        if self.treatment.type == 'fertigation':
            # En fertirrigación, la dosis es para toda la parcela
            return self.total_dose

        machine = self.treatment.machine
        water_per_ha = self.treatment.actual_water_per_ha()

        if not machine or not water_per_ha or not self.dose or not self.dose_type:
            return None

        capacity = machine.capacity

        if 'ha' in self.dose_type:
            area_per_load = capacity / water_per_ha
            value = float(self.dose) * area_per_load
        elif '1000l' in self.dose_type:
            value = float(self.dose) * capacity / 1000
        elif '2000l' in self.dose_type:
            value = float(self.dose) * capacity / 2000
        elif 'pct' in self.dose_type:
            value = float(self.dose) * capacity / 100
        else:
            return None

        return round(value, 1)

    def save(self, *args, **kwargs):
        # Calculamos la dosis total antes de guardar
        self.set_dose_units()

        # Detectar si es una actualización o creación
        is_new = self.pk is None

        if is_new:
            # Para objetos nuevos, calcular dosis desde total
            self.calculate_dose_from_total()
        else:
            # Obtener el objeto original de la BD
            old_obj = TreatmentProduct.objects.get(pk=self.pk)

            # Detectar qué campos han cambiado
            dose_changed = old_obj.dose != self.dose
            total_dose_changed = old_obj.total_dose != self.total_dose

            # Cuando un tratamiento cambia el mojado, hay que recalcular la dosis total y de ahí los precios
            if (self.treatment.water_per_ha_changed()):
                self.calculate_total_dose()

            if dose_changed and not total_dose_changed:
                # Solo cambió la dosis, recalcular total
                self.calculate_total_dose()
            else:
                # En cualquier otro caso, recalcular dosis desde total
                self.calculate_dose_from_total()

        # Calculamos los precios finales
        self.calculate_prices()

        self.organization = self.treatment.organization

        super().save(*args, **kwargs)

    def calculate_prices(self):
        if self.unit_price == 0:
            self.unit_price = self.product.price  # Solo si aún no estaba puesto (caso creación)

        self.total_price = self.unit_price * self.total_dose
        self.price_per_ha = self.total_price / Decimal(self.treatment.field.area)

    def calculate_total_dose(self):
        """Calcula la dosis total basada en el tipo de dosis y los parámetros del tratamiento"""
        field_area = Decimal(self.treatment.field.area)
        water_per_ha = Decimal(self.treatment.actual_water_per_ha())

        if self.dose_type in ['kg_per_1000l', 'l_per_1000l']:
            total_water = water_per_ha * field_area
            result = (self.dose * total_water) / 1000
        elif self.dose_type in ['kg_per_ha', 'l_per_ha']:
            result = self.dose * field_area
        elif self.dose_type == 'pct':
            total_water = water_per_ha * field_area
            result = (self.dose / Decimal(100)) * total_water
        else:
            result = Decimal(0)

        self.total_dose = round(result, 1)

    def calculate_dose_from_total(self):
        """Calcula la dosis basada en la dosis total y los parámetros del tratamiento"""
        field_area = Decimal(self.treatment.field.area)
        water_per_ha = Decimal(self.treatment.actual_water_per_ha())

        if self.dose_type in ['kg_per_1000l', 'l_per_1000l']:
            total_water = water_per_ha * field_area
            result = (self.total_dose * 1000) / total_water
        elif self.dose_type in ['kg_per_ha', 'l_per_ha']:
            result = self.total_dose / field_area
        elif self.dose_type == 'pct':
            total_water = water_per_ha * field_area
            result = (self.total_dose * Decimal(100)) / total_water
        else:
            result = Decimal(0)

        self.dose = round(result, 1)


class Harvest(OrganizationOwnedModel):
    field = models.ForeignKey(Field, on_delete=models.RESTRICT)
    date = models.DateField()
    amount = models.FloatField()  # kg o toneladas
