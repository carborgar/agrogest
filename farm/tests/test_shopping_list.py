from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse

from accounts.models import User
from farm.models import StoragePoint, Treatment
from farm.tests.factories import *


def _days(n):
    return date.today() + timedelta(days=n)


@pytest.fixture
def setup(client):
    org = OrganizationFactory()
    user = User.objects.create_user(username='preparar', password='pass', organization=org)
    client.force_login(user)
    field = FieldFactory(organization=org, name='Vegueta', area=2.5)
    machine = MachineFactory(organization=org)
    return client, org, field, machine


def _spray(org, field, machine, **kwargs):
    return SprayingTreatmentFactory(organization=org, field=field, machine=machine, **kwargs)


def _get(client, params=None):
    return client.get(reverse('treatment-shopping-list'), params or {})


def _checked(response):
    return {t.id for g in response.context['groups'] for t in g['treatments'] if t.checked}


@pytest.mark.django_db
class TestPrepareSelection:

    def test_groups_by_dates_and_preselects_overdue_and_next_7_days(self, setup):
        client, org, field, machine = setup
        late = _spray(org, field, machine, date=_days(-3))
        # Estado desfasado: sigue «pending» con fecha pasada → atrasado
        Treatment.objects.filter(pk=late.pk).update(status='pending')
        soon = _spray(org, field, machine, date=_days(7))
        mid = _spray(org, field, machine, date=_days(8))
        later = _spray(org, field, machine, date=_days(Treatment.UPCOMING_DAYS + 1))
        _spray(org, field, machine, date=_days(-5), finish_date=_days(-4))  # completado: no sale

        response = _get(client)
        groups = {g['index']: [t.id for t in g['treatments']] for g in response.context['groups']}

        assert groups == {0: [late.id], 1: [soon.id], 2: [mid.id], 3: [later.id]}
        assert _checked(response) == {late.id, soon.id}
        assert response.context['total_count'] == 4

    def test_selection_from_the_url_replaces_the_default(self, setup):
        client, org, field, machine = setup
        late = _spray(org, field, machine, date=_days(-3))
        mid = _spray(org, field, machine, date=_days(10))

        assert _checked(_get(client, {'treatment': [str(mid.id)]})) == {mid.id}
        # `treatment=` vacío: el usuario lo desmarcó todo y se respeta al recargar
        assert _checked(_get(client, {'treatment': ''})) == set()
        assert late.id not in _checked(_get(client, {'treatment': ['x', str(mid.id)]}))

    def test_other_organization_is_not_shown(self, setup):
        client, org, field, machine = setup
        other = OrganizationFactory(name='Otra')
        SprayingTreatmentFactory(organization=other, field=FieldFactory(organization=other),
                                 machine=MachineFactory(organization=other), date=_days(-1))

        response = _get(client)

        assert response.context['total_count'] == 0
        assert 'No hay tratamientos pendientes' in response.content.decode()


@pytest.mark.django_db
class TestPrepareData:

    def test_lines_carry_totals_cost_and_storage_point(self, setup):
        client, org, field, machine = setup
        field.storage_point = StoragePoint.objects.create(name='Injeros', organization=org)
        field.save()
        t = _spray(org, field, machine, date=_days(-1))
        tp = TreatmentProductFactory(treatment=t, organization=org,
                                     product=SprayingProductFactory(organization=org, name='COBRE'))
        tp.refresh_from_db()

        data = _get(client).context['pp_data']

        assert data == [{
            'id': t.id,
            'field': {'id': field.id, 'name': 'Vegueta', 'ha': 2.5, 'sp': field.storage_point_id, 'spName': 'Injeros'},
            'lines': [{'p': tp.product_id, 'n': 'COBRE', 'u': tp.total_dose_unit,
                       'q': float(tp.total_dose), 'c': float(tp.total_price)}],
        }]

    def test_field_without_storage_point_is_its_own_place(self, setup):
        client, org, field, machine = setup
        _spray(org, field, machine, date=_days(-1))

        data = _get(client).context['pp_data']

        assert data[0]['field']['sp'] is None and data[0]['field']['spName'] is None

    def test_page_embeds_the_data_and_has_no_calculate_button(self, setup):
        client, org, field, machine = setup
        _spray(org, field, machine, date=_days(-1))

        html = _get(client).content.decode()

        assert 'id="pp-data"' in html
        assert 'Calcular' not in html
        assert 'Por casetilla' in html and 'Por producto' in html
