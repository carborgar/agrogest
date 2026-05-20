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
class ShoppingListViewTest(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="Org Shopping List")
        self.user = User.objects.create_user(
            username="shopping-user",
            email="shopping@example.com",
            password="pass123",
            organization=self.organization,
        )
        self.client.force_login(self.user)

        self.field = Field.objects.create(
            name="Parcela Shopping",
            area=2,
            crop="Olivo",
            planting_year=2020,
            organization=self.organization,
        )
        self.machine = Machine.objects.create(
            name="Pulverizador Shopping",
            type="Pulverizador",
            capacity=1000,
            organization=self.organization,
        )
        product_type = ProductType.objects.create(
            name="Fitosanitario",
            organization=self.organization,
        )

        self.treatment = Treatment.objects.create(
            name="Tratamiento compra",
            type="spraying",
            date=date.today() + timedelta(days=1),
            field=self.field,
            machine=self.machine,
            water_per_ha=1000,
            organization=self.organization,
        )

        product_1 = Product.objects.create(
            name="Producto 1",
            product_type=product_type,
            spraying_dose=Decimal("1.00"),
            spraying_dose_type="l_per_ha",
            price=Decimal("10.00"),
            organization=self.organization,
        )
        product_2 = Product.objects.create(
            name="Producto 2",
            product_type=product_type,
            spraying_dose=Decimal("1.00"),
            spraying_dose_type="l_per_ha",
            price=Decimal("7.50"),
            organization=self.organization,
        )

        TreatmentProduct.objects.create(
            treatment=self.treatment,
            product=product_1,
            dose=Decimal("1.00"),
            total_dose=Decimal("2.00"),
            dose_type="l_per_ha",
            total_dose_unit="L",
            unit_price=Decimal("10.00"),
            organization=self.organization,
        )
        TreatmentProduct.objects.create(
            treatment=self.treatment,
            product=product_2,
            dose=Decimal("1.00"),
            total_dose=Decimal("2.00"),
            dose_type="l_per_ha",
            total_dose_unit="L",
            unit_price=Decimal("7.50"),
            organization=self.organization,
        )

    def test_shopping_list_shows_total_euros_per_product(self):
        response = self.client.get(
            reverse("treatment-shopping-list"),
            {"treatment": [str(self.treatment.pk)]},
        )

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertRegex(content, r"20[,.]00€")
        self.assertRegex(content, r"15[,.]00€")
