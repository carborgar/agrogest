"""El asistente nunca devuelve al usuario detalles técnicos de las excepciones."""
import json
import logging
from unittest.mock import MagicMock, patch

import pytest
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse

from farm import ai_service
from farm.models import ChatMessage
from farm.tests.factories import OrganizationFactory

SECRETO = "SECRETO-interno sk-12345 https://proveedor.example/v1/modelo-x"


@pytest.fixture(autouse=True)
def _limpiar_cache(db):
    cache.delete(ai_service._QUOTA_CACHE_KEY)
    yield
    cache.delete(ai_service._QUOTA_CACHE_KEY)


@pytest.fixture
def org(db):
    return OrganizationFactory()


def _llamar(org, exc):
    client = MagicMock()
    client.chats.create.return_value.send_message.side_effect = exc
    with override_settings(GEMINI_API_KEY='k', GEMINI_DAILY_LIMIT=0), \
            patch.object(ai_service.genai, 'Client', return_value=client):
        return ai_service.chat_with_ai(org, 'hola', [])


@pytest.mark.parametrize('exc,esperado', [
    (TimeoutError(SECRETO), ai_service.MSG_NO_DISPONIBLE),
    (RuntimeError(SECRETO), ai_service.MSG_NO_DISPONIBLE),
    (RuntimeError('403 API_KEY_INVALID ' + SECRETO), ai_service.MSG_NO_CONFIGURADO),
    (RuntimeError('429 RESOURCE_EXHAUSTED ' + SECRETO), ai_service.MSG_LIMITE_CUOTA),
])
def test_fallos_devuelven_texto_generico(org, caplog, exc, esperado):
    with caplog.at_level(logging.WARNING):
        texto, error = _llamar(org, exc)
    assert texto is None
    assert error == esperado
    assert 'SECRETO' not in error and 'sk-' not in error and 'http' not in error
    assert 'SECRETO' in caplog.text  # el detalle va al log


def test_error_generico_no_dispara_circuit_breaker(org):
    _llamar(org, RuntimeError(SECRETO))
    assert not ai_service.is_quota_exhausted()


def test_mensaje_limite_lo_detecta_el_js():
    assert 'Límite' in ai_service.MSG_LIMITE_CUOTA


def test_sin_clave(org, caplog):
    with override_settings(GEMINI_API_KEY=''), caplog.at_level(logging.WARNING):
        texto, error = ai_service.chat_with_ai(org, 'hola', [])
    assert texto is None
    assert error == ai_service.MSG_NO_CONFIGURADO
    assert 'GEMINI' not in error and '.env' not in error
    assert 'GEMINI_API_KEY' in caplog.text


def test_limite_diario(org, caplog):
    ChatMessage.objects.create(organization=org, session_id='s', role='assistant', content='x')
    with override_settings(GEMINI_API_KEY='k', GEMINI_DAILY_LIMIT=1), \
            caplog.at_level(logging.WARNING):
        texto, error = ai_service.chat_with_ai(org, 'hola', [])
    assert texto is None
    assert 'Límite' in error
    assert 'GEMINI' not in error and '.env' not in error
    assert 'Límite diario' in caplog.text


def test_circuit_breaker_activo(org):
    ai_service.mark_quota_exhausted()
    with override_settings(GEMINI_API_KEY='k'):
        _, error = ai_service.chat_with_ai(org, 'hola', [])
    assert error == ai_service.MSG_LIMITE_CUOTA
    assert 'Gemini' not in error


@pytest.mark.django_db
def test_vista_no_filtra_excepcion(client, org, caplog):
    from django.contrib.auth import get_user_model
    user = get_user_model().objects.create_user(username='u', password='p', organization=org)
    client.force_login(user)
    with patch('farm.views.chat_views.chat_with_ai', side_effect=RuntimeError(SECRETO)), \
            caplog.at_level(logging.ERROR):
        resp = client.post(reverse('chat'), json.dumps({'message': 'hola'}),
                           content_type='application/json')
    data = resp.json()
    assert data['error'] == ai_service.MSG_NO_DISPONIBLE
    assert 'SECRETO' not in resp.content.decode()
    assert 'SECRETO' in caplog.text


@pytest.mark.django_db
def test_vista_error_de_proveedor_extremo_a_extremo(client, org):
    from django.contrib.auth import get_user_model
    user = get_user_model().objects.create_user(username='u2', password='p', organization=org)
    client.force_login(user)
    mock_client = MagicMock()
    mock_client.chats.create.return_value.send_message.side_effect = TimeoutError(SECRETO)
    with override_settings(GEMINI_API_KEY='k', GEMINI_DAILY_LIMIT=0), \
            patch.object(ai_service.genai, 'Client', return_value=mock_client):
        resp = client.post(reverse('chat'), json.dumps({'message': 'hola'}),
                           content_type='application/json')
    assert 'SECRETO' not in resp.content.decode()
    assert resp.json()['error'] == ai_service.MSG_NO_DISPONIBLE


class _ErrorSDK(Exception):
    def __init__(self, code, msg=''):
        super().__init__(msg)
        self.code = code


@pytest.mark.parametrize('exc,esperado', [
    (_ErrorSDK(429, SECRETO), ai_service.MSG_LIMITE_CUOTA),
    (_ErrorSDK(403, SECRETO), ai_service.MSG_NO_CONFIGURADO),
    # Con código presente manda el código, no el texto
    (_ErrorSDK(500, 'quota 429 403 ' + SECRETO), ai_service.MSG_NO_DISPONIBLE),
])
def test_clasifica_por_codigo_de_estado(org, exc, esperado):
    _, error = _llamar(org, exc)
    assert error == esperado


def test_sentry_no_envia_variables_locales():
    from pathlib import Path
    from django.conf import settings
    src = (Path(settings.BASE_DIR) / 'agrogest' / 'settings.py').read_text()
    assert 'include_local_variables=False' in src
