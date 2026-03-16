from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import Organization
from farm.models import Field, Machine, ProductType, Product, Treatment, TreatmentProduct

User = get_user_model()


@pytest.mark.django_db
class TreatmentEditViewTest(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="Org Edit Test")
        self.user = User.objects.create_user(
            username="editor",
            email="editor@example.com",
            password="pass123",
            organization=self.organization,
        )
        self.client.force_login(self.user)

        self.field = Field.objects.create(
            name="Parcela A",
            area=10.0,
            crop="Olivo",
            planting_year=2020,
            organization=self.organization,
        )
        self.machine = Machine.objects.create(
            name="Pulverizador 1000",
            type="Pulverizador",
            capacity=1000,
            organization=self.organization,
        )
        self.product_type = ProductType.objects.create(
            name="Fitosanitario",
            organization=self.organization,
        )

        self.product_1 = Product.objects.create(
            name="Producto 1",
            product_type=self.product_type,
            spraying_dose=Decimal("1.00"),
            spraying_dose_type="l_per_ha",
            price=Decimal("20.00"),
            organization=self.organization,
        )
        self.product_2 = Product.objects.create(
            name="Producto 2",
            product_type=self.product_type,
            spraying_dose=Decimal("1.00"),
            spraying_dose_type="l_per_ha",
            price=Decimal("30.00"),
            organization=self.organization,
        )
        self.product_3 = Product.objects.create(
            name="Producto 3",
            product_type=self.product_type,
            spraying_dose=Decimal("1.00"),
            spraying_dose_type="l_per_ha",
            price=Decimal("15.00"),
            organization=self.organization,
        )

        self.treatment = Treatment.objects.create(
            name="Tratamiento base",
            type="spraying",
            date=date.today() + timedelta(days=1),
            field=self.field,
            machine=self.machine,
            water_per_ha=1000,
            organization=self.organization,
        )

        self.tp_1 = TreatmentProduct.objects.create(
            treatment=self.treatment,
            product=self.product_1,
            dose=Decimal("2.00"),
            total_dose=Decimal("20.00"),
            dose_type="l_per_ha",
            total_dose_unit="L",
            unit_price=Decimal("20.00"),
            organization=self.organization,
        )
        self.tp_2 = TreatmentProduct.objects.create(
            treatment=self.treatment,
            product=self.product_2,
            dose=Decimal("1.00"),
            total_dose=Decimal("10.00"),
            dose_type="l_per_ha",
            total_dose_unit="L",
            unit_price=Decimal("30.00"),
            organization=self.organization,
        )

    def test_edit_page_is_available(self):
        response = self.client.get(reverse("treatment-edit", kwargs={"pk": self.treatment.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Editar tratamiento")
        self.assertContains(response, "Producto 1")
        self.assertContains(response, f'value="{self.treatment.date.isoformat()}"', html=False)
        self.assertContains(response, 'value="20.00"', html=False)
        self.assertContains(response, 'value="10.00"', html=False)

    def test_edit_treatment_updates_name_and_products(self):
        response = self.client.post(
            reverse("treatment-edit", kwargs={"pk": self.treatment.pk}),
            {
                "name": "Tratamiento editado",
                "type": "spraying",
                "date": self.treatment.date.isoformat(),
                "field": str(self.field.pk),
                "machine": str(self.machine.pk),
                "water_per_ha": "1000",
                "finish_date": "",
                "treatmentproduct_set-TOTAL_FORMS": "3",
                "treatmentproduct_set-INITIAL_FORMS": "2",
                "treatmentproduct_set-MIN_NUM_FORMS": "1",
                "treatmentproduct_set-MAX_NUM_FORMS": "1000",
                "treatmentproduct_set-0-id": str(self.tp_1.pk),
                "treatmentproduct_set-0-product": str(self.product_1.pk),
                "treatmentproduct_set-0-dose": "3.00",
                "treatmentproduct_set-0-total_dose": "30.00",
                "treatmentproduct_set-0-DELETE": "",
                "treatmentproduct_set-1-id": str(self.tp_2.pk),
                "treatmentproduct_set-1-product": str(self.product_2.pk),
                "treatmentproduct_set-1-dose": "1.00",
                "treatmentproduct_set-1-total_dose": "10.00",
                "treatmentproduct_set-1-DELETE": "on",
                "treatmentproduct_set-2-id": "",
                "treatmentproduct_set-2-product": str(self.product_3.pk),
                "treatmentproduct_set-2-dose": "0.50",
                "treatmentproduct_set-2-total_dose": "5.00",
                "treatmentproduct_set-2-DELETE": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("treatment-detail", kwargs={"pk": self.treatment.pk}))

        self.treatment.refresh_from_db()
        self.assertEqual(self.treatment.name, "Tratamiento editado")

        current_products = set(
            TreatmentProduct.objects.filter(treatment=self.treatment).values_list("product_id", flat=True)
        )
        self.assertEqual(current_products, {self.product_1.pk, self.product_3.pk})

        updated_tp_1 = TreatmentProduct.objects.get(treatment=self.treatment, product=self.product_1)
        self.assertEqual(updated_tp_1.dose, Decimal("3.00"))

