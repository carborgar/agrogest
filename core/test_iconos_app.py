import json
import struct
from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.staticfiles import finders


def _static(path):
    found = finders.find(path)
    assert found, f'No existe el estático {path}'
    return Path(found)


def _png_size(path):
    # Ancho y alto vienen en la cabecera IHDR del PNG (bytes 16-24)
    data = _static(path).read_bytes()[:24]
    assert data[:8] == b'\x89PNG\r\n\x1a\n', f'{path} no es un PNG'
    return struct.unpack('>II', data[16:24])


@pytest.mark.django_db
def test_cabecera_declara_favicon_icono_ios_y_manifest(client):
    head = client.get('/').content.decode().split('</head>')[0]
    for ruta in ('img/icons/favicon.svg', 'img/icons/favicon-32.png',
                 'img/icons/apple-touch-icon.png', 'manifest.webmanifest'):
        assert f'{settings.STATIC_URL}{ruta}' in head
    assert 'rel="apple-touch-icon"' in head and 'rel="manifest"' in head
    assert 'name="apple-mobile-web-app-title" content="AgroGest"' in head


def test_iconos_tienen_el_tamano_que_declaran():
    assert _png_size('img/icons/apple-touch-icon.png') == (180, 180)
    assert _png_size('img/icons/favicon-32.png') == (32, 32)
    manifest = json.loads(_static('manifest.webmanifest').read_text())
    propositos = set()
    for icono in manifest['icons']:
        ancho, alto = map(int, icono['sizes'].split('x'))
        assert _png_size(icono['src']) == (ancho, alto)
        propositos.add(icono['purpose'])
    assert propositos == {'any', 'maskable'}
