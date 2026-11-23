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

    def test_query_count_does_not_grow_with_fields(self, setup):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        client, org = setup

        def count():
            client.get(URL)  # calienta sesión y caché de flags
            with CaptureQueriesContext(connection) as ctx:
                client.get(URL)
            return len(ctx)

        def add_field(f):
            field = FieldFactory(organization=org)
            for i in range(6):
                _done(org, field, f'T{f}-{i}', i)

        add_field(0)
        one = count()
        for f in range(1, 6):
            add_field(f)
        assert count() == one

    def test_ties_on_finish_date_break_by_planned_date_then_id(self, setup):
        client, org = setup
        field = FieldFactory(organization=org)
        hoy = _ago(2)
        SprayingTreatmentFactory(organization=org, field=field, name='Previsto antes', date=_ago(9), finish_date=hoy)
        SprayingTreatmentFactory(organization=org, field=field, name='Creado antes', date=_ago(3), finish_date=hoy)
        SprayingTreatmentFactory(organization=org, field=field, name='Creado después', date=_ago(3), finish_date=hoy)
        assert _names(client.get(URL).context['rows'][0]) == ['Creado después', 'Creado antes', 'Previsto antes']

    def test_user_without_organization_sees_nothing(self, client):
        org = OrganizationFactory()
        _done(org, FieldFactory(organization=org), 'Ajeno', 1)
        user = User.objects.create_user(username='sinorg', password='pass')
        client.force_login(user)
        resp = client.get(URL)
        assert resp.status_code == 200 and resp.context['rows'] == []

    def test_empty_states(self, setup):
        client, org = setup
        assert 'No hay parcelas' in client.get(URL).content.decode()
        FieldFactory(organization=org)
        assert 'Todavía no hay tratamientos hechos' in client.get(URL).content.decode()

    def test_rendered_links_and_menu(self, setup):
        client, org = setup
        field = FieldFactory(organization=org, name='Cartuja')
        t = _done(org, field, 'ARAÑA CARTUJA', 3)
        resp = client.get(URL)
        html = resp.content.decode()
        assert reverse('treatment-detail', args=[t.id]) in html
        # Sin rango de fechas: el listado no se limita al año en curso
        assert f'?field={field.id}&status=completed&date_from=&date_to=' in html
        assert 'hace 3 d' in html
        active = [i['key'] for g in resp.context['nav_groups'] for i in g['items'] if i['active']]
        assert active == ['nav_by_field']


@pytest.mark.django_db
class TestTreatmentByFieldFilters:

    def _setup(self, org):
        from farm.tests.factories import ProductTypeFactory, SprayingProductFactory, SprayingTreatmentProductFactory
        acaricida = ProductTypeFactory(organization=org, name='Acaricida')
        cobre_t = ProductTypeFactory(organization=org, name='Fungicida')
        flash = SprayingProductFactory(organization=org, name='FLASH', product_type=acaricida)
        cupro = SprayingProductFactory(organization=org, name='CUPROCOL', product_type=cobre_t)
        a = FieldFactory(organization=org, name='Atalaya')
        b = FieldFactory(organization=org, name='Borboli')
        for field, name, ago, prod in [(a, 'ARAÑA', 40, flash), (a, 'COBRE', 10, cupro),
                                       (b, 'COBRE', 12, cupro), (b, 'ARAÑA', 300, flash)]:
            t = _done(org, field, name, ago)
            SprayingTreatmentProductFactory(treatment=t, product=prod)
        _done(org, a, 'Abonado', 2, factory=FertigationTreatmentFactory)
        return a, b, acaricida, flash

    def test_product_type_filter_keeps_fields_without_matches(self, setup):
        client, org = setup
        a, b, acaricida, _ = self._setup(org)
        rows = client.get(URL, {'product_types': acaricida.id}).context['rows']
        assert [_names(r) for r in rows] == [['ARAÑA'], ['ARAÑA']]

    def test_product_filter(self, setup):
        client, org = setup
        _, _, _, flash = self._setup(org)
        rows = client.get(URL, {'products': flash.id}).context['rows']
        assert [_names(r) for r in rows] == [['ARAÑA'], ['ARAÑA']]

    def test_type_filter(self, setup):
        client, org = setup
        self._setup(org)
        rows = client.get(URL, {'type': 'fertigation'}).context['rows']
        assert [_names(r) for r in rows] == [['Abonado'], []]
        assert 'Ninguno con estos filtros' in client.get(URL, {'type': 'fertigation'}).content.decode()

    def test_field_filter_limits_rows(self, setup):
        client, org = setup
        a, b, _, _ = self._setup(org)
        rows = client.get(URL, {'field': b.id}).context['rows']
        assert [r['field'].name for r in rows] == ['Borboli']

    def test_period_on_finish_date_and_last_n_inside(self, setup):
        client, org = setup
        self._setup(org)
        ctx = client.get(URL, {'date_from': _ago(50).isoformat(), 'date_to': _ago(5).isoformat(), 'n': 3}).context
        assert [_names(r) for r in ctx['rows']] == [['COBRE', 'ARAÑA'], ['COBRE']]
        assert ctx['panel_filter_count'] == 1

    def test_invalid_params_are_ignored(self, setup):
        client, org = setup
        self._setup(org)
        resp = client.get(URL, {'date_from': 'ayer', 'field': 'x', 'type': 'otro', 'products': '-1'})
        assert resp.status_code == 200 and resp.context['panel_filter_count'] == 0

    def test_limit_links_keep_filters(self, setup):
        client, org = setup
        _, _, acaricida, _ = self._setup(org)
        html = client.get(URL, {'product_types': acaricida.id, 'n': 3}).content.decode()
        assert f'?n=10&product_types={acaricida.id}"' in html

    def test_similar_treatments_share_color(self, setup):
        client, org = setup
        self._setup(org)
        ctx = client.get(URL).context
        colors = {t.name: t.similar_color for r in ctx['rows'] for t in r['treatments']}
        cobres = [t.similar_color for r in ctx['rows'] for t in r['treatments'] if t.name == 'COBRE']
        assert cobres[0] is not None and cobres[0] == cobres[1]
        assert colors['Abonado'] is None
        assert {g['label'] for g in ctx['groups']} >= {'COBRE'}
