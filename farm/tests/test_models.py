from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from farm.models import Field, Machine, ProductType, Product, Task, TaskProduct


class TaskProductModelTest(TestCase):
    def setUp(self):
        # Setup básico
        self.field = Field.objects.create(name="Campo A", area=10, crop="Maíz", planting_year=2022)
        self.machine = Machine.objects.create(name="Pulverizadora", type="Pulverizador", capacity=500)
        self.product_type = ProductType.objects.create(name="Fitosanitario")
        self.task = Task.objects.create(name="Tarea de prueba", type="spraying", date=timezone.now().date(),
                                        water_per_ha=850, field=self.field)

    def create_task_product(self, product, dose, dose_type):
        task_product = TaskProduct.objects.create(
            task=self.task,
            product=product,
            dose=dose,
            dose_type=dose_type,
            total_dose=0,
            total_dose_unit="L"
        )
        task_product.calculate_total_dose()
        return task_product

    def test_task_product_total_dose_calculation(self):
        """
        Verifica que la dosis total (total_dose) se calcule correctamente para cada tipo de dosis.
        """
        # Combinaciones de prueba con tipo de dosis, nombre del producto, dosis, y unidades esperadas
        test_cases = [
            # L/ha (Litros por hectárea)
            ("spraying", "Producto L/ha", 2, "l_per_ha", 20, 'L'),
            # kg/ha (Kilogramos por hectárea)
            ("spraying", "Producto Kg/ha", 3, "kg_per_ha", 30, 'kg'),
            # l/1000l (Litros por 1000 litros de agua)
            ("spraying", "Producto L/1000L", 5, "l_per_1000l", 42.5, 'L'),
            # kg/1000l (Kilogramos por 1000 litros de agua)
            ("spraying", "Producto Kg/1000L", 2, "kg_per_1000l", 17, 'kg'),
            # pct (Porcentaje)
            ("spraying", "Producto Porcentaje", 10, "pct", 850, 'L'),
        ]

        for task_type, product_name, dose, dose_type, expected_dose, expected_unit in test_cases:
            # Crear el producto y la tarea según el tipo de aplicación
            product = Product.objects.create(
                name=product_name,
                type="pesticide",
                product_type=self.product_type,
                spraying_dose=dose,
                spraying_dose_type=dose_type,
            )

            # Crear y calcular el TaskProduct
            task_product = self.create_task_product(product, dose, dose_type)

            # Comprobamos la dosis total y la unidad con el método extraído
            self._assert_dose_and_unit(task_product, Decimal(expected_dose), expected_unit)

    def _assert_dose_and_unit(self, task_product, expected_dose, expected_unit):
        """Método para verificar la dosis total y la unidad de dosis"""
        self.assertEqual(task_product.total_dose, expected_dose)
        self.assertEqual(task_product.total_dose_unit, expected_unit)

    def test_task_product_dose_unit(self):
        # Setup inicial
        task = Task.objects.create(name="Test Task", type="spraying", date="2025-04-04", field=self.field,
                                   water_per_ha=10)
        product = Product.objects.create(name="Test Product", type="fertilizer", spraying_dose=5,
                                         spraying_dose_type='l_per_1000l')

        task_product = TaskProduct.objects.create(task=task, product=product, dose=5)

        # Lista de dosis y sus unidades esperadas
        dose_data = [
            ('l_per_1000l', 'L'),
            ('kg_per_1000l', 'kg'),
            ('kg_per_ha', 'kg'),
            ('l_per_ha', 'L'),
            ('pct', 'L'),
        ]

        # Bucle para comprobar cada tipo de dosis
        for dose_type, expected_unit in dose_data:
            # Establecemos el tipo de dosis
            product.spraying_dose_type = dose_type
            product.save()

            # Calculamos la dosis total
            task_product.calculate_total_dose()

            # Comprobamos el resultado
            self.assertEqual(task_product.total_dose_unit, expected_unit)

    def test_task_product_unique_together(self):
        with self.assertRaises(Exception):
            TaskProduct.objects.create(
                task=self.task, product=self.product, dose=3, dose_type="l_per_ha", total_dose=0, total_dose_unit="L"
            )
