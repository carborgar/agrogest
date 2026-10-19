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
