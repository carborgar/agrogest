import pytest
from django.urls import reverse

from accounts.models import User
from farm.tests.factories import *


@pytest.mark.django_db
def test_calendar_page_has_desktop_and_mobile_containers(client):
    org = OrganizationFactory()
    client.force_login(User.objects.create_user(username='calpage', password='pass', organization=org))
    response = client.get(reverse('treatment-calendar'))
    assert response.status_code == 200
    html = response.content.decode()
    for marker in ('id="calendar"', 'id="cal-mobile"', 'id="cm-grid"', 'id="cal-filters-wrap"', 'id="detail-date"'):
        assert marker in html


@pytest.mark.django_db
def test_calendar_page_uses_design_language(client):
    """Filtros como panel inferior en móvil, FAB de «Nuevo» y modal con resumen dt-*, sin Bootstrap suelto."""
    org = OrganizationFactory()
    client.force_login(User.objects.create_user(username='caldesign', password='pass', organization=org))
    html = client.get(reverse('treatment-calendar')).content.decode()
    for marker in ('offcanvas-md offcanvas-bottom tl-filters', 'filter-check-dropdown', 'id="filter-clear"',
                   'id="cm-new"', 'tl-fab', 'dt-summary card card-flat', 'id="status-container"'):
        assert marker in html
    own = html[html.index('id="cal-filters-wrap"'):]
    assert 'shadow-sm' not in own and 'bg-light' not in own and 'style="' not in own


@pytest.mark.django_db
def test_calendar_chips_show_active_state_with_check(client):
    """Cada chip de Tipo y Estado lleva su ✓ (visible solo activo) y los filtros siguen leyendo las casillas."""
    org = OrganizationFactory()
    client.force_login(User.objects.create_user(username='calchips', password='pass', organization=org))
    html = client.get(reverse('treatment-calendar')).content.decode()
    chips = html.count('class="btn btn-outline-secondary cal-chip"')
    assert chips >= 4
    assert html.count('cal-chip-check') == chips
    assert html.count('class="btn-check status-checkbox"') == 3
    assert 'btn-check treatment-type-checkbox' in html
