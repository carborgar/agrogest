from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from accounts.models import Organization, User
from farm.models import Field, Product, ProductPriceHistory, ProductType, Treatment, TreatmentProduct


@pytest.mark.django_db
def test_range_recalculation_executes_with_valid_dates(client):
    organization = Organization.objects.create(name='Org Admin Recalc')
    user = User.objects.create_user(username='admin-recalc', password='pass', organization=organization)
    client.force_login(user)

    field = Field.objects.create(
        organization=organization,
        name='Parcela 1',
        area=4.0,
        crop='Olivo',
        planting_year=2020,
    )
    product_type = ProductType.objects.create(name='Herbicida', organization=organization)
    product = Product.objects.create(
        organization=organization,
        name='Producto A',
        product_type=product_type,
        price=Decimal('20.00'),
        spraying_dose=Decimal('2.0'),
        spraying_dose_type='l_per_1000l',
    )

    ProductPriceHistory.objects.create(
        organization=organization,
        product=product,
        price=Decimal('33.00'),
        effective_date=date.today(),
    )

    treatment = Treatment.objects.create(
        organization=organization,
        name='Tratamiento 1',
        type='spraying',
        date=date.today(),
        field=field,
        water_per_ha=400,
    )

    treatment_product = TreatmentProduct.objects.create(
        organization=organization,
        treatment=treatment,
        product=product,
        dose=Decimal('2.0'),
        dose_type='l_per_1000l',
        total_dose=Decimal('3.2'),
        total_dose_unit='L',
        unit_price=Decimal('10.00'),
    )

    url = reverse('treatment-cost-admin')
    response = client.post(
        url,
        {
            'action': 'execute_range',
            'start_date': date.today().isoformat(),
            'end_date': date.today().isoformat(),
        },
    )

    assert response.status_code == 302
    treatment_product.refresh_from_db()
    assert treatment_product.unit_price == Decimal('33.00')


@pytest.mark.django_db
def test_product_recalculation_updates_matching_treatments(client):
    organization = Organization.objects.create(name='Org Product Recalc')
    user = User.objects.create_user(username='product-recalc', password='pass', organization=organization)
    client.force_login(user)

    field = Field.objects.create(
        organization=organization,
        name='Parcela 2',
        area=5.0,
        crop='Almendro',
        planting_year=2021,
    )
    product_type = ProductType.objects.create(name='Fungicida', organization=organization)
    product = Product.objects.create(
        organization=organization,
        name='Producto B',
        product_type=product_type,
        price=Decimal('15.00'),
        spraying_dose=Decimal('1.0'),
        spraying_dose_type='l_per_ha',
    )

    ProductPriceHistory.objects.create(
        organization=organization,
        product=product,
        price=Decimal('25.00'),
        effective_date=date.today(),
    )

    treatment = Treatment.objects.create(
        organization=organization,
        name='Tratamiento 2',
        type='spraying',
        date=date.today(),
        field=field,
        water_per_ha=350,
    )

    treatment_product = TreatmentProduct.objects.create(
        organization=organization,
        treatment=treatment,
        product=product,
        dose=Decimal('1.0'),
        dose_type='l_per_ha',
        total_dose=Decimal('5.0'),
        total_dose_unit='L',
        unit_price=Decimal('11.00'),
    )

    url = reverse('treatment-cost-admin')
    response = client.post(
        url,
        {
            'action': 'execute_product',
            'product': str(product.id),
        },
    )

    assert response.status_code == 302
    treatment_product.refresh_from_db()
    assert treatment_product.unit_price == Decimal('25.00')


@pytest.mark.django_db
def test_preview_range_does_not_validate_product_form(client):
    organization = Organization.objects.create(name='Org Form Isolation')
    user = User.objects.create_user(username='form-isolation', password='pass', organization=organization)
    client.force_login(user)

    url = reverse('treatment-cost-admin')
    response = client.post(
        url,
        {
            'action': 'preview_range',
            'start_date': date.today().isoformat(),
            'end_date': date.today().isoformat(),
        },
        follow=True,
    )

    assert response.status_code == 200
    assert response.redirect_chain
    assert 'preview=range' in response.request['QUERY_STRING']
    assert response.context['range_form'].is_bound is True
    assert response.context['product_form'].is_bound is False
    assert response.context['product_form'].errors == {}


