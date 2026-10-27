"""Pantalla única de Productos: tipos como chips, coste/ha, uso en el año,
tendencia de precio, selección para la comparativa y vistas de tipos."""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse

from accounts.models import User
from farm.models import Product, ProductPriceHistory, ProductType, TreatmentProduct
from farm.tests.factories import *


@pytest.fixture
def setup(client):
    org = OrganizationFactory()
    user = User.objects.create_user(username='productos', password='pass', organization=org)
    client.force_login(user)
    return client, org


def _product(org, ptype=None, **kwargs):
    kwargs.setdefault('product_type', ptype or ProductTypeFactory(organization=org))
    return ProductFactory(organization=org, **kwargs)


def _list(client, **params):
    return client.get(reverse('product-list'), params)


def _names(response):
    return [p.name for p in response.context['products']]


def _use(org, product, treatment, total_price):
    tp = TreatmentProductFactory(treatment=treatment, product=product, organization=org)
    TreatmentProduct.objects.filter(pk=tp.pk).update(total_price=Decimal(total_price))
    return tp


# ── Coste/ha del modelo ───────────────────────────────────────────────────
@pytest.mark.django_db
class TestCostPerHa:

    def test_dose_per_volume_uses_reference_water(self):
        p = ProductFactory(price=Decimal('25'), spraying_dose=Decimal('2.5'), spraying_dose_type='l_per_1000l')
        # 2,5 L/1000 L × 1000 L/ha × 25 €/L
        assert p.cost_per_ha('spraying') == Decimal('62.50')

    def test_water_can_be_overridden(self):
        p = ProductFactory(price=Decimal('10'), spraying_dose=Decimal('2'), spraying_dose_type='kg_per_1000l')
        assert p.cost_per_ha('spraying', water_per_ha=500) == Decimal('10.00')

    def test_per_ha_and_pct(self):
        p = ProductFactory(price=Decimal('2'), fertigation_dose=Decimal('10'), fertigation_dose_type='l_per_ha',
                           spraying_dose=Decimal('0.5'), spraying_dose_type='pct')
        assert p.cost_per_ha('fertigation') == Decimal('20.00')
        assert p.cost_per_ha('spraying') == Decimal('10.00')  # 0,5 % de 1000 L = 5 L × 2 €

    def test_none_without_price_dose_or_application(self):
        no_price = ProductFactory(price=Decimal('0'))
        assert no_price.cost_per_ha('spraying') is None
        no_fert = ProductFactory(price=Decimal('5'), fertigation_dose=None, fertigation_dose_type=None)
        assert no_fert.cost_per_ha('fertigation') is None


# ── Listado ───────────────────────────────────────────────────────────────
@pytest.mark.django_db
class TestProductList:

    def test_no_pagination(self, setup):
        client, org = setup
        ptype = ProductTypeFactory(organization=org)
        for _ in range(25):
            _product(org, ptype)
        response = _list(client)
        assert response.status_code == 200
        assert len(response.context['products']) == 25
        assert response.context['page_obj'] is None and not response.context['is_paginated']

    def test_other_organizations_are_not_listed(self, setup):
        client, org = setup
        _product(org, name='Mío')
        ProductFactory(organization=OrganizationFactory(name='Otra org'), name='Ajeno')
        assert _names(_list(client)) == ['Mío']

    def test_filters(self, setup):
        client, org = setup
        fungi = ProductTypeFactory(organization=org, name='Fungicida')
        alga = ProductTypeFactory(organization=org, name='Algas')
        _product(org, fungi, name='A fungicida', spraying_dose=1, spraying_dose_type='l_per_ha',
                 fertigation_dose=None, fertigation_dose_type=None)
        _product(org, alga, name='B algas', price=Decimal('0'))
        _product(org, alga, name='C archivada', is_active=False)

        assert _names(_list(client)) == ['A fungicida', 'B algas']
        assert _names(_list(client, type=fungi.pk)) == ['A fungicida']
        assert _names(_list(client, application='fertigation')) == ['B algas']
        assert _names(_list(client, no_price='1')) == ['B algas']
        assert _names(_list(client, archived='1')) == ['A fungicida', 'B algas', 'C archivada']

    def test_selected_type_name_and_new_toolbar(self, setup):
        client, org = setup
        fungi = ProductTypeFactory(organization=org, name='Fungicida')
        _product(org, fungi)
        r = _list(client, type=fungi.pk)
        assert r.context['selected_type_name'] == 'Fungicida'
        assert _list(client).context['selected_type_name'] == ''
        html = _list(client).content.decode()
        for needle in ('id="plTopCompare"', 'id="plTypeSearch"', 'id="typeSearch"', 'pl-info'):
            assert needle in html
        assert 'pl-foot' not in html
        assert '1000 L/ha' in html

    def test_filter_links_keep_other_filters(self, setup):
        client, org = setup
        fungi = ProductTypeFactory(organization=org, name='Fungicida')
        _product(org, fungi)
        html = _list(client, type=fungi.pk, application='spraying').content.decode()
        assert f'type={fungi.pk}' in html and 'application=spraying' in html

    def test_type_chips_count_visible_products_only(self, setup):
        client, org = setup
        used = ProductTypeFactory(organization=org, name='Con productos')
        only_archived = ProductTypeFactory(organization=org, name='Solo archivados')
        ProductTypeFactory(organization=org, name='Vacío')
        _product(org, used)
        _product(org, only_archived, is_active=False)

        context = _list(client).context
        assert [(t.name, t.visible_count) for t in context['type_chips']] == [('Con productos', 1)]
        # «Gestionar tipos» sí los muestra todos, con su recuento total
        counts = {t.name: t.product_count for t in context['product_types']}
        assert counts == {'Con productos': 1, 'Solo archivados': 1, 'Vacío': 0}

        with_archived = _list(client, archived='1').context
        assert {t.name for t in with_archived['type_chips']} == {'Con productos', 'Solo archivados'}

    def test_year_usage_separates_spent_and_planned(self, setup):
        client, org = setup
        field, machine = FieldFactory(organization=org), MachineFactory(organization=org)
        product = _product(org)
        today = date.today()

        done = SprayingTreatmentFactory(organization=org, field=field, machine=machine, date=today,
                                        finish_date=today)
        last_year = SprayingTreatmentFactory(organization=org, field=field, machine=machine,
                                             date=date(today.year - 1, 6, 1), finish_date=date(today.year - 1, 6, 1))
        pending = SprayingTreatmentFactory(organization=org, field=field, machine=machine,
                                           date=today + timedelta(days=10))
        late = SprayingTreatmentFactory(organization=org, field=field, machine=machine,
                                        date=today - timedelta(days=3))
        _use(org, product, done, '100')
        _use(org, product, last_year, '999')   # otro año: no cuenta como gastado
        _use(org, product, pending, '40')
        _use(org, product, late, '10')

        listed = _list(client).context['products'][0]
        assert (listed.done_count, listed.spent) == (1, Decimal('100'))
        assert (listed.planned_count, listed.planned_cost) == (2, Decimal('50'))

    def test_unused_product_has_no_usage(self, setup):
        client, org = setup
        _product(org)
        listed = _list(client).context['products'][0]
        assert listed.done_count == 0 and listed.planned_count == 0

    def test_cost_per_ha_in_list(self, setup):
        client, org = setup
        _product(org, price=Decimal('25'), spraying_dose=Decimal('2.5'), spraying_dose_type='l_per_1000l',
                 fertigation_dose=None, fertigation_dose_type=None)
        listed = _list(client).context['products'][0]
        assert listed.cost_spraying == Decimal('62.50')
        assert listed.cost_fertigation is None

    def test_price_trend_needs_two_prices(self, setup):
        client, org = setup
        one = _product(org, name='Un precio', price=Decimal('10'))
        two = _product(org, name='Dos precios', price=Decimal('12'))
        ProductPriceHistory.objects.create(product=one, price=Decimal('10'), effective_date=date(2026, 1, 1),
                                           organization=org)
        ProductPriceHistory.objects.create(product=two, price=Decimal('10'), effective_date=date(2026, 1, 1),
                                           organization=org)
        ProductPriceHistory.objects.create(product=two, price=Decimal('12'), effective_date=date(2026, 5, 1),
                                           organization=org)
        by_name = {p.name: p for p in _list(client).context['products']}
        assert by_name['Un precio'].price_trend is None
        trend = by_name['Dos precios'].price_trend
        assert trend['up'] is True and trend['percent'] == 20 and trend['since'] == date(2026, 5, 1)

    def test_page_renders_new_ui_and_drops_old_menu_entries(self, setup):
        client, org = setup
        _product(org, name='ALLIETTE')
        html = _list(client).content.decode()
        assert 'ALLIETTE' in html and 'Gestionar tipos' in html and 'plBar' in html
        # Tipos y comparativa ya no son entradas del menú
        assert 'productosMenu' not in html
        assert 'href="/productos/tipos/"' not in html
        assert 'nav-submenu' in html  # el submenú de Gastos sigue existiendo

    def test_filter_links_keep_other_params(self, setup):
        client, org = setup
        ptype = ProductTypeFactory(organization=org, name='Algas')
        _product(org, ptype)
        html = _list(client, application='spraying').content.decode()
        assert f'type={ptype.pk}' in html and 'application=spraying' in html


# ── Historial de precios al guardar ───────────────────────────────────────
@pytest.mark.django_db
class TestPriceHistoryOnSave:

    def _post(self, client, ptype, url, **extra):
        data = {'name': 'Nuevo', 'product_type': ptype.pk, 'price': '10.00', 'comments': '',
                'spraying_dose': '1', 'spraying_dose_type': 'l_per_ha',
                'fertigation_dose': '', 'fertigation_dose_type': ''}
        data.update(extra)
        return client.post(url, data)

    def test_creating_records_first_price(self, setup):
        client, org = setup
        ptype = ProductTypeFactory(organization=org)
        assert self._post(client, ptype, reverse('product-create')).status_code == 302
        product = Product.objects.get(name='Nuevo')
        assert [h.price for h in product.price_history.all()] == [Decimal('10.00')]

    def test_creating_without_price_records_nothing(self, setup):
        client, org = setup
        ptype = ProductTypeFactory(organization=org)
        self._post(client, ptype, reverse('product-create'), price='0')
        assert not Product.objects.get(name='Nuevo').price_history.exists()

    def test_price_change_on_legacy_product_keeps_the_old_price(self, setup):
        client, org = setup
        product = _product(org, name='Antiguo', price=Decimal('10'))   # sin historial, como los ya existentes
        self._post(client, product.product_type, reverse('product-edit', args=[product.pk]),
                   name='Antiguo', price='12.00')
        prices = sorted(h.price for h in product.price_history.all())
        assert prices == [Decimal('10.00'), Decimal('12.00')]

    def test_same_price_adds_nothing(self, setup):
        client, org = setup
        product = _product(org, name='Igual', price=Decimal('10'))
        self._post(client, product.product_type, reverse('product-edit', args=[product.pk]),
                   name='Igual', price='10.00')
        assert not product.price_history.exists()


# ── Comparativa ───────────────────────────────────────────────────────────
@pytest.mark.django_db
class TestComparison:

    def test_ids_are_preloaded_and_foreign_or_invalid_ignored(self, setup):
        client, org = setup
        mine_a, mine_b = _product(org), _product(org)
        foreign = ProductFactory(organization=OrganizationFactory(name='Otra org'))
        response = client.get(reverse('product-comparison'),
                              {'ids': f'{mine_b.pk},{foreign.pk},abc,{mine_a.pk},{mine_b.pk},-3'})
        assert response.status_code == 200
        assert response.context['initial_ids'] == [mine_b.pk, mine_a.pk]

    def test_without_ids_starts_empty(self, setup):
        client, _ = setup
        assert client.get(reverse('product-comparison')).context['initial_ids'] == []

    def test_ids_are_capped(self, setup):
        client, org = setup
        ids = [_product(org).pk for _ in range(15)]
        response = client.get(reverse('product-comparison'), {'ids': ','.join(map(str, ids))})
        assert response.context['initial_ids'] == ids[:response.context['max_products']]


# ── Tipos de producto ─────────────────────────────────────────────────────
@pytest.mark.django_db
class TestProductTypes:

    def test_old_list_url_redirects_to_products(self, setup):
        client, _ = setup
        response = client.get(reverse('product-type-list'))
        assert response.status_code == 302 and response.url == reverse('product-list')

    def test_create_redirects_to_products_with_message(self, setup):
        client, org = setup
        response = client.post(reverse('product-type-create'), {'name': 'Nuevo tipo', 'description': ''})
        assert response.status_code == 302 and response.url == reverse('product-list')
        assert ProductType.objects.get(name='Nuevo tipo').organization == org
        assert 'creado' in str(list(get_messages(response.wsgi_request))[0])

    def test_ajax_create_returns_json_and_leaves_no_message(self, setup):
        client, org = setup
        response = client.post(reverse('product-type-create'), {'name': 'Rápido'},
                               headers={'X-Requested-With': 'XMLHttpRequest'})
        assert response.status_code == 201
        created = ProductType.objects.get(name='Rápido')
        assert response.json() == {'id': created.pk, 'name': 'Rápido'}
        assert list(get_messages(response.wsgi_request)) == []

    def test_duplicate_name_is_rejected_ignoring_case(self, setup):
        client, org = setup
        ProductTypeFactory(organization=org, name='Fungicida')
        response = client.post(reverse('product-type-create'), {'name': 'fungicida'},
                               headers={'X-Requested-With': 'XMLHttpRequest'})
        assert response.status_code == 400
        assert 'Ya tienes' in response.json()['errors'][0]
        assert ProductType.objects.filter(organization=org).count() == 1

    def test_same_name_in_another_organization_is_fine(self, setup):
        client, org = setup
        ProductTypeFactory(organization=OrganizationFactory(name='Otra org'), name='Fungicida')
        response = client.post(reverse('product-type-create'), {'name': 'Fungicida'})
        assert response.status_code == 302

    def test_editing_keeps_the_organization(self, setup):
        client, org = setup
        ptype = ProductTypeFactory(organization=org, name='Antes')
        client.post(reverse('product-type-edit', args=[ptype.pk]), {'name': 'Después', 'description': ''})
        ptype.refresh_from_db()
        assert (ptype.name, ptype.organization) == ('Después', org)

    def test_cannot_edit_foreign_type(self, setup):
        client, _ = setup
        foreign = ProductTypeFactory(organization=OrganizationFactory(name='Otra org'))
        response = client.post(reverse('product-type-edit', args=[foreign.pk]), {'name': 'Hack'})
        foreign.refresh_from_db()
        assert foreign.name != 'Hack' and response.status_code in (302, 403, 404)

    def test_delete_unused_type_shows_success_message(self, setup):
        client, org = setup
        ptype = ProductTypeFactory(organization=org)
        response = client.post(reverse('product-type-delete', args=[ptype.pk]))
        assert response.status_code == 302 and response.url == reverse('product-list')
        assert not ProductType.objects.filter(pk=ptype.pk).exists()
        assert 'eliminado' in str(list(get_messages(response.wsgi_request))[0])

    def test_delete_type_in_use_is_refused_without_500(self, setup):
        client, org = setup
        ptype = ProductTypeFactory(organization=org)
        _product(org, ptype)
        response = client.post(reverse('product-type-delete', args=[ptype.pk]))
        assert response.status_code == 302
        assert ProductType.objects.filter(pk=ptype.pk).exists()
        assert 'No se puede eliminar' in str(list(get_messages(response.wsgi_request))[0])


# ── Borrado de productos ──────────────────────────────────────────────────
@pytest.mark.django_db
class TestProductDelete:

    def test_delete_shows_success_message(self, setup):
        client, org = setup
        product = _product(org)
        response = client.post(reverse('product-delete', args=[product.pk]))
        assert response.status_code == 302
        assert not Product.objects.filter(pk=product.pk).exists()
        assert 'eliminado' in str(list(get_messages(response.wsgi_request))[0])

    def test_delete_product_used_in_treatment_is_refused_without_500(self, setup):
        client, org = setup
        product = _product(org)
        treatment = SprayingTreatmentFactory(organization=org, field=FieldFactory(organization=org),
                                             machine=MachineFactory(organization=org))
        _use(org, product, treatment, '10')
        response = client.post(reverse('product-delete', args=[product.pk]))
        assert response.status_code == 302
        assert Product.objects.filter(pk=product.pk).exists()
        assert 'No se puede eliminar' in str(list(get_messages(response.wsgi_request))[0])
