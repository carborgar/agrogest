"""Cliente HTTP de AEMET OpenData (https://opendata.aemet.es/).

Requiere AEMET_API_KEY en settings. Cada consulta es doble: la API devuelve una URL
de datos pre-autorizada y esa URL trae los datos reales.
"""
import json
import logging
import ssl
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)
AEMET_BASE = "https://opendata.aemet.es/opendata"


def _ssl_contexts():
    ctxs = []
    try:
        ctxs.append(ssl.create_default_context())
    except Exception:
        pass
    ctxs.append(ssl._create_unverified_context())  # noqa: S501
    return ctxs


def _http_get(url: str, timeout: int = 10):
    api_key = getattr(settings, "AEMET_API_KEY", "")
    # Las URLs de datos (/opendata/sh/...) son pre-autorizadas: NO añadir api_key
    is_api_endpoint = "opendata.aemet.es" in url and "/opendata/api/" in url
    if is_api_endpoint and api_key:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}api_key={urllib.parse.quote(api_key)}"
    for ctx in _ssl_contexts():
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
                raw_bytes = r.read()
                # AEMET puede devolver ISO-8859-1 en vez de UTF-8
                charset = "utf-8"
                ct = r.headers.get("Content-Type", "")
                if "charset=" in ct.lower():
                    charset = ct.lower().split("charset=")[-1].strip().split(";")[0].strip()
                try:
                    text = raw_bytes.decode(charset)
                except (UnicodeDecodeError, LookupError):
                    text = raw_bytes.decode("iso-8859-1")
                return json.loads(text)
        except (urllib.error.URLError, OSError) as exc:
            logger.debug("HTTP GET failed (%s): %s", url[:80], exc)
    return None


def aemet_fetch(path: str):
    """Doble petición AEMET: meta → datos URL → datos reales."""
    meta = _http_get(f"{AEMET_BASE}{path}")
    if not meta:
        return None
    if meta.get("estado", 0) != 200:
        logger.warning("AEMET estado=%s para %s", meta.get("estado"), path)
        return None
    datos_url = meta.get("datos")
    if not datos_url:
        return None
    return _http_get(datos_url)
