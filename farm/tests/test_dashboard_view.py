from datetime import date, timedelta
from unittest.mock import patch

import pytest
from django.test import override_settings
from django.urls import reverse

from accounts.models import User
from farm.models import Treatment
from farm.tests.factories import *


def _days(n):
    return date.today() + timedelta(days=n)


@pytest.fixture
def setup(client):
    org = OrganizationFactory()
    user = User.objects.create_user(username='inicio', password='pass', organization=org)
    client.force_login(user)
    field = FieldFactory(organization=org)
    machine = MachineFactory(organization=org)
    return client, org, field, machine


def _spray(org, field, machine, **kwargs):
    return SprayingTreatmentFactory(organization=org, field=field, machine=machine, **kwargs)


def _get(client):
    return client.get(reverse('field_list'))


@pytest.mark.django_db
class TestDashboardGroups:

    def test_groups_totals_and_preview(self, setup):
        client, org, field, machine = setup
        for i in range(12):
            late = _spray(org, field, machine, date=_days(-1 - i))
        # Estado desfasado: sigue «pending» con fecha pasada → cuenta como atrasado
        Treatment.objects.filter(pk=late.pk).update(status='pending')
        for d in (0, 7):
            _spray(org, field, machine, date=_days(d))
        for d in (8, 12, Treatment.UPCOMING_DAYS):
            _spray(org, field, machine, date=_days(d))
        _spray(org, field, machine, date=_days(Treatment.UPCOMING_DAYS + 1))  # fuera del horizonte
        _spray(org, field, machine, date=_days(-3), finish_date=_days(-2))    # completado

        response = _get(client)
        delayed, soon, later = response.context['groups']

        assert (delayed['total'], soon['total'], later['total']) == (12, 2, 3)
        assert len(delayed['treatments']) == 10  # vista previa
        assert [c['count'] for c in response.context['chips']] == [12, 2, 5]
        # Los dos grupos de próximos son ámbar (urgency_group 1), igual que en el listado
        assert {t.urgency_group for t in soon['treatments'] + later['treatments']} == {1}
        assert {t.urgency_group for t in delayed['treatments']} == {0}
        assert 'Ver los 12' in response.content.decode()

    def test_group_links_open_the_list_with_the_same_dates(self, setup):
        client, org, field, machine = setup
        response = _get(client)
        delayed, soon, later = response.context['groups']

        assert delayed['url'].endswith('?status=delayed')
        assert f'date_from={_days(0).isoformat()}&date_to={_days(7).isoformat()}' in soon['url']
        assert f'date_from={_days(8).isoformat()}&date_to={_days(Treatment.UPCOMING_DAYS).isoformat()}' in later['url']

    def test_nothing_pending_shows_all_clear(self, setup):
        client, org, field, machine = setup
        _spray(org, field, machine, date=_days(-3), finish_date=_days(-2))

        response = _get(client)

        assert response.context['has_work'] is False
        assert 'Todo al día' in response.content.decode()

    def test_rows_have_finish_button_and_no_menu(self, setup):
        client, org, field, machine = setup
        t = _spray(org, field, machine, date=_days(-1))

        html = _get(client).content.decode()

        assert f'finishTreatment_{t.pk}' in html
        assert 'dropdown-menu' not in html.split('hm-prod-title')[0].split('hm-todo-title')[1]

    def test_other_organization_is_not_shown(self, setup):
        client, org, field, machine = setup
        other_org = OrganizationFactory(name='Otra organización')
        other_field = FieldFactory(organization=other_org)
        SprayingTreatmentFactory(organization=other_org, field=other_field,
                                 machine=MachineFactory(organization=other_org), date=_days(-1))

        response = _get(client)

        assert response.context['groups'][0]['total'] == 0


@pytest.mark.django_db
class TestDashboardProducts:

    def _with_product(self, org, field, machine, name, **kwargs):
        t = _spray(org, field, machine, **kwargs)
        # El mismo nombre es el mismo producto (la lista de compra agrupa por producto)
        product = Product.objects.filter(organization=org, name=name).first() or \
            SprayingProductFactory(organization=org, name=name)
        # La dosis total la recalcula el modelo al guardar (dosis × superficie × mojado)
        TreatmentProductFactory(treatment=t, product=product, organization=org)
        return t

    def test_only_overdue_and_next_7_days_count(self, setup):
        client, org, field, machine = setup
        late = self._with_product(org, field, machine, 'COBRE', date=_days(-2))
        soon = self._with_product(org, field, machine, 'COBRE', date=_days(5))
        self._with_product(org, field, machine, 'AZUFRE', date=_days(10))   # >7 días: no entra

        response = _get(client)

        expected = sum(tp.total_dose for t in (late, soon) for tp in t.treatmentproduct_set.all())
        assert expected > 0
        assert [(p['product_name'], p['total_dose']) for p in response.context['products']] == [('COBRE', expected)]
        assert response.context['products_total'] == 1

    def test_no_urgent_treatments_does_not_list_everything(self, setup):
        client, org, field, machine = setup
        # Solo hay un tratamiento a 10 días: get_shopping_list con una lista vacía devolvería todo
        self._with_product(org, field, machine, 'AZUFRE', date=_days(10))

        response = _get(client)

        assert response.context['products'] == []
        assert 'Nada pendiente de aplicar' in response.content.decode()

    def test_preview_is_capped_and_counts_the_rest(self, setup):
        client, org, field, machine = setup
        for i in range(8):
            self._with_product(org, field, machine, f'P{i}', date=_days(-1))

        response = _get(client)

        assert len(response.context['products']) == 6
        assert response.context['products_hidden'] == 2


@pytest.mark.django_db
class TestDashboardWeather:
    GEOMETRY = '{"type": "Polygon", "coordinates": [[[-0.4, 39.4], [-0.39, 39.4], [-0.39, 39.41], [-0.4, 39.4]]]}'

    def _show(self, client, flag=True, key='clave'):
        with patch('farm.views.dashboard_views.is_enabled', return_value=flag), \
                override_settings(AEMET_API_KEY=key):
            return _get(client)

    def test_shown_when_any_field_has_coordinates(self, setup):
        client, org, field, machine = setup
        FieldFactory(organization=org, geometry=self.GEOMETRY)  # una cualquiera, no la del tratamiento

        response = self._show(client)

        assert response.context['show_weather'] is True
        html = response.content.decode()
        assert reverse('api-weather-summary') in html
        # Esqueleto visible desde el principio, no una tarjeta oculta que aparece de golpe
        assert 'Cargando previsión' in html and 'aria-busy="true"' in html

    def test_shown_even_without_pending_treatments(self, setup):
        client, org, *_ = setup
        FieldFactory(organization=org, geometry=self.GEOMETRY)

        assert self._show(client).context['show_weather'] is True

    @pytest.mark.parametrize('flag,key,geometry', [
        (False, 'clave', True),   # módulo apagado
        (True, '', True),         # sin clave de AEMET
        (True, 'clave', False),   # ninguna parcela con geometría
    ])
    def test_hidden_when_it_cannot_work(self, setup, flag, key, geometry):
        client, org, field, machine = setup
        if geometry:
            FieldFactory(organization=org, geometry=self.GEOMETRY)

        response = self._show(client, flag=flag, key=key)

        assert response.context['show_weather'] is False
        assert 'hmWeather' not in response.content.decode()
