import pytest
from django.urls import reverse
from decimal import Decimal

from farm.models import Harvest, Field
from accounts.models import Organization, User


@pytest.mark.django_db
def test_create_harvest_with_null_price(client):
    org = Organization.objects.create(name='Org')
    user = User.objects.create_user(username='test', password='pass', organization=org)
    client.force_login(user)

    field = Field.objects.create(name='F1', area=2.5, crop='naranjas', planting_year=2020, organization=org)

    url = reverse('harvest-create')
    data = {
        'field': field.id,
        'date': '2025-01-01',
        'amount': '1200',
        'area_ha': '2.5',
        'price_pending': 'on',
        'notes': 'Test'
    }

    resp = client.post(url, data, follow=True)
    assert resp.status_code == 200

    h = Harvest.objects.get(field=field)
    assert h.sale_price_per_kg is None
    assert h.price_pending is True
    assert h.yield_kg_per_ha == Decimal(str(1200)) / Decimal(str(2.5))


@pytest.mark.django_db
def test_summary_calculates_totals(client):
    org = Organization.objects.create(name='Org2')
    user = User.objects.create_user(username='test2', password='pass', organization=org)
    client.force_login(user)

    field = Field.objects.create(name='F2', area=1.0, crop='mandarinas', planting_year=2021, organization=org)

    # create 2 harvests with price and one without
    h1 = Harvest.objects.create(field=field, date='2025-02-01', amount=1000, area_ha=1.0, sale_price_per_kg=Decimal('0.5'), price_pending=False, organization=org)
    h2 = Harvest.objects.create(field=field, date='2025-02-02', amount=1500, area_ha=1.0, sale_price_per_kg=Decimal('0.6'), price_pending=False, organization=org)
    h3 = Harvest.objects.create(field=field, date='2025-02-03', amount=500, area_ha=1.0, sale_price_per_kg=None, price_pending=True, organization=org)

    url = reverse('harvest-summary')
    resp = client.get(url)
    assert resp.status_code == 200

    # context variables are available in template context
    assert resp.context['total_kg'] == 3000
    assert resp.context['total_ha'] == Decimal('3.0')
    assert resp.context['income'] == Decimal('1000')*Decimal('0.5') + Decimal('1500')*Decimal('0.6')

