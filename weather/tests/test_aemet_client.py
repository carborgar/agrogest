import http.client
import io
import json
import pickle
import socket
import urllib.error
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.test import override_settings

from weather.aemet import client
from weather.aemet.client import (
    AemetAuthError, AemetBadResponseError, AemetCoolingDownError, AemetNoDataError, AemetRateLimitError, AemetUnavailableError,
)

PATH = '/api/prediccion/especifica/municipio/diaria/41005'
KEY = 'clave-secreta'


class FakeResponse(io.BytesIO):
    def __init__(self, body, content_type='application/json;charset=UTF-8'):
        super().__init__(body if isinstance(body, bytes) else json.dumps(body).encode())
        self.headers = {'Content-Type': content_type}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def http_error(code, body):
    return urllib.error.HTTPError('https://x', code, 'error', {'Content-Type': 'application/json'},
                                  io.BytesIO(json.dumps(body).encode()))


META_OK = {'estado': 200, 'datos': 'https://opendata.aemet.es/opendata/sh/abc'}


@pytest.fixture(autouse=True)
def _clean():
    cache.clear()
    with override_settings(AEMET_API_KEY=KEY):
        yield


@pytest.mark.django_db
class TestAemetFetch:

    def test_two_requests_and_the_key_only_goes_to_the_api(self):
        with patch.object(client.urllib.request, 'urlopen',
                          side_effect=[FakeResponse(META_OK), FakeResponse([{'ok': 1}])]) as urlopen:
            assert client.aemet_fetch(PATH) == [{'ok': 1}]
        api_req, data_req = (c.args[0] for c in urlopen.call_args_list)
        assert api_req.get_header('Api_key') == KEY and KEY not in api_req.full_url
        assert data_req.get_header('Api_key') is None

    def test_latin1_answer_is_decoded(self):
        body = json.dumps([{'nombre': 'Almería'}], ensure_ascii=False).encode('iso-8859-1')
        with patch.object(client.urllib.request, 'urlopen',
                          side_effect=[FakeResponse(META_OK), FakeResponse(body, 'application/json')]):
            assert client.aemet_fetch(PATH) == [{'nombre': 'Almería'}]

    @pytest.mark.parametrize('code,error', [
        (401, AemetAuthError), (403, AemetAuthError), (404, AemetNoDataError),
        (429, AemetRateLimitError), (500, AemetUnavailableError),
    ])
    def test_http_errors_keep_their_cause(self, code, error):
        with patch.object(client.urllib.request, 'urlopen', side_effect=http_error(code, {'descripcion': 'motivo AEMET'})):
            with pytest.raises(error) as exc:
                client.aemet_fetch(PATH)
        assert exc.value.status == code and 'motivo AEMET' in str(exc.value) and PATH in str(exc.value)

    def test_error_inside_a_200_answer(self):
        meta = {'estado': 401, 'descripcion': 'API key invalido'}
        with patch.object(client.urllib.request, 'urlopen', return_value=FakeResponse(meta)):
            with pytest.raises(AemetAuthError, match='API key invalido'):
                client.aemet_fetch(PATH)

    def test_the_key_never_appears_in_the_error(self):
        error = urllib.error.URLError(f'fallo en https://opendata.aemet.es{PATH}?api_key={KEY}')
        with patch.object(client.urllib.request, 'urlopen', side_effect=error):
            with pytest.raises(AemetUnavailableError) as exc:
                client.aemet_fetch(PATH)
        assert KEY not in str(exc.value) and exc.value.__cause__ is None and exc.value.__suppress_context__

    @pytest.mark.parametrize('error', [urllib.error.URLError('Name or service not known'), socket.timeout('timed out')])
    def test_network_problems_are_unavailable(self, error):
        with patch.object(client.urllib.request, 'urlopen', side_effect=error):
            with pytest.raises(AemetUnavailableError):
                client.aemet_fetch(PATH)

    def test_429_inside_a_200_answer_starts_the_wait(self):
        with patch.object(client.urllib.request, 'urlopen',
                          return_value=FakeResponse({'estado': 429, 'descripcion': 'Límite'})) as urlopen:
            with pytest.raises(AemetRateLimitError):
                client.aemet_fetch(PATH)
            with pytest.raises(AemetCoolingDownError):
                client.aemet_fetch(PATH)
        assert urlopen.call_count == 1

    def test_error_inside_the_data_answer(self):
        with patch.object(client.urllib.request, 'urlopen',
                          side_effect=[FakeResponse(META_OK), FakeResponse({'estado': 404, 'descripcion': 'datos caducados'})]):
            with pytest.raises(AemetNoDataError, match='datos caducados'):
                client.aemet_fetch(PATH)

    def test_incomplete_read_is_unavailable(self):
        with patch.object(client.urllib.request, 'urlopen', side_effect=http.client.IncompleteRead(b'')):
            with pytest.raises(AemetUnavailableError, match='IncompleteRead'):
                client.aemet_fetch(PATH)

    def test_quoted_charset(self):
        assert client._decode('Almería'.encode(), 'application/json; charset="utf-8"') == 'Almería'

    def test_failing_data_url_is_identified(self):
        with patch.object(client.urllib.request, 'urlopen',
                          side_effect=[FakeResponse(META_OK), http_error(404, {'descripcion': 'caducada'})]):
            with pytest.raises(AemetNoDataError, match=r'\(datos\)'):
                client.aemet_fetch(PATH)

    def test_non_json_is_a_bad_response(self):
        with patch.object(client.urllib.request, 'urlopen',
                          side_effect=[FakeResponse(META_OK), FakeResponse(b'<html>mantenimiento</html>', 'text/html')]):
            with pytest.raises(AemetBadResponseError, match='mantenimiento'):
                client.aemet_fetch(PATH)

    def test_after_a_429_no_request_is_made_for_a_while(self):
        with patch.object(client.urllib.request, 'urlopen', side_effect=http_error(429, {'descripcion': 'Límite'})) as urlopen:
            with pytest.raises(AemetRateLimitError):
                client.aemet_fetch(PATH)
            with pytest.raises(AemetCoolingDownError):
                client.aemet_fetch(PATH)
        assert urlopen.call_count == 1

    def test_missing_key_is_an_auth_error_without_calling(self):
        with override_settings(AEMET_API_KEY=''), patch.object(client.urllib.request, 'urlopen') as urlopen:
            with pytest.raises(AemetAuthError, match='falta AEMET_API_KEY'):
                client.aemet_fetch(PATH)
        urlopen.assert_not_called()


@pytest.mark.django_db
def test_errors_can_be_pickled():
    error = pickle.loads(pickle.dumps(AemetRateLimitError(PATH, 'Límite', 429)))
    assert isinstance(error, AemetRateLimitError) and error.status == 429 and error.detail == 'Límite'
