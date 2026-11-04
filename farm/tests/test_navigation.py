"""Menú: una sola definición (farm/navigation.py) para el lateral, la barra inferior y la hoja «Más»."""
import pytest
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse

from accounts.models import User
from core.models import FeatureFlag
from farm.tests.factories import OrganizationFactory


@pytest.fixture
def logged(client):
    cache.clear()
    org = OrganizationFactory()
    user = User.objects.create_user(username='menu', password='pass', organization=org)
    client.force_login(user)
    return client


def _ctx(client, url_name='field_list'):
    return client.get(reverse(url_name)).context


def _keys(items):
    return [i['key'] for i in items]


@pytest.mark.django_db
class TestNavigation:

    def test_tabs_in_field_order(self, logged):
        ctx = _ctx(logged)
        assert _keys(ctx['nav_tabs']) == ['nav_home', 'nav_treatments', 'nav_shopping', 'nav_calendar']
        assert [t['tab_label'] for t in ctx['nav_tabs']] == ['Inicio', 'Tratamientos', 'Preparar', 'Calendario']

    def test_groups_by_task(self, logged):
        titles = [g['title'] for g in _ctx(logged)['nav_groups']]
        assert titles == ['', 'Tratamientos', 'Explotación', 'Economía', 'Configuración']

    def test_more_sheet_has_no_tab_duplicates(self, logged):
        ctx = _ctx(logged)
        more = [k for g in ctx['nav_more'] for k in _keys(g['items'])]
        assert not set(more) & set(_keys(ctx['nav_tabs']))
        assert 'nav_products' in more
        # Inicio solo tiene una pestaña: su grupo no sale en «Más»
        assert '' not in [g['title'] for g in ctx['nav_more']]

    def test_active_item_and_more_tab(self, logged):
        ctx = _ctx(logged, 'product-list')
        active = [i['key'] for g in ctx['nav_groups'] for i in g['items'] if i['active']]
        assert active == ['nav_products']
        assert ctx['nav_more_active'] is True
        assert _ctx(logged, 'treatment-list')['nav_more_active'] is False

    def test_stats_active_from_url(self, logged):
        ctx = _ctx(logged, 'yearly-stats')
        assert [i['key'] for g in ctx['nav_groups'] for i in g['items'] if i['active']] == ['nav_stats']

    def test_weather_only_with_flag(self, logged):
        keys = lambda c: [k for g in c['nav_groups'] for k in _keys(g['items'])]
        assert 'nav_weather' not in keys(_ctx(logged))
        FeatureFlag.objects.create(name='WEATHER', enabled=True)
        cache.clear()
        assert 'nav_weather' in keys(_ctx(logged))

    @override_settings(GEMINI_API_KEY='x')
    def test_ai_group_only_when_configured(self, logged):
        titles = [g['title'] for g in _ctx(logged)['nav_groups']]
        assert 'Herramientas' in titles

    def test_rendered_menu(self, logged):
        # Página sin enlaces propios a estas secciones: solo cuenta el menú
        html = logged.get(reverse('accounts:notification-preferences')).content.decode()
        assert 'gastosMenu' not in html                       # Gastos ya no es submenú
        assert html.count('href="%s"' % reverse('expense-list')) == 2   # lateral + hoja
        assert html.count('href="%s"' % reverse('treatment-shopping-list')) == 2  # lateral + pestaña
        assert 'sidebar-collapse-section d-none d-xl-block' in html
        # Notificaciones va en el menú del usuario, no entre las secciones del lateral
        sidebar = html[html.index('desktop-menu-nav-container'):html.index('sidebar-collapse-section')]
        assert reverse('accounts:notification-inbox') not in sidebar
