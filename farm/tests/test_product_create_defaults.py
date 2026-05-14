import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import Organization
from farm.models import Product, ProductType

User = get_user_model()


@pytest.mark.django_db
class ProductCreateDefaultsTest(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="Org test")
        self.user = User.objects.create_user(
            username="product-user",
            password="testpass123",
            organization=self.organization,
        )
        self.product_type = ProductType.objects.create(
            name="Herbicida",
            organization=self.organization,
        )
        self.client.force_login(self.user)

    def test_new_product_is_active_when_is_active_missing_in_post(self):
        response = self.client.post(
            reverse('product-create'),
            {
                'name': 'Producto nuevo',
                'product_type': self.product_type.id,
                'price': '12.50',
                'comments': '',
                # Simula el formulario actual: no envía is_active en creación
                'spraying_dose': '2.0',
                'spraying_dose_type': 'l_per_1000l',
                'fertigation_dose': '',
                'fertigation_dose_type': '',
            },
        )

        self.assertEqual(response.status_code, 302)

        created = Product.objects.get(name='Producto nuevo')
        self.assertTrue(created.is_active)

