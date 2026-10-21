from datetime import date, timedelta

import pytest
from django.urls import reverse

from accounts.models import User
from farm.models import Treatment
from farm.tests.factories import *

# Sin límites de fecha: evita que el rango por defecto (año en curso) afecte a los tests
NO_DATES = {'date_from': '', 'date_to': ''}
ALL_STATUSES = ['pending', 'delayed', 'completed']


def _days(n):
    return date.today() + timedelta(days=n)


@pytest.fixture
def setup(client):
    org = OrganizationFactory()
    user = User.objects.create_user(username='lista', password='pass', organization=org)
    client.force_login(user)
    field = FieldFactory(organization=org)
    machine = MachineFactory(organization=org)
    return client, org, field, machine


def _spray(org, field, machine, **kwargs):
    return SprayingTreatmentFactory(organization=org, field=field, machine=machine, **kwargs)


def _get(client, **params):
    return client.get(reverse('treatment-list'), {**NO_DATES, **params})


@pytest.mark.django_db
class TestTreatmentListView:

    def test_stale_pending_status_goes_to_overdue_group(self, setup):
        client, org, field, machine = setup
        t = _spray(org, field, machine, date=_days(-1))
        # Estado desfasado: en BD sigue como 'pending' aunque la fecha ya pasó
        Treatment.objects.filter(pk=t.pk).update(status='pending')

        response = _get(client)

        treatments = list(response.context['treatments'])
        assert [x.pk for x in treatments] == [t.pk]
        assert treatments[0].urgency_group == 0

    def test_default_order_by_urgency(self, setup):
        client, org, field, machine = setup
        late_old = _spray(org, field, machine, name='late_old', date=_days(-10))
        late_new = _spray(org, field, machine, name='late_new', date=_days(-2))
        soon = _spray(org, field, machine, name='soon', date=_days(3))
        later = _spray(org, field, machine, name='later', date=_days(30))
        done_old = _spray(org, field, machine, name='done_old', date=_days(-20), finish_date=_days(-15))
        done_new = _spray(org, field, machine, name='done_new', date=_days(-20), finish_date=_days(-5))

        response = _get(client, status=ALL_STATUSES)

        names = [t.name for t in response.context['treatments']]
        assert names == ['late_old', 'late_new', 'soon', 'later', 'done_new', 'done_old']
        assert response.context['show_groups'] is True

    def test_completed_hidden_by_default_and_last_when_selected(self, setup):
        client, org, field, machine = setup
        pending = _spray(org, field, machine, name='pend', date=_days(5))
        done = _spray(org, field, machine, name='done', date=_days(-3), finish_date=_days(-1))

        default = _get(client)
        assert [t.pk for t in default.context['treatments']] == [pending.pk]

        with_completed = _get(client, status=ALL_STATUSES)
        assert [t.pk for t in with_completed.context['treatments']] == [pending.pk, done.pk]

    def test_name_sort_disables_groups(self, setup):
        client, org, field, machine = setup
        _spray(org, field, machine, date=_days(5))

        response = _get(client, sort='name_asc')

        assert response.context['show_groups'] is False

    def test_group_counts_cover_whole_filtered_set_not_page(self, setup):
        client, org, field, machine = setup
        for i in range(30):
            _spray(org, field, machine, date=_days(-1 - i))  # 30 atrasados
        for i in range(3):
            _spray(org, field, machine, date=_days(2 + i))  # 3 próximos

        response = _get(client)

        assert len(response.context['treatments']) == 24
        assert response.context['group_counts'] == {0: 30, 1: 3, 2: 0, 3: 0}
        assert response.context['total_count'] == 33

    def test_overdue_shown_outside_date_range_but_others_not(self, setup):
        client, org, field, machine = setup
        overdue = _spray(org, field, machine, name='overdue', date=_days(-400))
        old_done = _spray(org, field, machine, name='old_done', date=_days(-400), finish_date=_days(-399))
        future = _spray(org, field, machine, name='future', date=_days(5))

        response = client.get(reverse('treatment-list'), {
            'date_from': _days(0).isoformat(),
            'date_to': _days(10).isoformat(),
            'status': ALL_STATUSES,
        })

        assert {t.pk for t in response.context['treatments']} == {overdue.pk, future.pk}

    def test_overdue_still_respects_other_filters(self, setup):
        client, org, field, machine = setup
        other_field = FieldFactory(organization=org)
        _spray(org, field, machine, name='a', date=_days(-3))
        b = _spray(org, other_field, machine, name='b', date=_days(-3))

        response = _get(client, field=[other_field.pk])

        assert [t.pk for t in response.context['treatments']] == [b.pk]

    def test_renders_fertigation_no_machine_and_completed(self, setup):
        client, org, field, machine = setup
        fert = FertigationTreatmentFactory(organization=org, field=field, name='fert', date=_days(2))
        FertigationTreatmentProductFactory(treatment=fert, product=FertigationProductFactory(organization=org))
        no_machine = SprayingTreatmentFactory(organization=org, field=field, machine=None, name='sin_maq', date=_days(-1))
        spray = _spray(org, field, machine, name='spray', date=_days(4))
        SprayingTreatmentProductFactory(treatment=spray, product=SprayingProductFactory(organization=org))
        done = _spray(org, field, machine, name='hecho', date=_days(-5), finish_date=_days(-3))
        SprayingTreatmentProductFactory(treatment=done, product=SprayingProductFactory(organization=org))

        response = _get(client, status=ALL_STATUSES)

        assert response.status_code == 200
        content = response.content.decode()
        for name in ('fert', 'sin_maq', 'spray', 'hecho'):
            assert name in content
        assert 'Atrasados' in content and 'Completados' in content


@pytest.mark.django_db
class TestTreatmentListTabs:

    def test_default_tab_is_todo_with_count(self, setup):
        client, org, field, machine = setup
        _spray(org, field, machine, date=_days(-2))
        _spray(org, field, machine, date=_days(3))
        _spray(org, field, machine, date=_days(-5), finish_date=_days(-4))

        response = _get(client)

        assert response.context['status_tab'] == 'todo'
        assert response.context['todo_count'] == 2
        assert response.context['status_subfilter'] == ''

    def test_done_tab_shows_only_completed_and_keeps_todo_count(self, setup):
        client, org, field, machine = setup
        _spray(org, field, machine, date=_days(3))
        done = _spray(org, field, machine, date=_days(-5), finish_date=_days(-4))

        response = _get(client, status='completed')

        assert response.context['status_tab'] == 'done'
        assert [t.pk for t in response.context['treatments']] == [done.pk]
        assert response.context['todo_count'] == 1

    def test_tab_urls_keep_other_filters_and_drop_page(self, setup):
        client, org, field, machine = setup
        _spray(org, field, machine, date=_days(3))

        response = _get(client, field=[field.pk], status='completed', page='1')

        assert 'status' not in response.context['todo_url']
        assert f'field={field.pk}' in response.context['todo_url']
        assert 'status=completed' in response.context['done_url']
        assert 'page' not in response.context['done_url']

    def test_legacy_single_status_link_shows_subfilter(self, setup):
        client, org, field, machine = setup
        late = _spray(org, field, machine, date=_days(-2))
        _spray(org, field, machine, date=_days(3))

        response = _get(client, status='delayed')

        assert response.context['status_tab'] == 'todo'
        assert response.context['status_subfilter'] == 'Atrasado'
        assert [t.pk for t in response.context['treatments']] == [late.pk]

    def test_card_view_and_switcher_are_gone(self, setup):
        client, org, field, machine = setup
        _spray(org, field, machine, date=_days(3))

        content = _get(client).content.decode()

        assert 'cardView' not in content and 'view-switcher' not in content
        assert 'tl-date--1' in content  # fecha en bloque de color del grupo «Próximos 7 días»
