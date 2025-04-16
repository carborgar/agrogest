from datetime import timedelta, date
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from farm.models import Field, Machine, ProductType, Product, Treatment, TreatmentProduct


class TreatmentTestCase(TestCase):
    def setUp(self):
        # Setup básico de los objetos necesarios para las pruebas
        self.field = Field.objects.create(name="Campo A", area=4.15, crop="Maíz", planting_year=2022)
        self.machine = Machine.objects.create(name="Pulverizadora", type="Pulverizador", capacity=2000)
        self.product_type = ProductType.objects.create(name="Fitosanitario")
        self.treatment = Treatment.objects.create(
            name="Tratamiento de prueba", type="spraying", date=timezone.now().date(),
            water_per_ha=1328, field=self.field, machine=self.machine
        )

    def test_calculate_machine_loads(self):
        """
        Campo de 4.15ha con 1328 L/ha = 5511L necesarios.
        Pulverizadora de 2000L:
            → 5511 / 2000 = 2 cargas completas
            → 5511 % 2000 = 1511L para la carga parcial
        """
        result = self.treatment.calculate_machine_loads()

        # Comprobamos que los valores calculados son los correctos
        self.assertEqual(result['total_water'], 5511)
        self.assertEqual(result['full_loads'], 2)
        self.assertTrue(result['partial_load'])
        self.assertEqual(result['partial_water'], 1511)

    def test_calculate_product_for_partial_load(self):
        """
        Producto con dosis de 2.5 L/ha.
        La carga parcial tiene 1511L de agua → 1511 / 1328 = 1.1378ha tratadas
        Dosis total para esa superficie: 2.5 * 1.1378 ≈ 2.85L
        """
        product = Product.objects.create(
            name="Producto X",
            type="pesticide",
            product_type=self.product_type,
            spraying_dose=2.5,
            spraying_dose_type='l_per_ha'
        )
        treatment_product = TreatmentProduct.objects.create(
            treatment=self.treatment,
            product=product,
            dose=Decimal('2.5'),
            dose_type='l_per_ha',
            total_dose=0,
            total_dose_unit='L'
        )
        amount = self.treatment.calculate_product_for_partial_load(treatment_product)
        self.assertEqual(amount, 2.84)

    def test_calculate_product_for_partial_load_zero_water_per_ha(self):
        """
        Test para verificar que la función maneja correctamente cuando water_per_ha es 0.
        """
        # Configuramos el tratamiento sin agua por hectárea
        self.treatment.water_per_ha = 0
        self.treatment.save()

        # Creamos un producto de prueba
        product = Product.objects.create(
            name="Producto sin agua",
            type="pesticide",
            product_type=self.product_type,
            spraying_dose=2.5,
            spraying_dose_type='l_per_ha'
        )

        # Creamos el TreatmentProduct
        tp = TreatmentProduct.objects.create(
            treatment=self.treatment,
            product=product,
            dose=Decimal(2.5),
            dose_type='l_per_ha',
            total_dose=0,
            total_dose_unit='L'
        )

        # Ejecutamos el cálculo de la dosis para la carga parcial
        result = self.treatment.calculate_product_for_partial_load(tp.product)

        # Validamos que el resultado sea cero
        self.assertEqual(result, 0)


class TreatmentProductModelTest(TestCase):
    def setUp(self):
        # Setup básico
        self.field = Field.objects.create(name="Campo A", area=10, crop="Maíz", planting_year=2022)
        self.machine = Machine.objects.create(name="Pulverizadora", type="Pulverizador", capacity=500)
        self.product_type = ProductType.objects.create(name="Fitosanitario")
        self.treatment = Treatment.objects.create(name="Tratamiento de prueba", type="spraying",
                                                  date=timezone.now().date(),
                                                  water_per_ha=850, field=self.field, machine=self.machine)

    def create_treatment_product(self, product, dose, dose_type):
        treatment_product = TreatmentProduct.objects.create(
            treatment=self.treatment,
            product=product,
            dose=dose,
            dose_type=dose_type,
            total_dose=0,
            total_dose_unit="L"
        )
        treatment_product.calculate_total_dose()
        return treatment_product

    def test_treatment_product_total_dose_calculation(self):
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

        for treatment_type, product_name, dose, dose_type, expected_dose, expected_unit in test_cases:
            # Crear el producto y el tratamiento según el tipo de aplicación
            product = Product.objects.create(
                name=product_name,
                type="pesticide",
                product_type=self.product_type,
                spraying_dose=dose,
                spraying_dose_type=dose_type,
            )

            # Crear y calcular el TreatmentProduct
            treatment_product = self.create_treatment_product(product, dose, dose_type)

            # Comprobamos la dosis total y la unidad con el método extraído
            self._assert_dose_and_unit(treatment_product, Decimal(expected_dose), expected_unit)

    def _assert_dose_and_unit(self, treatment, expected_dose, expected_unit):
        """Método para verificar la dosis total y la unidad de dosis"""
        self.assertEqual(treatment.total_dose, expected_dose)
        self.assertEqual(treatment.total_dose_unit, expected_unit)

    def test_treatment_product_dose_unit(self):
        # Setup inicial
        treatment = Treatment.objects.create(name="Test Treatment", type="spraying", date=date.today(),
                                             field=self.field,
                                             water_per_ha=10)
        product = Product.objects.create(name="Test Product", type="fertilizer", spraying_dose=5,
                                         spraying_dose_type='l_per_1000l')

        treatment_product = TreatmentProduct.objects.create(treatment=treatment, product=product, dose=5)

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
            treatment_product.calculate_total_dose()

            # Comprobamos el resultado
            self.assertEqual(treatment_product.total_dose_unit, expected_unit)

    def test_treatment_product_unique_together(self):
        with self.assertRaises(Exception):
            TreatmentProduct.objects.create(
                treatment=self.treatment, product=self.product, dose=3, dose_type="l_per_ha", total_dose=0,
                total_dose_unit="L"
            )

    def test_get_dose_per_load_all_types(self):
        test_cases = [
            {'dose': 2.5, 'dose_type': 'l_per_ha', 'expected': 1.47},  # 500 / 850 = 0.588 ha → 2.5 * 0.588 = 1.47
            {'dose': 3, 'dose_type': 'kg_per_ha', 'expected': 1.76},  # 3 * 0.588 = 1.764 → 1.76
            {'dose': 5, 'dose_type': 'l_per_1000l', 'expected': 2.5},  # 5 * 500 / 1000 = 2.5
            {'dose': 10, 'dose_type': 'kg_per_1000l', 'expected': 5.0},  # 10 * 500 / 1000 = 5.0
            {'dose': 2, 'dose_type': 'pct', 'expected': 10.0},  # 2% de 500 = 10.0
            {'dose': 2, 'dose_type': 'l_per_2000l', 'expected': 0.5},  # 2 * 500 / 2000 = 0.5
        ]

        for case in test_cases:
            with self.subTest(dose_type=case['dose_type']):
                product = Product.objects.create(
                    name=f"Producto {case['dose_type']}",
                    type="pesticide",
                    product_type=self.product_type,
                    spraying_dose=case['dose'],
                    spraying_dose_type=case['dose_type']
                )

                tp = TreatmentProduct.objects.create(
                    treatment=self.treatment,
                    product=product,
                    dose=Decimal(case['dose']),
                    dose_type=case['dose_type'],
                    total_dose=0,
                    total_dose_unit='L'
                )

                result = tp.get_dose_per_load()
                self.assertEqual(result, case['expected'])


class TreatmentStatusModelTest(TestCase):
    def setUp(self):
        # Setup básico
        self.field = Field.objects.create(name="Campo A", area=10, crop="Maíz", planting_year=2022)
        self.today = timezone.now().date()
        self.yesterday = self.today - timedelta(days=1)
        self.tomorrow = self.today + timedelta(days=1)

    def test_treatment_status_on_create(self):
        """Verifica que el estado se asigne correctamente al crear un tratamiento"""

        # Tratamiento con fecha futura debe ser pendiente
        future_treatment = Treatment.objects.create(
            name="Tratamiento futuro",
            type="spraying",
            date=self.tomorrow,
            field=self.field
        )
        self.assertEqual(future_treatment.status, 'pending')

        # Tratamiento con fecha pasada debe ser atrasado
        past_treatment = Treatment.objects.create(
            name="Tratamiento pasado",
            type="spraying",
            date=self.yesterday,
            field=self.field
        )
        self.assertEqual(past_treatment.status, 'delayed')

        # Tratamiento con fecha pasada, pero completado, debe ser completado
        completed_treatment = Treatment.objects.create(
            name="Tratamiento completado",
            type="spraying",
            date=self.yesterday,
            finish_date=self.today,
            field=self.field
        )
        self.assertEqual(completed_treatment.status, 'completed')

    def test_treatment_created_with_finish_date(self):
        """Verifica que un tratamiento creado con fecha de finalización tenga estado completado"""

        # Crear tratamiento con fecha en el pasado pero ya completado
        treatment_past = Treatment.objects.create(
            name="Tratamiento pasado completado",
            type="spraying",
            date=self.yesterday,
            finish_date=self.yesterday,  # Ya tiene fecha de finalización
            field=self.field
        )
        self.assertEqual(treatment_past.status, 'completed')

        # Crear tratamiento con fecha futura pero ya marcado como completado
        treatment_future = Treatment.objects.create(
            name="Tratamiento futuro completado",
            type="spraying",
            date=self.tomorrow,
            finish_date=self.today,  # Ya tiene fecha de finalización
            field=self.field
        )
        self.assertEqual(treatment_future.status, 'completed')

    def test_treatment_status_on_update(self):
        """Verifica que el estado se actualice correctamente al modificar un tratamiento"""

        # Crear tratamiento pendiente
        treatment = Treatment.objects.create(
            name="Tratamiento de prueba",
            type="spraying",
            date=self.tomorrow,
            field=self.field
        )
        self.assertEqual(treatment.status, 'pending')

        # Cambiar a completado
        treatment.finish_date = self.today
        treatment.save()
        self.assertEqual(treatment.status, 'completed')

        # Quitar fecha de finalización
        treatment.finish_date = None
        treatment.save()
        self.assertEqual(treatment.status, 'pending')

        # Cambiar fecha a pasada
        treatment.date = self.yesterday
        treatment.save()
        self.assertEqual(treatment.status, 'delayed')

    def test_status_consistency_with_methods(self):
        """Verifica que los métodos is_pending, is_completed, is_delayed
        sean consistentes con el campo status"""

        # Tratamiento pendiente
        pending_treatment = Treatment.objects.create(
            name="Tratamiento pendiente",
            type="spraying",
            date=self.tomorrow,
            field=self.field
        )
        self.assertTrue(pending_treatment.is_pending())
        self.assertFalse(pending_treatment.is_completed())
        self.assertFalse(pending_treatment.is_delayed())

        # Tratamiento completado
        completed_treatment = Treatment.objects.create(
            name="Tratamiento completado",
            type="spraying",
            date=self.today,
            finish_date=self.today,
            field=self.field
        )
        self.assertFalse(completed_treatment.is_pending())
        self.assertTrue(completed_treatment.is_completed())
        self.assertFalse(completed_treatment.is_delayed())

        # Tratamiento atrasado
        delayed_treatment = Treatment.objects.create(
            name="Tratamiento atrasado",
            type="spraying",
            date=self.yesterday,
            field=self.field
        )
        self.assertFalse(delayed_treatment.is_pending())
        self.assertFalse(delayed_treatment.is_completed())
        self.assertTrue(delayed_treatment.is_delayed())

    def test_treatment_status_display_and_classes(self):
        """Verifica que los métodos auxiliares para mostrar en templates
        devuelvan valores correctos"""

        # Crear tratamientos con diferentes estados
        pending_treatment = Treatment.objects.create(
            name="Tratamiento pendiente",
            type="spraying",
            date=self.tomorrow,
            field=self.field
        )

        completed_treatment = Treatment.objects.create(
            name="Tratamiento completado",
            type="spraying",
            date=self.today,
            finish_date=self.today,
            field=self.field
        )

        delayed_treatment = Treatment.objects.create(
            name="Tratamiento atrasado",
            type="spraying",
            date=self.yesterday,
            field=self.field
        )

        # Verificar display values
        self.assertEqual(pending_treatment.status_display(), 'Pendiente')
        self.assertEqual(completed_treatment.status_display(), 'Completado')
        self.assertEqual(delayed_treatment.status_display(), 'Atrasado')

        # Verificar classes para CSS
        self.assertEqual(pending_treatment.state_class(), 'warning')
        self.assertEqual(completed_treatment.state_class(), 'success')
        self.assertEqual(delayed_treatment.state_class(), 'danger')
