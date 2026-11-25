import json
import re
import struct
from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.staticfiles import finders


def _static(path):
    found = finders.find(path)
    assert found, f'No existe el estático {path}'
    return Path(found)


def _png_header(path):
    # Cabecera IHDR del PNG: ancho y alto (bytes 16-24) y tipo de color (byte 25)
    data = _static(path).read_bytes()[:26]
    assert data[:8] == b'\x89PNG\r\n\x1a\n', f'{path} no es un PNG'
    ancho, alto = struct.unpack('>II', data[16:24])
    return ancho, alto, data[25]


def _png_size(path):
    return _png_header(path)[:2]


@pytest.mark.django_db
def test_cabecera_declara_favicon_icono_ios_y_manifest(client):
    head = client.get('/').content.decode().split('</head>')[0]
    for rel, ruta in (('icon', 'img/icons/favicon.svg'), ('icon', 'img/icons/favicon-32.png'),
                      ('apple-touch-icon', 'img/icons/apple-touch-icon.png'),
                      ('manifest', 'manifest.webmanifest')):
        assert re.search(rf'<link rel="{rel}" href="{re.escape(settings.STATIC_URL + ruta)}(\?v=\w+)?"', head), ruta
    assert 'name="apple-mobile-web-app-title" content="AgroGest"' in head


def test_icono_de_ios_es_opaco():
    # iOS pinta de negro las zonas transparentes del apple-touch-icon: tipo de color 2 = RGB sin alfa
    assert _png_header('img/icons/apple-touch-icon.png')[2] == 2


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
