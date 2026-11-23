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
        assert active == ['nav_treatments']


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
        resp = client.get(URL)
        groups = {t.name: t.similar for r in resp.context['rows'] for t in r['treatments']}
        cobres = [t.similar for r in resp.context['rows'] for t in r['treatments'] if t.name == 'COBRE']
        assert cobres[0] is not None and cobres[0] is cobres[1]
        assert groups['Abonado'] is None
        assert 'parecido a «COBRE»' in resp.content.decode()

    def test_unparseable_or_foreign_ids_are_ignored(self, setup):
        client, org = setup
        self._setup(org)
        other = OrganizationFactory(name='Org Ajena')
        foreign = FieldFactory(organization=other)
        for params in ({'field': '²'}, {'products': '9' * 30}, {'n': '²'}, {'field': foreign.id},
                       {'product_types': '999999'}):
            resp = client.get(URL, params)
            assert resp.status_code == 200, params
            assert resp.context['panel_filter_count'] == 0 and len(resp.context['rows']) == 2

    def test_reversed_period_is_swapped(self, setup):
        client, org = setup
        self._setup(org)
        ctx = client.get(URL, {'date_from': _ago(5).isoformat(), 'date_to': _ago(50).isoformat()}).context
        assert [_names(r) for r in ctx['rows']] == [['COBRE', 'ARAÑA'], ['COBRE']]
        assert ctx['date_from'] == _ago(50).isoformat()


@pytest.mark.django_db
def test_more_groups_than_colors_repeat_with_dashed_border(setup):
    client, org = setup
    a, b = FieldFactory(organization=org, name='Uno'), FieldFactory(organization=org, name='Dos')
    names = ['Cobre', 'Cabrio', 'Mosca', 'Calibre', 'Potasio', 'Calcio', 'Hierro', 'Boro',
             'Zinc', 'Abono', 'Raices', 'Rajado', 'Cotonet', 'Piojo']
    for i, name in enumerate(names):
        _done(org, a, name, i + 1)
        _done(org, b, name, i + 1)
    from unittest.mock import patch
    with patch('farm.field_history.COLORS', 4):
        groups = client.get(URL, {'n': 10}).context['groups']
    assert len(groups) == 10  # uno por nombre, con los últimos 10 de cada parcela
    styles = sorted((g['color'], g['dashed']) for g in groups)
    assert styles == sorted([(c, False) for c in range(4)] + [(c, True) for c in [0, 1, 2, 3, 0, 1]])


@pytest.mark.django_db
def test_colors_do_not_change_with_n_or_filters(setup):
    client, org = setup
    fields = [FieldFactory(organization=org, name=n) for n in ('Uno', 'Dos', 'Tres')]
    # Los más antiguos (solo visibles con N=10) forman el grupo más grande
    for field in fields:
        for i in range(4):
            _done(org, field, 'ARAÑA', 60 + i)
        _done(org, field, 'COBRE', 5)
    _done(org, fields[0], 'CABRIO', 3)
    _done(org, fields[1], 'CABRIO', 3)

    def colors(params):
        rows = client.get(URL, params).context['rows']
        return {t.name: t.similar['color'] for r in rows for t in r['treatments'] if t.similar}

    full, short = colors({'n': 10}), colors({'n': 3})
    assert short['COBRE'] == full['COBRE'] and short['CABRIO'] == full['CABRIO']
    assert colors({'n': 3, 'type': 'spraying'})['COBRE'] == full['COBRE']


def _colors(client, params):
    rows = client.get(URL, params).context['rows']
    return {t.name: t.similar['color'] for r in rows for t in r['treatments'] if t.similar}


@pytest.mark.django_db
def test_equal_size_groups_keep_their_color_with_n(setup):
    client, org = setup
    a, b, c = (FieldFactory(organization=org, name=n) for n in ('Uno', 'Dos', 'Tres'))
    for field in (a, b):  # AZUFRE en 4.º lugar: solo se ve con N≥5
        _done(org, field, 'AZUFRE', 40)
        for i in range(3):
            _done(org, field, f'Suelto {field.name} {i}', 10 + i)
    _done(org, c, 'COBRE', 1)
    _done(org, c, 'COBRE', 2)
    c3, c10 = _colors(client, {'n': 3}), _colors(client, {'n': 10})
    assert c3['COBRE'] == c10['COBRE'], (c3, c10)


@pytest.mark.django_db
def test_old_period_colors_stable_with_n(setup):
    client, org = setup
    fields = [FieldFactory(organization=org, name=n) for n in ('Uno', 'Dos')]
    for field in fields:
        for i in range(4):
            _done(org, field, 'ALTERNARIA', 500 + i)
        _done(org, field, 'FENGIB', 420)
        _done(org, field, 'SUELO', 410)
        _done(org, field, 'RECIENTE', 1)
    period = {'date_from': _ago(600).isoformat(), 'date_to': _ago(400).isoformat()}
    short, full = _colors(client, {**period, 'n': 3}), _colors(client, {**period, 'n': 10})
    assert short and short == {k: full[k] for k in short}


@pytest.mark.django_db
def test_group_with_single_visible_member_is_not_colored_and_label_uses_visible(setup):
    client, org = setup
    a, b = FieldFactory(organization=org, name='Uno'), FieldFactory(organization=org, name='Dos')
    _done(org, a, 'RAICES', 1)
    for i, name in enumerate(['COBRE', 'MOSCA', 'CALIBRE', 'HIERRO']):
        _done(org, b, name, i + 1)
    _done(org, b, 'RAICES', 30)  # solo con N≥5
    resp = client.get(URL, {'n': 3})
    assert resp.context['groups'] == []
    assert 'parecido a' not in resp.content.decode()
    resp = client.get(URL, {'n': 5})
    assert [g['label'] for g in resp.context['groups']] == ['RAICES']


@pytest.mark.django_db
def test_legend_and_cards_share_group_index(setup):
    import re
    client, org = setup
    a, b = FieldFactory(organization=org, name='Uno'), FieldFactory(organization=org, name='Dos')
    for name in ('COBRE', 'CABRIO'):
        _done(org, a, name, 3)
        _done(org, b, name, 4)
    html = client.get(URL).content.decode()
    legend = set(re.findall(r'class="bf-key[^"]*" data-bf-group="(\d+)"', html))
    cards = set(re.findall(r'bf-card bf-grouped[^"]*" data-bf-group="(\d+)"', html))
    assert legend == cards == {'1', '2'}


@pytest.mark.django_db
class TestTabsAndHome:

    def test_list_tab_opens_by_field_keeping_shared_filters(self, setup):
        client, org = setup
        field = FieldFactory(organization=org)
        html = client.get(reverse('treatment-list'), {'field': field.id, 'type': 'spraying', 'q': 'x',
                                                      'status': 'completed'}).content.decode()
        assert f'{URL}?field={field.id}&amp;type=spraying"' in html

    def test_list_tab_without_filters_has_no_dates(self, setup):
        client, _ = setup
        assert f'href="{URL}"' in client.get(reverse('treatment-list')).content.decode()

    def test_by_field_tabs_go_back_to_list_with_filters(self, setup):
        client, org = setup
        field = FieldFactory(organization=org)
        _done(org, field, 'COBRE', 3)
        SprayingTreatmentFactory(organization=org, field=field, date=date.today() + timedelta(days=2))
        resp = client.get(URL, {'field': field.id, 'n': 3, 'date_from': _ago(30).isoformat()})
        list_url = reverse('treatment-list')
        assert resp.context['todo_url'] == f'{list_url}?field={field.id}'
        assert resp.context['done_url'] == (
            f'{list_url}?field={field.id}&date_from={_ago(30).isoformat()}&status=completed')
        assert resp.context['todo_count'] == 1 and resp.context['status_tab'] == 'by_field'

    def test_home_card_shows_last_three_per_field(self, setup):
        client, org = setup
        a, b = FieldFactory(organization=org, name='Uno'), FieldFactory(organization=org, name='Dos')
        for field in (a, b):
            for i, name in enumerate(['COBRE', 'CABRIO', 'MOSCA', 'VIEJO']):
                _done(org, field, name, i + 1)
        resp = client.get(reverse('field_list'))
        history = resp.context['field_history']
        assert [[t.name for t in r['treatments']] for r in history['rows']] == [['COBRE', 'CABRIO', 'MOSCA']] * 2
        html = resp.content.decode()
        assert 'Cómo van las parcelas' in html and f'href="{URL}"' in html
        assert {g['label'] for g in history['groups']} == {'COBRE', 'CABRIO', 'MOSCA'}

    def test_tabs_do_not_propagate_invalid_ids(self, setup):
        client, org = setup
        FieldFactory(organization=org)
        resp = client.get(URL, {'field': 'abc', 'products': '999999'})
        for key in ('todo_url', 'done_url'):
            assert 'abc' not in resp.context[key] and '999999' not in resp.context[key]
            assert client.get(resp.context[key]).status_code == 200

    def test_todo_count_matches_list_tab(self, setup):
        client, org = setup
        field = FieldFactory(organization=org)
        today = date.today()
        SprayingTreatmentFactory(organization=org, field=field, date=today + timedelta(days=2))
        SprayingTreatmentFactory(organization=org, field=field, date=_ago(400))  # atrasado de otro año
        SprayingTreatmentFactory(organization=org, field=field, date=date(today.year + 1, 1, 15))
        resp = client.get(URL)
        listed = client.get(resp.context['todo_url']).context['todo_count']
        assert resp.context['todo_count'] == listed == 2

    def test_list_with_mixed_statuses_still_has_tabs(self, setup):
        client, _ = setup
        resp = client.get(reverse('treatment-list'), {'status': ['pending', 'completed']})
        html = resp.content.decode()
        assert resp.context['status_tab'] == 'all' and 'Por parcela' in html
        assert 'tl-tab active' not in html

    def test_home_without_done_treatments_shows_empty_state(self, setup):
        client, org = setup
        FieldFactory(organization=org)
        html = client.get(reverse('field_list')).content.decode()
        assert 'Cómo van las parcelas' in html and 'bf-table' not in html

    def test_home_query_count_does_not_grow_with_fields(self, setup):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        def count():
            client.get(reverse('field_list'))
            with CaptureQueriesContext(connection) as ctx:
                client.get(reverse('field_list'))
            return len(ctx)

        client, org = setup
        field = FieldFactory(organization=org)
        _done(org, field, 'COBRE', 1)
        one = count()
        for i in range(5):
            field = FieldFactory(organization=org)
            for j in range(4):
                _done(org, field, f'T{i}{j}', j + 1)
        assert count() == one


@pytest.mark.django_db
def test_list_uses_same_product_filter_toggle_with_count(setup):
    from farm.tests.factories import ProductTypeFactory, SprayingProductFactory
    client, org = setup
    pt = ProductTypeFactory(organization=org)
    prod = SprayingProductFactory(organization=org)
    html = client.get(reverse('treatment-list'), {'product_types': pt.id, 'products': prod.id}).content.decode()
    assert 'Filtrar por producto' in html and 'Más filtros' not in html and 'Menos filtros' not in html
    assert '<span class="badge bg-primary ms-1">2</span>' in html
