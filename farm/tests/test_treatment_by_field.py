"""Por parcela: últimos N tratamientos hechos de cada parcela, para comparar cómo avanzan las tandas."""
from datetime import date, timedelta

import pytest
from django.urls import reverse

from accounts.models import User
from farm.tests.factories import (
    FertigationTreatmentFactory, FieldFactory, OrganizationFactory, SprayingTreatmentFactory,
)

URL = reverse('treatment-by-field')


def _ago(n):
    return date.today() - timedelta(days=n)


@pytest.fixture
def setup(client):
    org = OrganizationFactory()
    user = User.objects.create_user(username='porparcela', password='pass', organization=org)
    client.force_login(user)
    return client, org


def _done(org, field, name, days_ago, factory=SprayingTreatmentFactory):
    return factory(organization=org, field=field, name=name, date=_ago(days_ago), finish_date=_ago(days_ago))


def _names(row):
    return [t.name for t in row['treatments']]


@pytest.mark.django_db
class TestTreatmentByField:

    def test_requires_login(self, client):
        assert client.get(URL).status_code == 302

    def test_last_n_done_per_field_newest_first(self, setup):
        client, org = setup
        cartuja = FieldFactory(organization=org, name='Cartuja')
        for i in range(7):
            _done(org, cartuja, f'T{i}', days_ago=i * 10)
        rows = client.get(URL).context['rows']
        assert _names(rows[0]) == ['T0', 'T1', 'T2', 'T3', 'T4']
        assert len(rows[0]['missing']) == 0

    def test_limit_from_query_and_invalid_falls_back(self, setup):
        client, org = setup
        field = FieldFactory(organization=org)
        for i in range(12):
            _done(org, field, f'T{i}', days_ago=i)
        assert len(client.get(URL, {'n': 10}).context['rows'][0]['treatments']) == 10
        assert len(client.get(URL, {'n': 3}).context['rows'][0]['treatments']) == 3
        for bad in ('7', 'abc', '-1', '1000'):
            ctx = client.get(URL, {'n': bad}).context
            assert ctx['limit'] == 5 and len(ctx['rows'][0]['treatments']) == 5

    def test_only_done_of_any_type(self, setup):
        client, org = setup
        field = FieldFactory(organization=org)
        _done(org, field, 'Pulverizado', 5)
        _done(org, field, 'Abonado', 2, factory=FertigationTreatmentFactory)
        SprayingTreatmentFactory(organization=org, field=field, name='Pendiente', date=_ago(1))
        SprayingTreatmentFactory(organization=org, field=field, name='Futuro', date=date.today() + timedelta(days=3))
        assert _names(client.get(URL).context['rows'][0]) == ['Abonado', 'Pulverizado']

    def test_ordered_by_finish_date_not_planned_date(self, setup):
        client, org = setup
        field = FieldFactory(organization=org)
        SprayingTreatmentFactory(organization=org, field=field, name='Previsto antes, hecho tarde',
                                 date=_ago(20), finish_date=_ago(1))
        _done(org, field, 'Hecho hace 5', 5)
        assert _names(client.get(URL).context['rows'][0]) == ['Previsto antes, hecho tarde', 'Hecho hace 5']

    def test_all_fields_listed_by_name_with_padding(self, setup):
        client, org = setup
        b = FieldFactory(organization=org, name='Borboli')
        FieldFactory(organization=org, name='Vacila')
        a = FieldFactory(organization=org, name='Atalaya')
        _done(org, a, 'Araña', 3)
        _done(org, b, 'Cobre', 4)
        _done(org, b, 'Araña', 9)
        resp = client.get(URL)
        rows = resp.context['rows']
        assert [r['field'].name for r in rows] == ['Atalaya', 'Borboli', 'Vacila']
        assert len(rows[0]['missing']) == 4 and len(rows[1]['missing']) == 3
        assert rows[2]['treatments'] == []
        assert 'Sin tratamientos hechos' in resp.content.decode()

    def test_other_organizations_are_hidden(self, setup):
        client, org = setup
        mine = FieldFactory(organization=org, name='Mía')
        _done(org, mine, 'Mío', 1)
        other_org = OrganizationFactory(name='Org Ajena')  # la factoría reutiliza por nombre
        _done(other_org, FieldFactory(organization=other_org, name='Ajena'), 'Ajeno', 1)
        resp = client.get(URL)
        assert [r['field'].name for r in resp.context['rows']] == ['Mía']
        assert 'Ajeno' not in resp.content.decode()

    def test_query_count_does_not_grow_with_fields(self, setup, django_assert_max_num_queries):
        client, org = setup
        for f in range(6):
            field = FieldFactory(organization=org)
            for i in range(6):
                _done(org, field, f'T{f}-{i}', i)
        client.get(URL)  # calienta sesión y flags
        with django_assert_max_num_queries(15):
            client.get(URL)

    def test_empty_states(self, setup):
        client, org = setup
        assert 'No hay parcelas' in client.get(URL).content.decode()
        FieldFactory(organization=org)
        assert 'Todavía no hay tratamientos hechos' in client.get(URL).content.decode()

    def test_rendered_links_and_menu(self, setup):
        client, org = setup
        field = FieldFactory(organization=org, name='Cartuja')
        t = _done(org, field, 'ARAÑA CARTUJA', 3)
        html = client.get(URL).content.decode()
        assert reverse('treatment-detail', args=[t.id]) in html
        assert f'?field={field.id}&status=completed' in html
        assert 'hace 3 d' in html
        ctx = client.get(URL).context
        active = [i['key'] for g in ctx['nav_groups'] for i in g['items'] if i['active']]
        assert active == ['nav_by_field']
