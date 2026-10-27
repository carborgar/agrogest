from datetime import timedelta
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from farm import weather_service as ws
from farm.tests.factories import *

GEOMETRY = '{"type": "Polygon", "coordinates": [[[-0.4, 39.4], [-0.39, 39.4], [-0.39, 39.41], [-0.4, 39.4]]]}'


def _hour(date, hr, wind=5, rain=0, temp=18.0):
    """Una hora con la forma que devuelve _parse_horaria."""
    return {
        'date': date.isoformat(), 'hour': f'{hr:02d}:00', 'temperature': temp,
        'wind_speed': float(wind), 'precipitation_probability': rain,
        'treatment_ok': rain < 20 and wind <= 20.0,
    }


def _level(hr, level):
    return {'hour': hr, 'level': level}


class TestLevelsAndWindows:

    @pytest.mark.parametrize('wind,rain,expected', [
        (20, 19, 'ok'),     # justo en el límite de treatment_ok
        (21, 0, 'warn'),
        (25, 49, 'warn'),
        (26, 0, 'bad'),
        (5, 50, 'bad'),
        (5, 20, 'warn'),
    ])
    def test_hour_level(self, wind, rain, expected):
        assert ws.hour_level(_hour(timezone.localdate(), 10, wind=wind, rain=rain)) == expected

    def test_windows_merge_consecutive_ok_hours(self):
        hours = [_level(8, 'bad'), _level(9, 'ok'), _level(10, 'ok'), _level(11, 'warn'),
                 _level(12, 'ok'), _level(13, 'ok'), _level(14, 'ok')]
        assert ws.ok_windows(hours) == [{'from': 9, 'to': 11}, {'from': 12, 'to': 15}]

    def test_windows_split_on_missing_hours(self):
        # Hoy, tras filtrar las horas pasadas, puede haber un hueco: 10 y 12 no son seguidas
        assert ws.ok_windows([_level(10, 'ok'), _level(12, 'ok')]) == [
            {'from': 10, 'to': 11}, {'from': 12, 'to': 13}]

    def test_no_ok_hours_means_no_windows(self):
        assert ws.ok_windows([_level(10, 'bad'), _level(11, 'warn')]) == []
        assert ws.ok_windows([]) == []


@pytest.mark.django_db
class TestWeatherSummary:

    @pytest.fixture(autouse=True)
    def _clean(self):
        cache.clear()
        with override_settings(AEMET_API_KEY='clave'):
            yield

    @staticmethod
    def _fields(org, n=2):
        return [FieldFactory(organization=org, geometry=GEOMETRY) for _ in range(n)]

    def test_fields_of_the_same_municipality_share_one_request(self):
        org = OrganizationFactory()
        fields = self._fields(org, 3)
        today = timezone.localdate()
        hourly = [_hour(today, 8)] + [_hour(today + timedelta(days=1), 9)]

        with patch.object(ws, '_nearest_municipio', return_value={'cod': '46250', 'nombre': 'Valencia'}), \
                patch.object(ws, 'get_hourly_for_municipio', return_value=hourly) as hourly_mock, \
                patch.object(ws.timezone, 'localtime', return_value=timezone.now().replace(hour=6, minute=0)):
            summary = ws.get_weather_summary(fields)

        assert hourly_mock.call_count == 1
        assert len(summary) == 1 and summary[0]['name'] == 'Valencia'
        assert len(summary[0]['fields']) == 3

    def test_one_entry_per_municipality_ordered_by_parcels(self):
        org = OrganizationFactory()
        a, b, c = self._fields(org, 3)
        today = timezone.localdate()

        def nearest(lat, lon, _calls=[]):
            _calls.append(1)
            return {'cod': '1', 'nombre': 'Uno'} if len(_calls) == 1 else {'cod': '2', 'nombre': 'Dos'}

        with patch.object(ws, '_nearest_municipio', side_effect=nearest), \
                patch.object(ws, 'get_hourly_for_municipio', return_value=[_hour(today + timedelta(days=1), 9)]):
            summary = ws.get_weather_summary([a, b, c])

        assert [m['name'] for m in summary] == ['Dos', 'Uno']  # Dos tiene 2 parcelas
        assert [len(m['fields']) for m in summary] == [2, 1]

    def test_all_24_hours_but_today_only_the_remaining_ones(self):
        org = OrganizationFactory()
        fields = self._fields(org, 1)
        now = timezone.now().replace(hour=10, minute=30)
        today, tomorrow = timezone.localdate(), timezone.localdate() + timedelta(days=1)
        hourly = [_hour(today, h) for h in (4, 9, 10, 15, 23)] + [_hour(tomorrow, h) for h in (0, 5, 23)]

        with patch.object(ws, '_nearest_municipio', return_value={'cod': '1', 'nombre': 'Uno'}), \
                patch.object(ws, 'get_hourly_for_municipio', return_value=hourly), \
                patch.object(ws.timezone, 'localtime', return_value=now):
            days = ws.get_weather_summary(fields)[0]['days']

        assert [d['label'] for d in days] == ['Hoy', 'Mañana']
        assert [h['hour'] for h in days[0]['hours']] == [10, 15, 23]   # sin las pasadas (4, 9)
        assert [h['hour'] for h in days[1]['hours']] == [0, 5, 23]     # mañana, completo, madrugada y noche incluidas

    def test_empty_without_key_without_geometry_or_without_data(self):
        org = OrganizationFactory()
        fields = self._fields(org, 1)
        no_geo = FieldFactory(organization=org, geometry='')

        with override_settings(AEMET_API_KEY=''):
            assert ws.get_weather_summary(fields) == []
        with patch.object(ws, '_nearest_municipio', return_value={'cod': '1', 'nombre': 'Uno'}), \
                patch.object(ws, 'get_hourly_for_municipio', return_value=[]):
            assert ws.get_weather_summary(fields) == []
        assert ws.municipality_for_field(no_geo) is None

    def test_hourly_is_cached_and_failures_do_not_hammer_aemet(self):
        with patch.object(ws, '_aemet_fetch', return_value=None) as fetch:
            assert ws.get_hourly_for_municipio('9') == []
            assert ws.get_hourly_for_municipio('9') == []
        assert fetch.call_count == 1


@pytest.mark.django_db
class TestWeatherSummaryApi:

    @pytest.fixture
    def user(self, client):
        org = OrganizationFactory()
        user = User.objects.create_user(username='tiempo', password='pass', organization=org)
        client.force_login(user)
        return user

    def test_requires_login(self, client):
        assert client.get(reverse('api-weather-summary')).status_code == 401

    def test_404_when_module_is_off(self, client, user):
        with patch('core.models.is_enabled', return_value=False):
            assert client.get(reverse('api-weather-summary')).status_code == 404

    def test_only_fields_of_the_user_with_geometry(self, client, user):
        mine = FieldFactory(organization=user.organization, geometry=GEOMETRY)
        FieldFactory(organization=user.organization, geometry='')
        FieldFactory(organization=OrganizationFactory(name='Otra'), geometry=GEOMETRY)
        payload = [{'name': 'Valencia', 'fields': [mine.name], 'days': []}]

        with patch('core.models.is_enabled', return_value=True), \
                patch('farm.weather_service.get_weather_summary', return_value=payload) as build:
            response = client.get(reverse('api-weather-summary'))

        assert response.json() == {'municipalities': payload}
        assert [f.pk for f in build.call_args.args[0]] == [mine.pk]
