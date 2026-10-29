"""Cliente HTTP de AEMET OpenData (https://opendata.aemet.es/).

Requiere AEMET_API_KEY en settings. Cada consulta es doble: la API devuelve una URL
de datos pre-autorizada (campo `datos`) y esa URL trae los datos reales.

Los fallos se lanzan como `AemetError` (con su subclase según la causa) y NO se registran
aquí: quien llama sabe para qué era la consulta y lo registra una sola vez con ese contexto.
"""
import json
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request

import certifi
from django.conf import settings
from django.core.cache import cache

AEMET_BASE = "https://opendata.aemet.es/opendata"
TIMEOUT = 10
# AEMET limita las consultas por minuto. Tras un 429 se espera este tiempo antes de volver a
# llamar (en caché compartida, para que tampoco insistan las demás instancias de Vercel).
RATE_LIMIT_COOLDOWN = 60
_COOLDOWN_KEY = "aemet:rate-limited"
_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())


class AemetError(Exception):
    """Fallo al consultar AEMET. `path` es la ruta pedida (nunca la URL con la clave)."""
    reason = "AEMET no responde"

    def __init__(self, path: str, detail: str = "", status: int | None = None):
        api_key = getattr(settings, "AEMET_API_KEY", "")
        if api_key:   # por si algún mensaje de la librería trae la URL con la clave
            detail = detail.replace(api_key, "***").replace(urllib.parse.quote(api_key), "***")
        self.path = path
        self.detail = detail
        self.status = status
        status_txt = f" HTTP {status}" if status else ""
        super().__init__(f"{self.reason}{status_txt} en {path}: {detail}".rstrip(": "))

    def __reduce__(self):
        # Para poder guardarlo en la caché (pickle) con todos sus datos
        return self.__class__, (self.path, self.detail, self.status)


class AemetAuthError(AemetError):
    reason = "AEMET rechaza la API key"


class AemetRateLimitError(AemetError):
    reason = "AEMET limita las consultas por minuto"


class AemetNoDataError(AemetError):
    reason = "AEMET no tiene datos"


class AemetUnavailableError(AemetError):
    reason = "AEMET no responde"


class AemetBadResponseError(AemetError):
    reason = "AEMET devuelve una respuesta inesperada"


def _error_for_status(status: int | None) -> type[AemetError]:
    if status in (401, 403):
        return AemetAuthError
    if status == 429:
        return AemetRateLimitError
    if status == 404:
        return AemetNoDataError
    return AemetUnavailableError


def _decode(raw: bytes, content_type: str) -> str:
    # AEMET puede devolver ISO-8859-1 en vez de UTF-8
    charset = "utf-8"
    if "charset=" in content_type.lower():
        charset = content_type.lower().split("charset=")[-1].split(";")[0].strip()
    try:
        return raw.decode(charset)
    except (UnicodeDecodeError, LookupError):
        return raw.decode("iso-8859-1")


def _description(body: str) -> str:
    """`descripcion` del JSON de error de AEMET, o el inicio del cuerpo si no es JSON."""
    try:
        return str(json.loads(body).get("descripcion") or "").strip()
    except (ValueError, AttributeError):
        return body.strip()[:200]


def _get_json(url: str, path: str):
    """GET que devuelve el JSON. `path` solo se usa para identificar la consulta en los errores."""
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=_SSL_CONTEXT) as r:
            body = _decode(r.read(), r.headers.get("Content-Type", ""))
    except urllib.error.HTTPError as exc:
        body = _decode(exc.read() or b"", exc.headers.get("Content-Type", "") if exc.headers else "")
        raise _error_for_status(exc.code)(path, _description(body), exc.code) from exc
    except urllib.error.URLError as exc:
        # Sin conexión, DNS, certificado SSL no válido, timeout de conexión…
        raise AemetUnavailableError(path, str(exc.reason)) from exc
    except (socket.timeout, TimeoutError) as exc:
        raise AemetUnavailableError(path, f"sin respuesta en {TIMEOUT} s") from exc
    except OSError as exc:
        raise AemetUnavailableError(path, str(exc)) from exc
    try:
        return json.loads(body)
    except ValueError as exc:
        raise AemetBadResponseError(path, f"no es JSON: {body.strip()[:200]}") from exc


def aemet_fetch(path: str):
    """Doble petición AEMET (metadatos → URL de datos → datos). Lanza `AemetError` si falla."""
    if cache.get(_COOLDOWN_KEY):
        raise AemetRateLimitError(path, "en espera tras un 429 reciente; no se llama")
    api_key = getattr(settings, "AEMET_API_KEY", "")
    if not api_key:
        raise AemetAuthError(path, "falta AEMET_API_KEY en la configuración")
    try:
        meta = _get_json(f"{AEMET_BASE}{path}?api_key={urllib.parse.quote(api_key)}", path)
        # AEMET a veces responde HTTP 200 con el error en el cuerpo: {"estado": 401, "descripcion": ...}
        if not isinstance(meta, dict):
            raise AemetBadResponseError(path, f"metadatos inesperados: {str(meta)[:200]}")
        estado = meta.get("estado")
        if estado != 200:
            status = estado if isinstance(estado, int) else None
            raise _error_for_status(status)(path, str(meta.get("descripcion") or ""), status)
        datos_url = meta.get("datos")
        if not datos_url:
            raise AemetBadResponseError(path, "los metadatos no traen la URL de datos")
        # La URL de datos es pre-autorizada: no lleva la API key
        return _get_json(datos_url, f"{path} (datos)")
    except AemetRateLimitError:
        cache.set(_COOLDOWN_KEY, True, RATE_LIMIT_COOLDOWN)
        raise
