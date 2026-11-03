"""Formularios de producto y de tipo con el patrón tf-*: contexto, errores y histórico."""
import json
import re
import shutil
import subprocess
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse

from accounts.models import User
from farm.models import Product, ProductPriceHistory
from farm.tests.factories import *


@pytest.fixture
def setup(client):
    org = OrganizationFactory()
    user = User.objects.create_user(username='formprod', password='pass', organization=org)
    client.force_login(user)
    return client, org


def _history(product, org, prices):
    today = date.today()
    for i, price in enumerate(prices):
        ProductPriceHistory.objects.create(product=product, price=Decimal(price), organization=org,
                                           effective_date=today - timedelta(days=100 * (len(prices) - i)))


@pytest.mark.django_db
class TestProductForm:

    def test_new_form_uses_tf_pattern_and_reference_water(self, setup):
        client, _ = setup
        response = client.get(reverse('product-create'))
        html = response.content.decode()
        assert response.context['reference_water'] == Product.REFERENCE_WATER_PER_HA
        assert 'tf-layout' in html and 'tf-summary' in html and 'tf-inp' in html
        assert 'id="pfSprayOn"' in html and 'id="pfFertOn"' in html
        assert 'id="pfActiveOn"' not in html  # el estado solo se muestra al editar

    def test_edit_shows_history_rows_with_percentage_change(self, setup):
        client, org = setup
        product = ProductFactory(organization=org, price=Decimal('11'))
        _history(product, org, ['10.00', '11.00'])
        response = client.get(reverse('product-edit', args=[product.pk]))
        items = response.context['history_with_trend']
        assert [i['trend'] for i in items] == ['up', 'initial']
        assert items[0]['change_pct'] == Decimal('10.0') and items[1]['change_pct'] is None
        html = response.content.decode()
        assert 'id="pfSpark"' in html and 'id="pfPriceData"' in html
        assert 'data-price-delete' in html and 'chart.js' not in html

    def test_edit_without_history_shows_empty_state_and_no_chart(self, setup):
        client, org = setup
        product = ProductFactory(organization=org)
        html = client.get(reverse('product-edit', args=[product.pk])).content.decode()
        assert 'Sin histórico todavía' in html and 'id="pfSpark"' not in html

    def test_used_product_cannot_be_deleted_from_the_form(self, setup):
        client, org = setup
        product = ProductFactory(organization=org)
        assert 'id="pfDelete"' in client.get(reverse('product-edit', args=[product.pk])).content.decode()
        treatment = TreatmentFactory(organization=org)
        TreatmentProductFactory(treatment=treatment, product=product, organization=org)
        html = client.get(reverse('product-edit', args=[product.pk])).content.decode()
        assert 'id="pfDelete"' not in html and 'no se puede eliminar' in html

    def test_errors_show_banner_and_field_messages(self, setup):
        client, org = setup
        response = client.post(reverse('product-create'), {
            'name': '', 'product_type': '', 'price': '-1', 'spraying_dose': '2', 'spraying_dose_type': 'l_per_ha'})
        html = response.content.decode()
        assert response.status_code == 200
        assert 'Revisa los campos marcados.' in html and 'id="pfBanner"' in html
        assert 'El precio no puede ser negativo.' in html and 'tf-err' in html

    def test_missing_dose_error_is_shown_without_field_hint(self, setup):
        client, org = setup
        ptype = ProductTypeFactory(organization=org)
        response = client.post(reverse('product-create'), {'name': 'X', 'product_type': ptype.pk, 'price': '1'})
        html = response.content.decode()
        assert 'al menos una configuración válida' in html
        assert 'Revisa los campos marcados.' not in html

    def test_archive_switch_value_is_saved(self, setup):
        client, org = setup
        product = ProductFactory(organization=org)
        url = reverse('product-edit', args=[product.pk])
        data = {'name': product.name, 'product_type': product.product_type.pk, 'price': '1',
                'spraying_dose': '1', 'spraying_dose_type': 'l_per_ha'}
        assert client.post(url, data).status_code == 302  # sin is_active en el POST: archivado
        product.refresh_from_db()
        assert product.is_active is False
        assert client.post(url, {**data, 'is_active': 'on'}).status_code == 302
        product.refresh_from_db()
        assert product.is_active is True


JS_COST_CASES = [
    ('spraying', 'kg_per_ha', '2.5'), ('spraying', 'l_per_ha', '1.2'),
    ('spraying', 'kg_per_1000l', '0.75'), ('spraying', 'l_per_1000l', '0.3'),
    ('spraying', 'pct', '0.25'), ('fertigation', 'l_per_ha', '10'), ('fertigation', 'kg_per_ha', '4'),
]


@pytest.mark.django_db
class TestSummaryParity:
    """El resumen en vivo del formulario (JS) debe dar el mismo coste/ha que Product.cost_per_ha."""

    def test_water_constant_comes_from_the_model(self, setup):
        client, _ = setup
        html = client.get(reverse('product-create')).content.decode()
        assert re.search(rf'const WATER = {Product.REFERENCE_WATER_PER_HA};', html)

    @pytest.mark.skipif(shutil.which('node') is None, reason='requiere node')
    def test_js_cost_matches_cost_per_ha_for_every_dose_type(self, setup):
        client, org = setup
        html = client.get(reverse('product-create')).content.decode()
        water = re.search(r'const WATER = (\d+);', html).group(1)
        func = re.search(r'function costPerHa\(m\) \{.*?\n        \}\n', html, re.S).group(0)
        price = Decimal('3.40')
        script = (
            f'const WATER = {water}; const num = el => {{ const v = parseFloat(String(el.value).replace(",", ".")); '
            f'return Number.isFinite(v) ? v : 0; }}; const price = {{value: "{price}"}}; {func}'
            f'const cases = {json.dumps(JS_COST_CASES)}; '
            'console.log(JSON.stringify(cases.map(c => costPerHa({dose: {value: c[2]}, type: {value: c[1]}}))));'
        )
        out = subprocess.run(['node', '-e', script], capture_output=True, text=True, check=True).stdout
        for (kind, dose_type, dose), js_value in zip(JS_COST_CASES, json.loads(out)):
            product = ProductFactory(organization=org, price=price, **{
                f'{kind}_dose': Decimal(dose), f'{kind}_dose_type': dose_type})
            assert round(js_value, 2) == float(product.cost_per_ha(kind)), (kind, dose_type)


@pytest.mark.django_db
class TestPriceDelete:

    def _entry(self, org):
        product = ProductFactory(organization=org)
        return ProductPriceHistory.objects.create(product=product, price=Decimal('5'), organization=org,
                                                  effective_date=date.today())

    def test_delete_requires_post_with_csrf(self, setup):
        _, org = setup
        entry = self._entry(org)
        user = User.objects.get(username='formprod')
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(user)
        url = reverse('product-price-delete', args=[entry.pk])
        assert strict.get(url).status_code == 405
        assert strict.post(url).status_code == 403
        assert ProductPriceHistory.objects.filter(pk=entry.pk).exists()
        strict.get(reverse('product-edit', args=[entry.product_id]))  # emite la cookie CSRF
        token = strict.cookies['csrftoken'].value
        response = strict.post(url, {'csrfmiddlewaretoken': token})
        assert response.status_code == 302
        assert response.url == reverse('product-edit', args=[entry.product_id])
        assert not ProductPriceHistory.objects.filter(pk=entry.pk).exists()

    def test_other_organization_gets_404(self, setup):
        client, _ = setup
        entry = self._entry(OrganizationFactory(name='Otra organización'))
        assert client.post(reverse('product-price-delete', args=[entry.pk])).status_code == 404
        assert ProductPriceHistory.objects.filter(pk=entry.pk).exists()


@pytest.mark.django_db
class TestProductTypeForm:

    def test_new_form_uses_tf_pattern(self, setup):
        client, _ = setup
        html = client.get(reverse('product-type-create')).content.decode()
        assert 'tf-layout' in html and 'Crear tipo' in html and 'id="ptDelete"' not in html

    def test_edit_shows_product_count_and_blocks_delete_when_used(self, setup):
        client, org = setup
        ptype = ProductTypeFactory(organization=org)
        ProductFactory(organization=org, product_type=ptype)
        ProductFactory(organization=org, product_type=ptype)
        response = client.get(reverse('product-type-edit', args=[ptype.pk]))
        html = response.content.decode()
        assert response.context['product_count'] == 2
        assert '2 productos con este tipo' in html and 'id="ptDelete"' not in html

    def test_unused_type_offers_delete(self, setup):
        client, org = setup
        ptype = ProductTypeFactory(organization=org)
        html = client.get(reverse('product-type-edit', args=[ptype.pk])).content.decode()
        assert 'id="ptDelete"' in html and '0 productos con este tipo' in html

    def test_duplicate_name_shows_field_error(self, setup):
        client, org = setup
        ProductTypeFactory(organization=org, name='Fungicida')
        response = client.post(reverse('product-type-create'), {'name': 'fungicida'})
        html = response.content.decode()
        assert response.status_code == 200 and 'Ya tienes un tipo con ese nombre.' in html
