"""
{% static_v 'js/fichero.js' %} → /static/js/fichero.js?v=<hash del contenido>.

Por qué: con StaticFilesStorage los navegadores pueden reutilizar un JS viejo tras un cambio o un despliegue y
mezclarlo con una plantilla nueva (pantalla del formulario de tratamiento con «Por cuba llena» y sin mojado por defecto
cuando el código ya decía otra cosa). Con el hash en la URL, cualquier cambio del fichero fuerza la descarga.
"""
import hashlib

from django import template
from django.contrib.staticfiles import finders
from django.templatetags.static import static

register = template.Library()
_CACHE = {}


def _digest(path):
    absolute = finders.find(path)
    if not absolute:
        return ''
    # En producción los ficheros no cambian hasta el siguiente despliegue; en desarrollo se vuelve a calcular si cambia el mtime.
    import os
    mtime = os.path.getmtime(absolute)
    cached = _CACHE.get(path)
    if cached and cached[0] == mtime:
        return cached[1]
    with open(absolute, 'rb') as fh:
        digest = hashlib.md5(fh.read()).hexdigest()[:10]
    _CACHE[path] = (mtime, digest)
    return digest


@register.simple_tag
def static_v(path):
    url = static(path)
    digest = _digest(path)
    return f'{url}?v={digest}' if digest else url
