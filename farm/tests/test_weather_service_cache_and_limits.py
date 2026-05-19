from types import SimpleNamespace

import pytest
from django.conf import settings
from django.core.cache import cache

from farm import weather_service


@pytest.fixture(autouse=True)
def _clear_cache_between_tests(db):
    """Fixture para limpiar caché entre tests. Usa 'db' para permitir acceso a BD en DatabaseCache."""
    try:
        cache.clear()
    except Exception:
        pass
    yield
    try:
        cache.clear()
    except Exception:
        pass


@pytest.mark.django_db
def test_allow_aemet_request_respects_internal_per_minute_limit(settings):
    settings.AEMET_RATE_LIMIT_PER_MINUTE = 2

    assert weather_service._allow_aemet_request() is True
    assert weather_service._allow_aemet_request() is True
    assert weather_service._allow_aemet_request() is False


@pytest.mark.django_db
def test_get_weather_for_field_uses_fresh_cache_before_hitting_api(settings, monkeypatch):
    settings.AEMET_API_KEY = "token"

    field = SimpleNamespace(
        geometry='{"type":"Point","coordinates":[-3.70379,40.41678]}'
    )
    municipio = {"cod": "28079", "nombre": "Madrid"}
    payload = {"municipality": "Madrid", "daily": [{"date": "2026-05-19"}], "hourly": []}

    monkeypatch.setattr(weather_service, "_nearest_municipio", lambda lat, lon: municipio)

    cache_key = weather_service._WEATHER_CACHE_KEY.format(cod=municipio["cod"])
    cache.set(cache_key, payload, timeout=1800)

    def fail_if_called(_path):
        raise AssertionError("No debería llamar a AEMET si hay caché fresca")

    monkeypatch.setattr(weather_service, "_aemet_fetch", fail_if_called)

    result = weather_service.get_weather_for_field(field)
    assert result == payload


@pytest.mark.django_db
def test_get_weather_for_field_returns_stale_cache_when_rate_limited(settings, monkeypatch):
    settings.AEMET_API_KEY = "token"

    field = SimpleNamespace(
        geometry='{"type":"Point","coordinates":[-3.70379,40.41678]}'
    )
    municipio = {"cod": "28079", "nombre": "Madrid"}
    stale_payload = {"municipality": "Madrid", "daily": [{"date": "2026-05-18"}], "hourly": []}

    monkeypatch.setattr(weather_service, "_nearest_municipio", lambda lat, lon: municipio)

    stale_key = weather_service._WEATHER_STALE_CACHE_KEY.format(cod=municipio["cod"])
    cache.set(stale_key, stale_payload, timeout=21600)

    def rate_limited(_path):
        raise weather_service.AemetRateLimitExceeded("rate-limited")

    monkeypatch.setattr(weather_service, "_aemet_fetch", rate_limited)

    result = weather_service.get_weather_for_field(field)
    assert result == stale_payload

