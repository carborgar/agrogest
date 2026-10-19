from datetime import date, timedelta

import pytest
from django.urls import reverse

from accounts.models import User
from farm.models import Treatment
from farm.tests.factories import *


def _days(n):
    return date.today() + timedelta(days=n)


@pytest.fixture
def setup(client):
    org = OrganizationFactory()
    user = User.objects.create_user(username='cal', password='pass', organization=org)
    client.force_login(user)
    field = FieldFactory(organization=org)
    machine = MachineFactory(organization=org)
    return client, org, field, machine


def _spray(org, field, machine, **kwargs):
    return SprayingTreatmentFactory(organization=org, field=field, machine=machine, **kwargs)


def _events(client, start, end, **params):
    response = client.get(reverse('api-calendar-treatments'),
                          {'start': start.isoformat(), 'end': end.isoformat(), **params})
    assert response.status_code == 200
    return response.json()


@pytest.mark.django_db
class TestCalendarApi:

    def test_requires_login_with_401_json(self, client):
        for url in (reverse('api-calendar-treatments'),
                    reverse('api-treatment-detail', args=[1])):
            assert client.get(url).status_code == 401
        assert client.post(reverse('api-treatment-move', args=[1]), {'date': '2026-01-01'}).status_code == 401

    def test_completed_treatment_is_placed_on_finish_date(self, setup):
        client, org, field, machine = setup
        # Prevista en un mes, terminada en otro: debe salir en el mes de finalización
        t = _spray(org, field, machine, date=_days(-40), finish_date=_days(-5))

        in_finish_range = _events(client, _days(-10), _days(0))
        in_planned_range = _events(client, _days(-45), _days(-35))

        assert [e['id'] for e in in_finish_range] == [t.pk]
        assert in_finish_range[0]['date'] == _days(-5).isoformat()
        assert in_finish_range[0]['status'] == 'completed'
        assert in_finish_range[0]['editable'] is True
        assert in_planned_range == []

    def test_end_is_exclusive(self, setup):
        client, org, field, machine = setup
        t = _spray(org, field, machine, date=_days(5))
        assert _events(client, _days(0), _days(5)) == []
        assert [e['id'] for e in _events(client, _days(0), _days(6))] == [t.pk]

    def test_status_is_computed_from_dates_and_filterable(self, setup):
        client, org, field, machine = setup
        stale = _spray(org, field, machine, date=_days(-1))
        Treatment.objects.filter(pk=stale.pk).update(status='pending')  # estado desfasado en BD
        _spray(org, field, machine, date=_days(2))

        events = _events(client, _days(-5), _days(10))
        assert {e['id']: e['status'] for e in events}[stale.pk] == 'delayed'

        only_delayed = _events(client, _days(-5), _days(10), statuses='delayed')
        assert [e['id'] for e in only_delayed] == [stale.pk]
        assert _events(client, _days(-5), _days(10), statuses='none') == []

    def test_event_includes_field_and_type(self, setup):
        client, org, field, machine = setup
        _spray(org, field, machine, date=_days(1))
        event = _events(client, _days(0), _days(3))[0]
        assert event['field_name'] == field.name
        assert event['type'] == 'spraying'
        assert event['type_display'] == 'Pulverización'
        assert event['editable'] is True

    def test_other_organization_is_not_visible(self, setup):
        client, org, field, machine = setup
        other = OrganizationFactory(name='Otra organización')
        other_field = FieldFactory(organization=other)
        SprayingTreatmentFactory(organization=other, field=other_field,
                                 machine=MachineFactory(organization=other), date=_days(1))
        assert _events(client, _days(0), _days(3)) == []

    def test_detail_includes_loads_and_per_load_doses(self, setup):
        client, org, field, machine = setup
        t = _spray(org, field, machine, date=_days(1))
        data = client.get(reverse('api-treatment-detail', args=[t.pk])).json()
        assert data['can_finish'] is True
        assert data['machine_capacity'] == machine.capacity
        assert data['field_crop'] == field.crop
        assert 'loads' in data


@pytest.mark.django_db
class TestMoveTreatment:

    def test_move_updates_date_and_status(self, setup):
        client, org, field, machine = setup
        t = _spray(org, field, machine, date=_days(3))

        response = client.post(reverse('api-treatment-move', args=[t.pk]), {'date': _days(-2).isoformat()})

        assert response.status_code == 200
        t.refresh_from_db()
        assert t.date == _days(-2)
        assert response.json()['status'] == 'delayed'
        assert t.status == 'delayed'

    def test_moving_completed_changes_finish_date_only(self, setup):
        client, org, field, machine = setup
        t = _spray(org, field, machine, date=_days(-3), finish_date=_days(-2))

        response = client.post(reverse('api-treatment-move', args=[t.pk]), {'date': _days(-1).isoformat()})

        assert response.status_code == 200
        t.refresh_from_db()
        assert t.finish_date == _days(-1)
        assert t.date == _days(-3)
        assert t.status == 'completed'
        assert response.json() == {'success': True, 'date': _days(-1).isoformat(), 'status': 'completed'}

    def test_invalid_date_and_get_not_allowed(self, setup):
        client, org, field, machine = setup
        t = _spray(org, field, machine, date=_days(3))
        url = reverse('api-treatment-move', args=[t.pk])
        assert client.post(url, {'date': 'no-es-fecha'}).status_code == 400
        assert client.get(url).status_code == 405

    def test_cannot_move_other_organization_treatment(self, setup):
        client, org, field, machine = setup
        other = OrganizationFactory(name='Otra organización')
        t = SprayingTreatmentFactory(organization=other, field=FieldFactory(organization=other),
                                     machine=MachineFactory(organization=other), date=_days(3))
        response = client.post(reverse('api-treatment-move', args=[t.pk]), {'date': _days(5).isoformat()})
        assert response.status_code == 404


@pytest.mark.django_db
class TestCreateWithPresetDate:

    def test_date_query_param_preselects_date(self, setup):
        client, *_ = setup
        response = client.get(reverse('treatment-create'), {'date': '2026-11-03'})
        assert response.status_code == 200
        assert response.context['form']['date'].value() == '2026-11-03'

    def test_invalid_date_param_is_ignored(self, setup):
        client, *_ = setup
        response = client.get(reverse('treatment-create'), {'date': 'xx'})
        assert response.status_code == 200
        assert response.context['form']['date'].value() == date.today().strftime('%Y-%m-%d')


@pytest.mark.django_db
class TestCalendarPage:

    def test_page_renders_with_filters_and_loads_fullcalendar_only_here(self, setup):
        client, org, field, machine = setup
        html = client.get(reverse('treatment-calendar')).content.decode()
        assert 'id="calendar"' in html
        assert f'id="filter-field-{field.pk}"' in html
        assert 'id="pane-day"' in html and 'id="pane-detail"' in html
        assert 'fullcalendar@6' in html
        # El resto de páginas ya no cargan FullCalendar
        other = client.get(reverse('treatment-list'), {'date_from': '', 'date_to': ''}).content.decode()
        assert 'fullcalendar' not in other
