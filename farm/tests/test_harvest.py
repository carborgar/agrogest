import re
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse

from accounts.models import Organization, User
from farm.models import Field, Harvest

YEAR = date.today().year


@pytest.fixture
def org(db):
    return Organization.objects.create(name='Org')


@pytest.fixture
def user(org):
    return User.objects.create_user(username='cosechero', password='pass', organization=org)


@pytest.fixture
def logged(client, user):
    client.force_login(user)
    return client


def make_field(org, name='Cartuja', area='2.5'):
    return Field.objects.create(name=name, area=Decimal(area), crop='olivo', planting_year=2010, organization=org)


def make_harvest(org, field, day, amount, price=None, pending=False, notes=''):
    return Harvest.objects.create(field=field, date=day, amount=amount, sale_price_per_kg=price,
                                  price_pending=pending, notes=notes, organization=org)


def summary(client, **params):
    return client.get(reverse('harvest-summary'), params)


# ── Formulario ────────────────────────────────────────────────────────────────

def test_create_harvest_with_pending_price(logged, org):
    field = make_field(org)
    data = {'field': field.id, 'date': f'{YEAR}-01-01', 'amount': '1200', 'price_pending': 'on', 'notes': 'Test'}

    resp = logged.post(reverse('harvest-create'), data, follow=True)

    assert resp.status_code == 200
    h = Harvest.objects.get(field=field)
    assert h.sale_price_per_kg is None
    assert h.price_pending is True
    assert h.organization == org
    assert h.kg_per_ha() == Decimal('480')


def test_form_page_uses_tf_pattern_and_exposes_areas(logged, org):
    field = make_field(org, area='2.5')

    resp = logged.get(reverse('harvest-create'))

    assert resp.status_code == 200
    assert resp.context['is_edit'] is False
    assert resp.context['field_areas'] == {str(field.id): str(field.area)}
    html = resp.content.decode()
    assert 'tf-summary' in html and 'tf-inp' in html and 'Registrar cosecha' in html


def test_form_edit_page_is_edit(logged, org):
    h = make_harvest(org, make_field(org), f'{YEAR}-02-01', 500, Decimal('0.5'))

    resp = logged.get(reverse('harvest-edit', args=[h.pk]))

    assert resp.status_code == 200
    assert resp.context['is_edit'] is True
    assert 'Guardar' in resp.content.decode()


def test_form_only_offers_own_fields(logged, org):
    mine = make_field(org, 'Mía')
    other = make_field(Organization.objects.create(name='Otra'), 'Ajena')

    resp = logged.get(reverse('harvest-create'))

    queryset = resp.context['form'].fields['field'].queryset
    assert list(queryset) == [mine]
    assert str(other.id) not in resp.context['field_areas']


def test_form_error_shows_banner_and_field_error(logged, org):
    field = make_field(org)

    resp = logged.post(reverse('harvest-create'), {'field': field.id, 'date': f'{YEAR}-01-01', 'amount': ''})

    assert resp.status_code == 200
    html = resp.content.decode()
    assert 'Revisa los campos marcados.' in html
    assert 'tf-err' in html
    assert Harvest.objects.count() == 0


def test_negative_amount_is_rejected(logged, org):
    field = make_field(org)

    resp = logged.post(reverse('harvest-create'), {'field': field.id, 'date': f'{YEAR}-01-01', 'amount': '-5'})

    assert resp.status_code == 200
    assert not Harvest.objects.exists()


def test_edit_updates_and_clears_price_when_pending(logged, org):
    h = make_harvest(org, make_field(org), f'{YEAR}-02-01', 500, Decimal('0.5'))

    resp = logged.post(reverse('harvest-edit', args=[h.pk]), {
        'field': h.field_id, 'date': f'{YEAR}-02-01', 'amount': '700', 'sale_price_per_kg': '0.50', 'price_pending': 'on'})

    assert resp.status_code == 302
    h.refresh_from_db()
    assert h.amount == 700 and h.sale_price_per_kg is None and h.price_pending


def test_cannot_edit_other_organization_harvest(logged):
    other = Organization.objects.create(name='Otra')
    h = make_harvest(other, make_field(other), f'{YEAR}-02-01', 500)

    resp = logged.get(reverse('harvest-edit', args=[h.pk]))

    assert resp.status_code in (302, 403, 404)


def test_delete_removes_harvest_and_shows_message(logged, org):
    h = make_harvest(org, make_field(org), f'{YEAR}-02-01', 500)

    resp = logged.post(reverse('harvest-delete', args=[h.pk]))

    assert resp.status_code == 302
    assert not Harvest.objects.filter(pk=h.pk).exists()
    assert 'Cosecha eliminada correctamente.' in [str(m) for m in get_messages(resp.wsgi_request)]


# ── Resumen ───────────────────────────────────────────────────────────────────

def test_summary_calculates_totals(logged, org):
    field = make_field(org, area='1.0')
    make_harvest(org, field, f'{YEAR}-02-01', 1000, Decimal('0.5'))
    make_harvest(org, field, f'{YEAR}-02-02', 1500, Decimal('0.6'))
    make_harvest(org, field, f'{YEAR}-02-03', 500, None, pending=True)

    resp = summary(logged)

    assert resp.status_code == 200
    assert resp.context['total_kg'] == 3000
    assert resp.context['total_area'] == Decimal('1.0')
    assert resp.context['kg_per_ha_overall'] == Decimal('3000')
    assert resp.context['income'] == Decimal('1000') * Decimal('0.5') + Decimal('1500') * Decimal('0.6')
    assert resp.context['harvest_count'] == 3
    (group,) = resp.context['field_groups']
    assert group['total_kg'] == 3000 and group['kg_per_ha'] == Decimal('3000') and group['income'] == Decimal('1400')


def test_summary_defaults_to_current_year_and_todos_shows_all(logged, org):
    field = make_field(org)
    make_harvest(org, field, f'{YEAR}-02-01', 100)
    make_harvest(org, field, f'{YEAR - 1}-12-01', 200)

    assert summary(logged).context['total_kg'] == 100
    resp = summary(logged, date_from='', date_to='')
    assert resp.context['total_kg'] == 300
    assert resp.context['active_year'] is None and not resp.context['custom_dates']


def test_year_tabs_keep_other_filters_and_mark_active(logged, org):
    field = make_field(org)

    resp = summary(logged, field=field.id, q='olivo')

    tabs = resp.context['year_tabs']
    assert [t['label'] for t in tabs] == ['Todos', str(YEAR), str(YEAR - 1), str(YEAR - 2)]
    assert [t['active'] for t in tabs] == [False, True, False, False]
    for tab in tabs:
        assert f'field={field.id}' in tab['url'] and 'q=olivo' in tab['url']
    html = resp.content.decode()
    assert 'aria-current="page"' in html and 'quick-year-btn' not in html
    assert 'date_from=&date_to=' in tabs[0]['url'] or 'date_to=&date_from=' in tabs[0]['url']


def test_summary_search_by_field_and_notes(logged, org):
    cartuja, borboli = make_field(org, 'Cartuja'), make_field(org, 'Borboli')
    make_harvest(org, cartuja, f'{YEAR}-02-01', 100, notes='zona alta')
    make_harvest(org, borboli, f'{YEAR}-02-02', 200)

    assert summary(logged, q='cartu').context['total_kg'] == 100
    assert summary(logged, q='ALTA').context['total_kg'] == 100
    assert summary(logged, q='nada').context['harvest_count'] == 0


def test_summary_filter_by_field_and_single_field_flag(logged, org):
    a, b = make_field(org, 'A'), make_field(org, 'B')
    make_harvest(org, a, f'{YEAR}-02-01', 100)
    make_harvest(org, b, f'{YEAR}-02-02', 200)

    resp = summary(logged, field=a.id)
    assert resp.context['total_kg'] == 100 and resp.context['single_field_selected']
    assert 'Por parcela' not in resp.content.decode()

    resp = logged.get(reverse('harvest-summary') + f'?field={a.id}&field={b.id}')
    assert resp.context['total_kg'] == 300 and not resp.context['single_field_selected']
    assert 'Por parcela' in resp.content.decode()
    assert resp.context['panel_filter_count'] == 2


def test_summary_ignores_invalid_params(logged, org):
    make_harvest(org, make_field(org), f'{YEAR}-02-01', 100)

    resp = summary(logged, field=['abc', '²', '9' * 30], date_from='2026-02-30', date_to='basura')

    assert resp.status_code == 200
    assert resp.context['total_kg'] == 100
    assert resp.context['selected_field_ids'] == []


def test_summary_with_only_date_from_has_no_upper_limit(logged, org):
    field = make_field(org)
    make_harvest(org, field, f'{YEAR - 1}-06-01', 10)
    make_harvest(org, field, f'{YEAR}-02-01', 100)
    make_harvest(org, field, f'{YEAR + 1}-02-01', 1000)

    resp = summary(logged, date_from=f'{YEAR}-01-01')

    assert resp.status_code == 200
    assert resp.context['total_kg'] == 1100
    assert resp.context['active_date_to'] == ''


def test_summary_only_counts_own_organization(logged, org):
    make_harvest(org, make_field(org), f'{YEAR}-02-01', 100)
    other = Organization.objects.create(name='Otra')
    make_harvest(other, make_field(other, 'Ajena'), f'{YEAR}-02-01', 999)

    assert summary(logged).context['total_kg'] == 100


def test_summary_paginates_on_server_with_totals_from_everything(logged, org):
    field = make_field(org)
    for i in range(51):
        make_harvest(org, field, f'{YEAR}-01-01', 10)

    first = summary(logged)
    second = summary(logged, page=2)

    assert len(first.context['harvests']) == 50 and len(second.context['harvests']) == 1
    assert first.context['total_kg'] == second.context['total_kg'] == 510
    assert first.context['harvest_count'] == 51


def test_summary_empty_states(logged, org):
    html = summary(logged).content.decode()
    assert 'No hay cosechas en' in html

    html = summary(logged, date_from='', date_to='').content.decode()
    assert 'Todavía no hay cosechas' in html

    html = summary(logged, q='zzz').content.decode()
    assert 'No hay cosechas con estos filtros' in html


def test_summary_row_shows_pending_and_price(logged, org):
    field = make_field(org)
    make_harvest(org, field, f'{YEAR}-02-01', 1850, Decimal('0.62'))
    make_harvest(org, field, f'{YEAR}-02-02', 900, None, pending=True)

    html = summary(logged).content.decode()

    # Django separa los miles con un espacio duro en es-ES
    assert re.search(r'1\D850', html) and '0,62' in html and re.search(r'1\D147,00', html)
    assert 'pendiente' in html.lower()
