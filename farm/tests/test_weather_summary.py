from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse

from accounts.models import User
from farm import weather_service as ws
from farm.tests.factories import *

GEOMETRY = '{"type": "Polygon", "coordinates": [[[-0.4, 39.4], [-0.39, 39.4], [-0.39, 39.41], [-0.4, 39.4]]]}'
DAILY = [{'date': '2026-10-27', 'hours': []}]


class TestThresholds:
    """Los umbrales están en un solo sitio; todo lo demás (horas, días, JS) usa `level`."""

    @pytest.mark.parametrize('rain,wind,expected', [
        (19, 20, 'ok'),      # justo en el límite
        (0, 21, 'warn'),
        (49, 25, 'warn'),
        (20, 5, 'warn'),
        (0, 26, 'bad'),
        (50, 5, 'bad'),
    ])
    def test_treatment_level(self, rain, wind, expected):
        assert ws.treatment_level(rain, wind) == expected
        assert ws.treatment_ok(rain, wind) == (expected == 'ok')

    @pytest.mark.parametrize('wind,expected', [(10, 0), (15, 1), (19.9, 2), (20, 3)])
    def test_wind_level(self, wind, expected):
        assert ws.wind_level(wind) == expected

    def test_synthesized_hours_carry_level(self):
        hours = ws._synthesize_hours('2026-11-01', {
            'max_precipitation_probability': 60, 'max_wind_speed': 8.0, 'min_temp': 10, 'max_temp': 20})
        assert {h['level'] for h in hours} == {'bad'}
        assert {h['wind_level'] for h in hours} == {0}


@pytest.mark.django_db
class TestWeatherSummary:

    @pytest.fixture(autouse=True)
    def _clean(self):
        cache.clear()

    @staticmethod
    def _fields(org, n):
        return [FieldFactory(organization=org, geometry=GEOMETRY) for _ in range(n)]

    def test_fields_of_the_same_municipality_share_one_forecast(self):
        fields = self._fields(OrganizationFactory(), 3)

        with patch.object(ws, '_nearest_municipio', return_value={'cod': '46250', 'nombre': 'Valencia'}), \
                patch.object(ws, 'get_forecast', return_value=DAILY) as forecast:
            summary = ws.get_weather_summary(fields)

        assert forecast.call_count == 1
        [muni] = summary['municipalities']
        assert muni['name'] == 'Valencia' and muni['daily'] == DAILY
        assert muni['fields'] == [{'id': f.id, 'name': f.name} for f in fields]
        assert summary['errors'] == []

    def test_one_entry_per_municipality_ordered_by_parcels(self):
        a, b, c = self._fields(OrganizationFactory(), 3)
        municipios = iter([{'cod': '1', 'nombre': 'Uno'}, {'cod': '2', 'nombre': 'Dos'}, {'cod': '2', 'nombre': 'Dos'}])

        with patch.object(ws, '_nearest_municipio', side_effect=lambda *_: next(municipios)), \
                patch.object(ws, 'get_forecast', return_value=DAILY):
            summary = ws.get_weather_summary([a, b, c])

        assert [(m['name'], len(m['fields'])) for m in summary['municipalities']] == [('Dos', 2), ('Uno', 1)]

    def test_fields_without_forecast_or_location_are_reported(self):
        org = OrganizationFactory()
        ok, no_data = self._fields(org, 2)
        broken = FieldFactory(organization=org, geometry='{"type": "LineString"}')
        municipios = iter([{'cod': '1', 'nombre': 'Uno'}, {'cod': '2', 'nombre': 'Dos'}])

        with patch.object(ws, '_nearest_municipio', side_effect=lambda *_: next(municipios)), \
                patch.object(ws, 'get_forecast', side_effect=lambda cod: DAILY if cod == '1' else None):
            summary = ws.get_weather_summary([ok, no_data, broken])

        assert [m['name'] for m in summary['municipalities']] == ['Uno']
        assert sorted(f for e in summary['errors'] for f in e['fields']) == sorted([no_data.name, broken.name])

    def test_forecast_is_cached_and_failures_do_not_hammer_aemet(self):
        with patch.object(ws, '_build_forecast', return_value=None) as build:
            assert ws.get_forecast('9') is None
            assert ws.get_forecast('9') is None
        assert build.call_count == 1

        with patch.object(ws, '_build_forecast', return_value=DAILY) as build:
            assert ws.get_forecast('8') == DAILY
            assert ws.get_forecast('8') == DAILY
        assert build.call_count == 1


@pytest.mark.django_db
class TestWeatherApiAndPage:

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

    @override_settings(AEMET_API_KEY='')
    def test_503_without_aemet_key(self, client, user):
        with patch('core.models.is_enabled', return_value=True):
            response = client.get(reverse('api-weather-summary'))
        assert response.status_code == 503
        assert 'clave de AEMET' in response.json()['error']

    @override_settings(AEMET_API_KEY='clave')
    def test_only_fields_of_the_user_with_geometry(self, client, user):
        mine = FieldFactory(organization=user.organization, geometry=GEOMETRY)
        FieldFactory(organization=user.organization, geometry='')
        FieldFactory(organization=OrganizationFactory(name='Otra'), geometry=GEOMETRY)
        payload = {'municipalities': [], 'errors': []}

        with patch('core.models.is_enabled', return_value=True), \
                patch('farm.weather_service.get_weather_summary', return_value=payload) as build:
            response = client.get(reverse('api-weather-summary'))

        assert response.json() == payload
        assert [f.pk for f in build.call_args.args[0]] == [mine.pk]

    def test_per_field_endpoint_is_gone(self):
        from django.urls import NoReverseMatch
        with pytest.raises(NoReverseMatch):
            reverse('api-field-weather', args=[1])

    def test_weather_page_lists_only_own_fields(self, client, user):
        mine = FieldFactory(organization=user.organization, geometry=GEOMETRY, name='Mía')
        FieldFactory(organization=OrganizationFactory(name='Otra'), geometry=GEOMETRY, name='Ajena')

        with patch('core.models.is_enabled', return_value=True):
            response = client.get(reverse('weather-overview'))

        assert [f['id'] for f in response.context['fields_with_geo']] == [mine.id]
        assert 'Ajena' not in response.content.decode()
