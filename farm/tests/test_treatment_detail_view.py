from datetime import date, timedelta

import pytest
from django.urls import reverse

from accounts.models import User
from farm.tests.factories import *


def _days(n):
    return date.today() + timedelta(days=n)


@pytest.fixture
def setup(client):
    org = OrganizationFactory()
    user = User.objects.create_user(username='detalle', password='pass', organization=org)
    client.force_login(user)
    field = FieldFactory(organization=org, area=2.2)
    return client, org, field


def _html(client, treatment):
    response = client.get(reverse('treatment-detail', args=[treatment.pk]))
    assert response.status_code == 200
    return response, response.content.decode()


@pytest.mark.django_db
class TestTreatmentDetailView:

    def test_spraying_pending_shows_prep_first_with_both_loads(self, setup):
        client, org, field = setup
        machine = MachineFactory(organization=org, capacity=2000)
        t = SprayingTreatmentFactory(organization=org, field=field, machine=machine, water_per_ha=1500, date=_days(2))
        SprayingTreatmentProductFactory(treatment=t, product=SprayingProductFactory(organization=org))

        response, html = _html(client, t)

        assert response.context['load_info']['full_loads'] == 1
        assert response.context['tone'] == 1
        assert 'Marcar como hecho' in html
        assert 'dt-label">Mojado' in html and 'dt-label">Máquina' in html
        assert 'dtLoadLast' in html  # selector Llena / Última en móvil
        assert html.index('Preparación') < html.index('Costes')

    def test_completed_shows_costs_first_and_no_finish_button(self, setup):
        client, org, field = setup
        machine = MachineFactory(organization=org, capacity=2000)
        t = SprayingTreatmentFactory(organization=org, field=field, machine=machine, water_per_ha=1500,
                                     date=_days(-3), finish_date=_days(-2))
        SprayingTreatmentProductFactory(treatment=t, product=SprayingProductFactory(organization=org))

        response, html = _html(client, t)

        assert response.context['tone'] == 3
        assert 'Marcar como hecho' not in html
        assert html.index('Costes') < html.index('Preparación')
        assert '+1 día de retraso' in html

    def test_fertigation_has_no_water_nor_loads(self, setup):
        client, org, field = setup
        t = FertigationTreatmentFactory(organization=org, field=field, date=_days(5))
        FertigationTreatmentProductFactory(treatment=t, product=FertigationProductFactory(organization=org))

        response, html = _html(client, t)

        assert response.context['load_info'] is None
        assert 'dt-label">Mojado' not in html
        assert 'dt-label">Máquina' not in html
        assert 'Cuba llena' not in html and 'dtLoad' not in html
        assert 'Fertirrigación: cantidades para toda la parcela' in html

    def test_spraying_without_machine_explains_missing_loads(self, setup):
        client, org, field = setup
        t = SprayingTreatmentFactory(organization=org, field=field, machine=None, date=_days(1))
        SprayingTreatmentProductFactory(treatment=t, product=SprayingProductFactory(organization=org))

        response, html = _html(client, t)

        assert response.context['load_info'] is None
        assert 'no se pueden calcular las cubas' in html
        assert 'Cuba llena' not in html

    def test_single_partial_load_has_no_selector(self, setup):
        client, org, field = setup
        machine = MachineFactory(organization=org, capacity=5000)  # 2,2 ha × 1000 L = 2200 L < 1 cuba
        t = SprayingTreatmentFactory(organization=org, field=field, machine=machine, water_per_ha=1000, date=_days(1))
        SprayingTreatmentProductFactory(treatment=t, product=SprayingProductFactory(organization=org))

        response, html = _html(client, t)

        assert response.context['load_info']['full_loads'] == 0
        assert 'dtLoadLast' not in html
        assert 'Una sola cuba de 2200 L' in html

    def test_products_numbered_by_position(self, setup):
        client, org, field = setup
        machine = MachineFactory(organization=org, capacity=2000)
        t = SprayingTreatmentFactory(organization=org, field=field, machine=machine, date=_days(1))
        SprayingTreatmentProductFactory(treatment=t, position=1, product=SprayingProductFactory(organization=org, name='SEGUNDO'))
        SprayingTreatmentProductFactory(treatment=t, position=0, product=SprayingProductFactory(organization=org, name='PRIMERO'))

        _, html = _html(client, t)

        assert html.index('PRIMERO') < html.index('SEGUNDO')

    def test_overdue_pending_highlights_delay_and_shows_capacity(self, setup):
        client, org, field = setup
        machine = MachineFactory(organization=org, capacity=2000, name='Atomizador viejo')
        t = SprayingTreatmentFactory(organization=org, field=field, machine=machine, water_per_ha=1500, date=_days(-3))
        SprayingTreatmentProductFactory(treatment=t, product=SprayingProductFactory(organization=org))

        _, html = _html(client, t)

        assert 'dt-badge dt-tone-0">3 días de retraso' in html
        assert 'Cuba de 2000 L' in html
        assert 'Atomizador viejo' not in html
