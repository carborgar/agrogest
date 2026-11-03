import json
import re
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.staticfiles import finders
from django.urls import reverse

from accounts.models import User
from farm.models import Expense, ExpenseType, Harvest, Treatment
from farm.tests.factories import *

YEAR = date.today().year


@pytest.fixture
def setup(client):
    org = OrganizationFactory()
    user = User.objects.create_user(username='stats', password='pass', organization=org)
    client.force_login(user)
    f1 = FieldFactory(organization=org, area=2.0)
    f2 = FieldFactory(organization=org, area=3.0)
    return client, org, f1, f2


def _expense(org, field, name, amount, year=YEAR):
    et, _ = ExpenseType.objects.get_or_create(name=name, organization=org)
    return Expense.objects.create(organization=org, field=field, expense_type=et, payment_date=date(year, 3, 1),
                                  calculation_mode='total', amount=Decimal(amount))


def _harvest(org, field, kg, price, year=YEAR):
    return Harvest.objects.create(organization=org, field=field, date=date(year, 2, 1), amount=kg,
                                  sale_price_per_kg=Decimal(price) if price else None)


def _done(org, field, month, **kw):
    d = date(YEAR, month, 10)
    return SprayingTreatmentFactory(organization=org, field=field, date=d, finish_date=d,
                                    status=Treatment.STATUS_COMPLETED, **kw)


def _get(client, **params):
    return client.get(reverse('yearly-stats'), params)


@pytest.mark.django_db
class TestKeyFigures:

    def test_result_and_cost_per_ha(self, setup):
        client, org, f1, f2 = setup
        _expense(org, f1, 'Agua', '500')
        _harvest(org, f1, 1000, '2.00')
        ctx = _get(client).context
        assert ctx['total_cost_all'] == 500
        assert ctx['result'] == 1500  # 2000 de ingresos - 500 de gasto
        assert ctx['total_ha_farm'] == 5.0
        assert ctx['cost_per_ha'] == 100.0

    def test_field_filter_applies_to_expenses_and_harvests(self, setup):
        client, org, f1, f2 = setup
        _expense(org, f1, 'Agua', '500')
        _expense(org, f2, 'Agua', '300')
        _harvest(org, f1, 1000, '2.00')
        _harvest(org, f2, 4000, '1.00')
        ctx = _get(client, field=f1.id).context
        assert ctx['total_expenses'] == 500
        assert ctx['total_harvest_kg'] == 1000
        assert ctx['total_ha_farm'] == 2.0
        assert ctx['cost_per_ha'] == 250.0

    def test_expenses_rest_completes_the_total(self, setup):
        client, org, f1, _ = setup
        for i in range(7):
            _expense(org, f1, f'Tipo {i}', str(100 + i))
        ctx = _get(client).context
        assert len(ctx['expenses_by_type']) == 5
        listed = sum(e['total'] for e in ctx['expenses_by_type'])
        assert listed + ctx['expenses_rest'] == ctx['total_expenses']
        assert ctx['expenses_rest'] > 0

    def test_harvests_without_price_are_counted(self, setup):
        client, org, f1, _ = setup
        _harvest(org, f1, 500, None)
        _harvest(org, f1, 500, '1.00')
        assert _get(client).context['harvests_without_price'] == 1


@pytest.mark.django_db
class TestYearTabs:

    def test_three_tabs_with_current_year_active(self, setup):
        client, *_ = setup
        tabs = _get(client).context['year_tabs']
        assert [t['label'] for t in tabs] == [str(YEAR), str(YEAR - 1), str(YEAR - 2)]
        assert [t['active'] for t in tabs] == [True, False, False]

    def test_tabs_keep_filters(self, setup):
        client, org, f1, _ = setup
        tabs = _get(client, field=f1.id, type='spraying', year=YEAR - 1).context['year_tabs']
        assert tabs[1]['active']
        for t in tabs:
            assert f'field={f1.id}' in t['url'] and 'type=spraying' in t['url']
        assert tabs[0]['url'].count('year=') == 1 and f'year={YEAR}' in tabs[0]['url']

    def test_older_selected_year_gets_its_own_tab(self, setup):
        client, *_ = setup
        tabs = _get(client, year=YEAR - 5).context['year_tabs']
        assert tabs[-1]['label'] == str(YEAR - 5) and tabs[-1]['active']

    def test_filter_counter_and_clear_url(self, setup):
        client, org, f1, f2 = setup
        ctx = _get(client, field=[f1.id, f2.id], type='spraying').context
        assert ctx['panel_filter_count'] == 3
        assert ctx['clear_url'] == f'?year={YEAR}'


@pytest.mark.django_db
class TestMonthlyBars:

    def test_bars_scale_to_busiest_month(self, setup):
        client, org, f1, _ = setup
        for _i in range(2):
            _done(org, f1, 3)
        _done(org, f1, 5)
        bars = _get(client).context['monthly_bars']
        assert [b['pct'] for b in bars][2:5] == [100, 0, 50]
        assert [b['is_max'] for b in bars].count(True) == 1 and bars[2]['is_max']

    def test_no_highlight_on_ties_or_empty(self, setup):
        client, org, f1, _ = setup
        assert not any(b['is_max'] for b in _get(client).context['monthly_bars'])
        _done(org, f1, 3)
        _done(org, f1, 4)
        assert not any(b['is_max'] for b in _get(client).context['monthly_bars'])


@pytest.mark.django_db
class TestRendering:

    def test_empty_state_without_filters(self, setup):
        client, *_ = setup
        html = _get(client).content.decode()
        assert 'Todavía no hay actividad' in html
        assert '<canvas' not in html
        assert 'stats-charts-data' not in html

    def test_empty_state_with_filters_offers_to_clear(self, setup):
        client, org, f1, f2 = setup
        _expense(org, f2, 'Agua', '300')
        html = _get(client, field=f1.id).content.decode()
        assert 'No hay datos con estos filtros' in html
        assert 'Quitar filtros' in html

    def test_full_page_has_key_figures_and_no_inline_style_blocks(self, setup):
        client, org, f1, _ = setup
        _expense(org, f1, 'Agua', '500')
        _done(org, f1, 3)
        html = _get(client).content.decode()
        for label in ('Gasto total', 'Ingresos', 'Resultado', 'Gasto por ha'):
            assert label in html
        assert 'aria-current="page"' in html
        assert '<style' not in html.split('<body', 1)[1]


def _chart_data(html):
    raw = re.search(r'<script id="stats-charts-data" type="application/json">(.*?)</script>', html, re.S).group(1)
    return json.loads(raw)


@pytest.mark.django_db
class TestCharts:

    def test_canvases_and_json_data(self, setup):
        client, org, f1, f2 = setup
        _expense(org, f1, 'Agua', '500')
        _harvest(org, f1, 1500, '2.00')
        _harvest(org, f2, 800, '1.00')
        for _i in range(2):
            _done(org, f1, 3)
        _done(org, f1, 5)
        html = _get(client).content.decode()
        for key in ('months', 'expenses', 'harvests'):
            assert f'data-st-chart="{key}"' in html
        assert html.count('role="img"') >= 3 and 'aria-label="Gráfica' in html
        assert html.count('<details class="st-data"') >= 3 and 'Ver datos' in html
        data = _chart_data(html)
        assert data['months']['counts'][2:5] == [2, 0, 1]
        assert data['months']['peak'] == 2 and len(data['months']['labels']) == 12
        assert data['expenses'] == [{'label': 'Agua', 'value': 500.0, 'other': False}]
        assert data['harvests'] == [{'label': f1.name, 'value': 1500.0}, {'label': f2.name, 'value': 800.0}]

    def test_data_is_json_script_not_inline_js(self, setup):
        client, org, f1, _ = setup
        _expense(org, f1, 'Agua <b>"x"</b>', '500')
        html = _get(client).content.decode()
        assert 'type="application/json"' in html
        assert 'Agua <b>' not in html  # escapado por json_script
        assert _chart_data(html)['expenses'][0]['label'] == 'Agua <b>"x"</b>'
        assert 'new Chart(' not in html

    def test_product_type_chart_data(self, setup):
        client, org, f1, _ = setup
        t = _done(org, f1, 3)
        TreatmentProductFactory(treatment=t, organization=org)
        data = _chart_data(_get(client).content.decode())
        assert len(data['productTypes']) == 1
        assert data['productTypes'][0]['value'] == 1
        assert isinstance(data['productTypes'][0]['cost'], float)

    def test_sections_without_data_show_empty_state_not_canvas(self, setup):
        client, org, f1, _ = setup
        _expense(org, f1, 'Agua', '500')  # solo hay gasto: no hay tratamientos ni cosechas
        html = _get(client).content.decode()
        assert 'data-st-chart="expenses"' in html
        for key in ('months', 'harvests', 'types'):
            assert f'data-st-chart="{key}"' not in html
        assert 'Sin tratamientos completados' in html
        assert 'Sin cosechas en' in html
        assert 'hm-empty' in html

    def test_no_expenses_shows_empty_state(self, setup):
        client, org, f1, _ = setup
        _harvest(org, f1, 500, '1.00')
        html = _get(client).content.decode()
        assert 'data-st-chart="expenses"' not in html and 'Sin gastos en' in html
        assert 'data-st-chart="harvests"' in html

    def test_chartjs_is_vendored_and_loaded_with_static(self, setup):
        client, org, f1, _ = setup
        _done(org, f1, 3)
        html = _get(client).content.decode()
        vendor = finders.find('js/vendor/chart.umd.min.js')
        assert vendor, 'Chart.js debe estar versionado en static/js/vendor'
        with open(vendor, encoding='utf-8') as fh:
            head = fh.read(300)
        assert 'Chart.js v4.4.0' in head and 'MIT License' in head
        assert finders.find('js/stats-charts.js')
        assert '/static/js/vendor/chart.umd.min.js' in html and '/static/js/stats-charts.js' in html
        assert 'chart.js@' not in html
        assert html.index('chart.umd.min.js') < html.index('stats-charts.js')


@pytest.mark.django_db
class TestRobustness:

    @pytest.mark.parametrize('params', [
        {'year': '0'}, {'year': '99999'}, {'year': '1999'}, {'year': 'abc'},
        {'field': 'abc'}, {'field': '²'}, {'field': '99999999999999999999'}, {'type': 'xx'},
    ])
    def test_invalid_params_fall_back_to_defaults(self, setup, params):
        client, *_ = setup
        resp = _get(client, **params)
        assert resp.status_code == 200
        ctx = resp.context
        assert ctx['selected_year'] == YEAR
        assert ctx['selected_fields'] == [] and ctx['selected_types'] == []

    def test_selected_year_always_in_year_list(self, setup):
        client, *_ = setup
        assert 2010 in _get(client, year=2010).context['available_years']
        assert YEAR + 1 in _get(client, year=YEAR + 1).context['available_years']


@pytest.mark.django_db
class TestScopeAndFilters:

    def test_type_filter_hides_result_and_shows_note(self, setup):
        client, org, f1, _ = setup
        _expense(org, f1, 'Agua', '500')
        _done(org, f1, 3)
        resp = _get(client, type='spraying')
        assert resp.context['result'] is None
        assert 'El tipo solo filtra tratamientos y coste de productos' in resp.content.decode()
        resp = _get(client)
        assert resp.context['result'] is not None
        assert 'El tipo solo filtra' not in resp.content.decode()

    def test_unpriced_harvest_warning_next_to_income(self, setup):
        client, org, f1, _ = setup
        _harvest(org, f1, 500, None)
        assert 'sin precio' in _get(client).content.decode()

    def test_other_organization_field_is_excluded(self, setup):
        client, org, f1, _ = setup
        other = OrganizationFactory(name="Otra organización")
        of = FieldFactory(organization=other, area=7.0)
        _expense(other, of, 'Agua', '900')
        ctx = _get(client, field=of.id).context
        assert ctx['total_expenses'] == 0
        assert ctx['total_ha_farm'] == 0
        assert _get(client).context['total_ha_farm'] == 5.0

    def test_data_only_in_other_years(self, setup):
        client, org, f1, _ = setup
        _expense(org, f1, 'Agua', '500', year=YEAR - 1)
        html = _get(client).content.decode()
        assert 'Todavía no hay actividad' in html
        assert _get(client, year=YEAR - 1).context['total_expenses'] == 500

    def test_zero_area_shows_dash(self, client):
        org = OrganizationFactory()
        client.force_login(User.objects.create_user(username='z', password='p', organization=org))
        f = FieldFactory(organization=org, area=0)
        _expense(org, f, 'Agua', '100')
        resp = _get(client)
        assert resp.context['cost_per_ha'] is None
        assert '—' in resp.content.decode()
