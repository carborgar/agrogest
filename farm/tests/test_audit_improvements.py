from datetime import date, timedelta

import pytest
from django.urls import reverse

from accounts.models import User
from farm.models import Treatment
from farm.templatetags.custom_filters import treatment_tone
from farm.tests.factories import *


def _days(n):
    return date.today() + timedelta(days=n)


@pytest.fixture
def setup(client):
    org = OrganizationFactory()
    user = User.objects.create_user(username='audit', password='pass', organization=org)
    client.force_login(user)
    field = FieldFactory(organization=org)
    machine = MachineFactory(organization=org)
    return client, org, field, machine


@pytest.mark.django_db
class TestUpcomingHorizon:

    def test_tone_uses_dates_and_15_day_horizon(self, setup):
        _, org, field, machine = setup
        mk = lambda **kw: SprayingTreatmentFactory(organization=org, field=field, machine=machine, **kw)
        assert treatment_tone(mk(date=_days(-1))) == 0
        assert treatment_tone(mk(date=_days(Treatment.UPCOMING_DAYS))) == 1
        assert treatment_tone(mk(date=_days(Treatment.UPCOMING_DAYS + 1))) == 2
        assert treatment_tone(mk(date=_days(-3), finish_date=_days(-2))) == 3

    def test_list_groups_up_to_15_days_as_upcoming(self, setup):
        client, org, field, machine = setup
        t = SprayingTreatmentFactory(organization=org, field=field, machine=machine, date=_days(12))

        response = client.get(reverse('treatment-list'), {'date_from': '', 'date_to': ''})

        assert list(response.context['treatments'])[0].urgency_group == 1
        assert 'Próximos 15 días' in response.content.decode()


@pytest.mark.django_db
class TestPrepareProducts:

    def test_new_url_and_old_one_redirects(self, setup):
        client, *_ = setup
        assert reverse('treatment-shopping-list') == '/tratamientos/preparar/'
        response = client.get('/tratamientos/lista-compra/?treatment=1')
        assert response.status_code == 301
        assert response['Location'] == '/tratamientos/preparar/?treatment=1'

    def test_page_title(self, setup):
        client, *_ = setup
        assert 'Preparar productos' in client.get(reverse('treatment-shopping-list')).content.decode()


@pytest.mark.django_db
class TestDetailActions:

    def test_finish_not_duplicated_in_actions_menu(self, setup):
        client, org, field, machine = setup
        t = SprayingTreatmentFactory(organization=org, field=field, machine=machine, date=_days(2))

        html = client.get(reverse('treatment-detail', args=[t.pk])).content.decode()

        assert 'Marcar como hecho' in html
        assert '>Finalizar</a>' not in html.replace('\n', '').replace('  ', '')
        assert 'dt-cell--desk' in html  # coste oculto en móvil mientras está pendiente
