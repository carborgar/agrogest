from datetime import datetime

from django.db import models


class Field(models.Model):
    name = models.CharField(max_length=100)
    area = models.FloatField()  # en hectáreas o m²
    crop = models.CharField(max_length=100)
    planting_year = models.IntegerField()
    location = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return self.name

    def pending_tasks_count(self):
        # Cuenta las tareas pendientes para este campo
        objs = Task.objects.filter(field=self, finish_date__isnull=True, date__gte=datetime.now().date())
        return objs.count()

    def completed_tasks_count(self):
        # Cuenta las tareas completadas para este campo
        return Task.objects.filter(field=self, finish_date__isnull=False).count()

    def delayed_tasks_count(self):
        # Cuenta las tareas atrasadas para este campo
        return Task.objects.filter(field=self, finish_date__isnull=True, date__lt=datetime.now().date()).count()


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


class Task(models.Model):
    TYPE_CHOICES = [
        ('spraying', 'Pulverización'),
        ('fertigation', 'Fertirrigación'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pendiente'),
        ('completed', 'Completada'),
        ('delayed', 'Atrasada'),
    ]

    name = models.CharField(max_length=100)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    creation_timestamp = models.DateTimeField(auto_now_add=True)
    update_timestamp = models.DateTimeField(auto_now=True)
    date = models.DateField()
    finish_date = models.DateField(null=True, blank=True)
    field = models.ForeignKey('farm.Field', on_delete=models.CASCADE)
    machine = models.ForeignKey('farm.Machine', on_delete=models.SET_NULL, null=True, blank=True)
    products = models.ManyToManyField('farm.Product', through='TaskProduct')
    water_per_ha = models.FloatField(help_text="Litros de agua por hectárea", null=True, blank=True)

    def __str__(self):
        return f"{self.name} - {self.date}"

    def is_pending(self):
        return not self.finish_date and self.date >= datetime.now().date()

    def is_completed(self):
        return self.finish_date is not None

    def is_delayed(self):
        return not self.finish_date and self.date < datetime.now().date()

    def status(self):
        if self.is_completed():
            return 'completed'
        elif self.is_delayed():
            return 'delayed'
        else:
            return 'pending'

    # métodos para mostrar en el template
    def status_display(self):
        # Devuelve el valor legible para el template
        status_map = {
            'pending': 'Pendiente',
            'completed': 'Completada',
            'delayed': 'Atrasada',
        }
        return status_map.get(self.status(), 'Desconocido')

    def state_class(self):
        status_map = {
            'pending': 'warning',
            'completed': 'success',
            'delayed': 'danger',
        }
        return status_map.get(self.status(), 'secondary')  # 'secondary' como fallback

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


class TaskProduct(models.Model):
    task = models.ForeignKey("Task", on_delete=models.CASCADE)
    product = models.ForeignKey("Product", on_delete=models.CASCADE)
    dose = models.FloatField()
    dose_type = models.CharField(max_length=20)
    total_dose = models.FloatField()
    total_dose_unit = models.CharField(max_length=10, choices=[('L', 'Litros'), ('kg', 'Kilogramos')])

    class Meta:
        unique_together = ('task', 'product')  # Evita duplicados

    def __str__(self):
        return f"{self.product.name} en {self.task} - {self.dose}"

    def calculate_total_dose(self):
        """Calcula la dosis total basada en el tipo de dosis y los parámetros de la tarea"""
        # Get the appropriate dose and dose type for the task's application method
        task_type = self.task.type
        dose_to_use, dose_type_to_use = self.product.get_dose_for_application(task_type)

        # Si no hay una dosis específica para este tipo o si se especificó una dosis personalizada
        if dose_to_use is None or self.dose is not None:
            # Use the entered dose if available
            dose_to_use = self.dose if self.dose is not None else None
            dose_type_to_use = self.dose_type if self.dose_type else None

            # Si no tenemos una dosis válida, no podemos continuar
            if dose_to_use is None or dose_type_to_use is None:
                raise ValueError(f"No se pudo determinar la dosis para {self.product.name} en tarea tipo {task_type}")

        # Almacenar el tipo de dosis apropiado
        self.dose_type = dose_type_to_use

        # Determinar la unidad de medida
        if self.dose_type in ['kg_per_1000l', 'kg_per_ha']:
            self.total_dose_unit = 'kg'
        else:
            self.total_dose_unit = 'L'

        # Obtener datos necesarios
        field_area = self.task.field.area
        water_per_ha = self.task.water_per_ha

        # Calcular la dosis total según el tipo de dosis
        if self.dose_type in ['kg_per_1000l', 'l_per_1000l']:
            total_water = water_per_ha * field_area  # Total litros
            self.total_dose = (dose_to_use * total_water) / 1000

        elif self.dose_type in ['kg_per_ha', 'l_per_ha']:
            self.total_dose = dose_to_use * field_area

        elif self.dose_type == 'pct':
            total_water = water_per_ha * field_area
            self.total_dose = (dose_to_use / 100) * total_water
            self.total_dose_unit = 'L'  # Siempre litros para porcentaje

    def save(self, *args, **kwargs):
        # Calculamos la dosis total antes de guardar
        self.calculate_total_dose()
        super().save(*args, **kwargs)


class Harvest(models.Model):
    field = models.ForeignKey(Field, on_delete=models.CASCADE)
    date = models.DateField()
    amount = models.FloatField()  # kg o toneladas
