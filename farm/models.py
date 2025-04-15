from datetime import datetime
from decimal import Decimal

from django.db import models


class Field(models.Model):
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


class Machine(models.Model):
    name = models.CharField(max_length=100)
    type = models.CharField(max_length=50)  # Ej. Pulverizador
    capacity = models.IntegerField()  # Capacidad en litros

    def __str__(self):
        return f"{self.name}"


class ProductType(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name


class Product(models.Model):
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
    type = models.CharField(max_length=50, choices=[('fertilizer', 'Fertilizante'), ('pesticide', 'Fitosanitario')])
    product_type = models.ForeignKey(ProductType, on_delete=models.CASCADE, null=True)

    # Spraying-specific dose fields
    spraying_dose = models.FloatField(null=True, blank=True)
    spraying_dose_type = models.CharField(max_length=20, choices=SPRAYING_DOSE_TYPE_CHOICES, null=True, blank=True)

    # Fertigation-specific dose fields
    fertigation_dose = models.FloatField(null=True, blank=True)
    fertigation_dose_type = models.CharField(max_length=20, choices=FERTIGATION_DOSE_TYPE_CHOICES, null=True,
                                             blank=True)

    comments = models.TextField(blank=True)

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


class Treatment(models.Model):
    TYPE_CHOICES = [
        ('spraying', 'Pulverización'),
        ('fertigation', 'Fertirrigación'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pendiente'),
        ('completed', 'Completado'),
        ('delayed', 'Atrasado'),
    ]

    name = models.CharField(max_length=100)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    creation_timestamp = models.DateTimeField(auto_now_add=True)
    update_timestamp = models.DateTimeField(auto_now=True)
    date = models.DateField()
    finish_date = models.DateField(null=True, blank=True)
    field = models.ForeignKey('farm.Field', on_delete=models.CASCADE)
    machine = models.ForeignKey('farm.Machine', on_delete=models.SET_NULL, null=True, blank=True)
    products = models.ManyToManyField('farm.Product', through='TreatmentProduct')
    water_per_ha = models.IntegerField(help_text="Litros de agua por hectárea", null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    def __str__(self):
        return f"{self.name} - {self.date}"

    def save(self, *args, **kwargs):
        # Calcular status antes de guardar
        self.update_status()
        super().save(*args, **kwargs)

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

    def get_water_per_ha(self):
        if self.type == 'fertigation':
            return 0
        return self.water_per_ha


class TreatmentProduct(models.Model):
    treatment = models.ForeignKey("Treatment", on_delete=models.CASCADE)
    product = models.ForeignKey("Product", on_delete=models.CASCADE)
    dose = models.DecimalField(max_digits=10, decimal_places=2)
    dose_type = models.CharField(max_length=20)
    total_dose = models.DecimalField(max_digits=10, decimal_places=2)
    total_dose_unit = models.CharField(max_length=10, choices=[('L', 'Litros'), ('kg', 'Kilogramos')])

    class Meta:
        unique_together = ('treatment', 'product')  # Evita duplicados

    def __str__(self):
        return f"{self.product.name} en {self.treatment} - {self.dose}"

    def calculate_total_dose(self):
        """Calcula la dosis total basada en el tipo de dosis y los parámetros del tratamiento"""
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

        # Obtener datos necesarios
        field_area = self.treatment.field.area
        water_per_ha = self.treatment.water_per_ha

        # Calcular la dosis total según el tipo de dosis
        if self.dose_type in ['kg_per_1000l', 'l_per_1000l']:
            total_water = water_per_ha * field_area  # Total litros
            self.total_dose = (self.dose * Decimal(total_water)) / 1000

        elif self.dose_type in ['kg_per_ha', 'l_per_ha']:
            self.total_dose = self.dose * Decimal(field_area)

        elif self.dose_type == 'pct':
            total_water = water_per_ha * field_area
            self.total_dose = (self.dose / Decimal(100)) * total_water
            self.total_dose_unit = 'L'  # Siempre litros para porcentaje

    def save(self, *args, **kwargs):
        # Calculamos la dosis total antes de guardar
        self.calculate_total_dose()
        super().save(*args, **kwargs)


class Harvest(models.Model):
    field = models.ForeignKey(Field, on_delete=models.CASCADE)
    date = models.DateField()
    amount = models.FloatField()  # kg o toneladas
