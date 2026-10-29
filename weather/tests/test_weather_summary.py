import logging
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from weather import services as ws
from weather import treatment_rules as rules
from weather.aemet.client import AemetAuthError, AemetRateLimitError, AemetUnavailableError
from weather.aemet.parsers import synthesize_hours
from farm.tests.factories import *

GEOMETRY = '{"type": "Polygon", "coordinates": [[[-0.4, 39.4], [-0.39, 39.4], [-0.39, 39.41], [-0.4, 39.4]]]}'
DAILY = [{'date': '2026-10-27', 'hours': []}]
UPDATED = timezone.now()
FORECAST = {'daily': DAILY, 'updated_at': UPDATED, 'stale': False}


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
        assert rules.treatment_level(rain, wind) == expected
        assert rules.treatment_ok(rain, wind) == (expected == 'ok')

    @pytest.mark.parametrize('wind,expected', [(10, 0), (15, 1), (19.9, 2), (20, 3)])
    def test_wind_level(self, wind, expected):
        assert rules.wind_level(wind) == expected

    def test_synthesized_hours_carry_level(self):
        hours = synthesize_hours('2026-11-01', {
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
                patch.object(ws, 'get_forecast', return_value=FORECAST) as forecast:
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
                patch.object(ws, 'get_forecast', return_value=FORECAST):
            summary = ws.get_weather_summary([a, b, c])

        assert [(m['name'], len(m['fields'])) for m in summary['municipalities']] == [('Dos', 2), ('Uno', 1)]

    def test_fields_without_forecast_or_location_are_reported(self):
        org = OrganizationFactory()
        ok, no_data = self._fields(org, 2)
        broken = FieldFactory(organization=org, geometry='{"type": "LineString"}')
        municipios = iter([{'cod': '1', 'nombre': 'Uno'}, {'cod': '2', 'nombre': 'Dos'}])

        def fake_forecast(cod):
            if cod == '1':
                return FORECAST
            raise AemetUnavailableError('/x', 'timeout')

        with patch.object(ws, '_nearest_municipio', side_effect=lambda *_: next(municipios)), \
                patch.object(ws, 'get_forecast', side_effect=fake_forecast):
            summary = ws.get_weather_summary([ok, no_data, broken])

        assert [m['name'] for m in summary['municipalities']] == ['Uno']
        assert sorted(f for e in summary['errors'] for f in e['fields']) == sorted([no_data.name, broken.name])
        reasons = {e['reason']: e['fields'] for e in summary['errors']}
        assert reasons[ws.REASON_UNAVAILABLE] == [no_data.name]
        assert reasons[ws.REASON_LOCATION] == [broken.name]

    def test_summary_carries_freshness(self):
        [field] = self._fields(OrganizationFactory(), 1)
        stale = {**FORECAST, 'stale': True}
        with patch.object(ws, '_nearest_municipio', return_value={'cod': '1', 'nombre': 'Uno'}), \
                patch.object(ws, 'get_forecast', return_value=stale):
            [muni] = ws.get_weather_summary([field])['municipalities']
        assert muni['stale'] is True and muni['updated_at'] == UPDATED.isoformat()

    def test_catalogue_failure_is_reported_with_its_reason(self):
        [field] = self._fields(OrganizationFactory(), 1)
        with patch.object(ws, '_get_municipios', side_effect=AemetAuthError('/api/maestro/municipios', 'API key invalido', 401)):
            summary = ws.get_weather_summary([field])
        assert summary['errors'] == [{'reason': ws.REASON_AUTH, 'fields': [field.name]}]


@pytest.mark.django_db
class TestForecastCache:

    @pytest.fixture(autouse=True)
    def _clean(self):
        cache.clear()

    def test_fresh_forecast_is_reused(self):
        with patch.object(ws, '_build_forecast', return_value=DAILY) as build:
            first = ws.get_forecast('8')
            second = ws.get_forecast('8')
        assert build.call_count == 1
        assert first['daily'] == second['daily'] == DAILY and not second['stale']

    def test_expired_forecast_is_refreshed(self):
        cache.set('aemet:forecast:8', {'daily': [], 'updated_at': timezone.now() - timedelta(hours=1)})
        with patch.object(ws, '_build_forecast', return_value=DAILY) as build:
            assert ws.get_forecast('8')['daily'] == DAILY
        assert build.call_count == 1

    def test_last_good_forecast_is_served_when_aemet_fails(self, caplog):
        old = timezone.now() - timedelta(hours=3)
        cache.set('aemet:forecast:8', {'daily': DAILY, 'updated_at': old})
        with patch.object(ws, '_build_forecast', side_effect=AemetUnavailableError('/p', 'timeout')), \
                caplog.at_level(logging.WARNING, logger='weather.services'):
            result = ws.get_forecast('8')
        assert result == {'daily': DAILY, 'updated_at': old, 'stale': True}
        [record] = caplog.records
        assert record.levelno == logging.WARNING
        assert 'municipio 8' in record.getMessage() and 'timeout' in record.getMessage()

    def test_failure_without_saved_forecast_raises_and_waits_before_retrying(self, caplog):
        error = AemetRateLimitError('/p', 'Límite de peticiones', 429)
        with patch.object(ws, '_build_forecast', side_effect=error) as build, \
                caplog.at_level(logging.WARNING, logger='weather.services'):
            with pytest.raises(AemetRateLimitError):
                ws.get_forecast('9')
            with pytest.raises(AemetRateLimitError):   # dentro de la espera: ni llama ni repite el log
                ws.get_forecast('9')
        assert build.call_count == 1
        assert len(caplog.records) == 1

    def test_auth_errors_are_logged_as_error(self, caplog):
        with patch.object(ws, '_build_forecast', side_effect=AemetAuthError('/p', 'API key invalido', 401)), \
                caplog.at_level(logging.WARNING, logger='weather.services'):
            with pytest.raises(AemetAuthError):
                ws.get_forecast('7')
        [record] = caplog.records
        assert record.levelno == logging.ERROR and 'API key invalido' in record.getMessage()


@pytest.mark.django_db
class TestBuildForecast:

    @pytest.fixture(autouse=True)
    def _clean(self):
        cache.clear()

    def test_uses_the_other_part_when_one_fails_and_logs_it(self, caplog):
        day = {'date': '2026-11-01', 'max_precipitation_probability': 0, 'max_wind_speed': 5.0,
               'min_temp': 10, 'max_temp': 20, 'dominant_code': '11'}

        def fetch(path):
            if '/horaria/' in path:
                raise AemetUnavailableError(path, 'HTTP 500')
            return 'diaria'

        with patch.object(ws, 'aemet_fetch', side_effect=fetch), \
                patch.object(ws, 'parse_diaria', return_value=[day]), \
                caplog.at_level(logging.WARNING, logger='weather.services'):
            daily = ws._build_forecast('5')
        assert [d['date'] for d in daily] == ['2026-11-01']
        assert 'horaria' in caplog.text and 'HTTP 500' in caplog.text

    def test_unparseable_answer_is_a_bad_response(self):
        with patch.object(ws, 'aemet_fetch', return_value={'inesperado': True}), \
                patch.object(ws, 'parse_horaria', side_effect=KeyError('prediccion')), \
                patch.object(ws, 'parse_diaria', side_effect=KeyError('prediccion')):
            with pytest.raises(ws.AemetBadResponseError, match='no se pudo interpretar'):
                ws._build_forecast('5')


@pytest.mark.django_db
class TestMunicipality:

    @pytest.fixture(autouse=True)
    def _clean(self):
        cache.clear()

    CATALOGUE = [{'cod': '46250', 'nombre': 'Valencia', 'lat': 39.47, 'lon': -0.38},
                 {'cod': '41091', 'nombre': 'Sevilla', 'lat': 37.39, 'lon': -5.99}]

    def test_nearest_is_remembered_and_follows_new_coordinates(self):
        with patch.object(ws, '_get_municipios', return_value=self.CATALOGUE) as catalogue:
            assert ws._nearest_municipio(39.4, -0.4)['nombre'] == 'Valencia'
            assert ws._nearest_municipio(39.4, -0.4)['nombre'] == 'Valencia'
            assert catalogue.call_count == 1                       # mismas coordenadas: no se busca otra vez
            assert ws._nearest_municipio(37.4, -6.0)['nombre'] == 'Sevilla'   # parcela movida
            assert catalogue.call_count == 2

    def test_catalogue_is_cached(self):
        raw = [{'id': 'id46250', 'nombre': 'Valencia', 'latitud_dec': '39.47', 'longitud_dec': '-0.38'}]
        with patch.object(ws, 'aemet_fetch', return_value=raw) as fetch:
            assert ws._get_municipios() == [self.CATALOGUE[0]]
            assert ws._get_municipios() == [self.CATALOGUE[0]]
        assert fetch.call_count == 1


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
                patch('weather.services.get_weather_summary', return_value=payload) as build:
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
