"""
Previsión meteorológica de las parcelas usando AEMET OpenData.
Flujo:
  1. Calcula el centroide de la parcela (lat/lon).
  2. Busca el municipio AEMET más cercano (catálogo de municipios de AEMET).
  3. Obtiene predicción horaria (48 h) y diaria (7 días) para ese municipio.
  4. Construye un dict unificado con datos diarios y horarios.

Caché: todo va a la caché de Django (en BD), compartida por todas las instancias de Vercel.
Solo se guardan datos de AEMET; nada de lo que crea el usuario (parcelas, tratamientos…).
  - Catálogo de municipios: 7 días (casi no cambia).
  - Municipio de unas coordenadas: 90 días. Si la parcela cambia de contorno, su centroide
    cambia y con él la clave, así que se busca de nuevo sin invalidar nada.
  - Previsión de un municipio: fresca 30 min (5 si vino incompleta), pero se guarda 2 días
    para enseñar la última buena (marcada como `stale`) si AEMET falla.
  - Tras un fallo se espera antes de volver a llamar (5 min; 1 min si fue el límite de consultas).
Las claves llevan versión (`aemet:v1:`): si cambia lo que se guarda, se sube y lo viejo se ignora.
"""
import json
import logging
import re
import time
from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone

from weather.aemet import client
from weather.aemet.client import (
    AemetAuthError, AemetBadResponseError, AemetCoolingDownError, AemetError, AemetNoDataError,
    AemetRateLimitError, AemetUnavailableError, aemet_fetch,
)
from weather.aemet.parsers import build_days, parse_diaria, parse_horaria

logger = logging.getLogger(__name__)

_KEY = "aemet:v1"
_MUNICIPIOS_KEY = f"{_KEY}:municipios"
_MUNICIPIOS_RETRY_KEY = f"{_KEY}:municipios-retry"
_MUNICIPIOS_TTL = 86400 * 7
_NEAREST_TTL = 86400 * 90
_FORECAST_FRESH = timedelta(minutes=30)          # AEMET actualiza varias veces al día; 30 min sobra
_FORECAST_PARTIAL_FRESH = timedelta(minutes=5)   # si solo llegó la horaria o la diaria
_FORECAST_KEEP = 86400 * 2                       # cuánto se guarda la última previsión buena
_RETRY_WAIT = 300                                # tras un fallo, no se reintenta en cada carga
# Tiempo máximo de consultas a AEMET por carga: lo que falte se da como guardado o como error,
# para no pasar del tiempo máximo de la función de Vercel.
SUMMARY_BUDGET = 12

# Mensajes para el usuario según la causa (el detalle técnico va al log)
REASON_LOCATION = "No se pudo ubicar la parcela: revisa su contorno en el mapa."
REASON_AUTH = "El servicio del tiempo no está bien configurado. Avisa al administrador."
REASON_RATE_LIMIT = "AEMET está limitando las consultas. Inténtalo en un minuto."
REASON_NO_DATA = "AEMET no tiene previsión para este municipio ahora mismo."
REASON_UNAVAILABLE = "AEMET no responde. Inténtalo en unos minutos."


def _user_reason(exc: AemetError) -> str:
    if isinstance(exc, AemetAuthError):
        return REASON_AUTH
    if isinstance(exc, AemetRateLimitError):
        return REASON_RATE_LIMIT
    if isinstance(exc, AemetNoDataError):
        return REASON_NO_DATA
    return REASON_UNAVAILABLE


def _log_aemet_error(exc: AemetError, what: str) -> None:
    """Un solo registro por fallo, con lo que se intentaba hacer y la causa real.

    ERROR (llega a Sentry) cuando hay que actuar: clave rechazada o formato que ya no entendemos.
    WARNING cuando es pasajero: límite de consultas, caída de AEMET, sin datos.
    La espera tras un 429 no se registra: el 429 ya se registró cuando ocurrió.
    """
    if isinstance(exc, AemetCoolingDownError):
        return
    if isinstance(exc, (AemetAuthError, AemetBadResponseError)):
        logger.error("AEMET: %s: %s", what, exc, exc_info=exc if exc.__cause__ else None)
    else:
        logger.warning("AEMET: %s: %s", what, exc)


# Los fallos se guardan como datos simples (no la excepción) para que un cambio en las clases
# no rompa la lectura de la caché.
_ERROR_TYPES = {cls.__name__: cls for cls in (
    AemetError, AemetAuthError, AemetBadResponseError, AemetRateLimitError, AemetCoolingDownError,
    AemetNoDataError, AemetUnavailableError)}


def _remember_failure(key: str, exc: AemetError) -> None:
    """Guarda el fallo para no reintentar en cada carga (1 min si es el límite de consultas)."""
    if isinstance(exc, AemetCoolingDownError):
        return   # la espera ya la controla el cliente
    wait = client.RATE_LIMIT_COOLDOWN if isinstance(exc, AemetRateLimitError) else _RETRY_WAIT
    cache.set(key, (type(exc).__name__, exc.path, exc.detail, exc.status), wait)


def _recent_failure(key: str) -> AemetError | None:
    saved = cache.get(key)
    if not saved:
        return None
    name, path, detail, status = saved
    return _ERROR_TYPES.get(name, AemetError)(path, detail, status)


# ── Municipios ────────────────────────────────────────────────────────
def _parse_coord(raw) -> float | None:
    if raw is None:
        return None
    s = str(raw).strip()
    try:
        return float(s)
    except ValueError:
        pass
    m = re.match(r"(\d+)\s+(\d+)'\s*([\d.]+)?''?\s*([NSEWnsew]?)", s)
    if m:
        deg, mn, sec, hemi = m.groups()
        val = float(deg) + float(mn) / 60 + float(sec or 0) / 3600
        if hemi.upper() in ("S", "W"):
            val = -val
        return val
    return None


def _parse_catalogue(raw) -> list:
    """[(cod, nombre, lat, lon)] con las coordenadas redondeadas (la fila en caché ocupa menos)."""
    path = "/api/maestro/municipios"
    if not isinstance(raw, list):
        raise AemetBadResponseError(path, f"se esperaba una lista: {str(raw)[:200]}")
    municipios = []
    try:
        for m in raw:
            lat = _parse_coord(m.get("latitud_dec") or m.get("latitud"))
            lon = _parse_coord(m.get("longitud_dec") or m.get("longitud"))
            if lat is not None and lon is not None:
                municipios.append((m.get("id", "").replace("id", ""), m.get("nombre", ""), round(lat, 4), round(lon, 4)))
    except (AttributeError, TypeError, ValueError) as exc:
        raise AemetBadResponseError(path, f"no se pudo interpretar: {exc!r}") from exc
    if not municipios:
        raise AemetBadResponseError(path, f"{len(raw)} municipios y ninguno con coordenadas")
    return municipios


def _get_municipios() -> list:
    """Catálogo de municipios AEMET con coordenadas. Lanza `AemetError` si no se puede obtener."""
    municipios = cache.get(_MUNICIPIOS_KEY)
    if municipios:
        return municipios
    failed = _recent_failure(_MUNICIPIOS_RETRY_KEY)
    if failed:
        raise failed
    try:
        municipios = _parse_catalogue(aemet_fetch("/api/maestro/municipios"))
    except AemetError as exc:
        _log_aemet_error(exc, "catálogo de municipios")
        _remember_failure(_MUNICIPIOS_RETRY_KEY, exc)
        raise
    cache.set(_MUNICIPIOS_KEY, municipios, _MUNICIPIOS_TTL)
    logger.info("AEMET: catálogo de %d municipios cargado", len(municipios))
    return municipios


def _nearest_municipio(lat: float, lon: float) -> dict:
    """Municipio más cercano a unas coordenadas, recordado por coordenadas."""
    key = f"{_KEY}:municipio:{lat:.5f},{lon:.5f}"
    municipio = cache.get(key)
    if municipio is None:
        cod, nombre, _, _ = min(_get_municipios(), key=lambda m: (m[2] - lat) ** 2 + (m[3] - lon) ** 2)
        municipio = {"cod": cod, "nombre": nombre}
        cache.set(key, municipio, _NEAREST_TTL)
    return municipio


# ── Geometría ─────────────────────────────────────────────────────────
def _get_centroid(geometry_json: str):
    try:
        geojson = json.loads(geometry_json)
    except (json.JSONDecodeError, TypeError):
        return None
    geo_type = geojson.get("type")
    coords = geojson.get("coordinates")
    if not coords:
        return None
    if geo_type == "Point":
        return coords[1], coords[0]
    if geo_type == "Polygon":
        ring = coords[0]
    elif geo_type == "MultiPolygon":
        ring = coords[0][0]
    elif geo_type == "Feature":
        return _get_centroid(json.dumps(geojson.get("geometry", {})))
    else:
        return None
    if not ring:
        return None
    lons = [p[0] for p in ring]
    lats = [p[1] for p in ring]
    return sum(lats) / len(lats), sum(lons) / len(lons)


# ── Previsión de un municipio ─────────────────────────────────────────
def _fetch_part(cod: str, kind: str, parse):
    """Descarga y parsea una predicción ('horaria' o 'diaria'). Lanza `AemetError`."""
    path = f"/api/prediccion/especifica/municipio/{kind}/{cod}"
    raw = aemet_fetch(path)
    try:
        return parse(raw)
    except Exception as exc:  # formato de AEMET que no esperábamos
        raise AemetBadResponseError(path, f"no se pudo interpretar: {exc!r}") from exc


def _build_forecast(cod: str) -> tuple[list, bool]:
    """Previsión de 7 días de un municipio AEMET: (días con sus horas, incompleta).

    Combina la predicción horaria (48 h) con la diaria. Si solo falla una de las dos se usa
    la otra (incompleta=True) y se registra el fallo. Si fallan las dos se registra el menos
    grave y se lanza el más grave (lo registra quien llama), para que nada quede sin log.
    """
    parts, failures = {}, []
    for kind, parse in (("horaria", parse_horaria), ("diaria", parse_diaria)):
        try:
            parts[kind] = _fetch_part(cod, kind, parse)
        except AemetError as exc:
            failures.append(exc)
            parts[kind] = []
    failures.sort(key=lambda e: e.severity, reverse=True)
    if failures and not (parts["horaria"] or parts["diaria"]):
        for exc in failures[1:]:
            _log_aemet_error(exc, f"previsión del municipio {cod}")
        raise failures[0]
    for exc in failures:
        _log_aemet_error(exc, f"previsión incompleta del municipio {cod}, se sigue con la otra")
    try:
        daily = build_days(parts["horaria"], parts["diaria"])
    except Exception as exc:  # datos con una forma que no esperábamos
        raise AemetBadResponseError(f"/api/prediccion/especifica/municipio/*/{cod}",
                                    f"no se pudo combinar: {exc!r}") from exc
    if not daily:
        raise AemetNoDataError(f"/api/prediccion/especifica/municipio/*/{cod}", "las predicciones no traen días")
    return daily, bool(failures)


# ── Previsión por municipio de las parcelas (Inicio y El Tiempo) ───────
def municipality_for_field(field) -> dict | None:
    """Municipio AEMET ({'cod', 'nombre'}) más cercano al centro de la parcela.

    None si la parcela no tiene un contorno válido. Lanza `AemetError` si hace falta el
    catálogo de municipios y AEMET no lo da.
    """
    if not getattr(field, "geometry", None):
        return None
    coords = _get_centroid(field.geometry)
    if coords is None:
        return None
    return _nearest_municipio(*coords)


def get_forecast(cod: str, can_fetch: bool = True) -> dict:
    """Previsión de un municipio con caché.

    Devuelve {"daily", "updated_at", "stale"}: `stale` indica que es la última buena porque
    AEMET ha fallado (o no ha dado tiempo a consultarla). Lanza `AemetError` si no hay ninguna.
    `can_fetch=False`: no se llama a AEMET (se ha agotado el tiempo de esta carga).
    """
    key, retry_key = f"{_KEY}:forecast:{cod}", f"{_KEY}:forecast-retry:{cod}"
    saved = cache.get(key)   # {"daily", "updated_at", "fresh_until"}
    now = timezone.now()
    if saved and now < saved["fresh_until"]:
        return _forecast_result(saved, stale=False)

    failed = _recent_failure(retry_key)   # fallo reciente: no se insiste hasta que pase la espera
    if failed is None and not can_fetch:
        failed = AemetUnavailableError(f"/api/prediccion/especifica/municipio/*/{cod}",
                                       "no consultada: se agotó el tiempo de esta carga")
        _log_aemet_error(failed, f"previsión del municipio {cod}")
    elif failed is None:
        try:
            daily, partial = _build_forecast(cod)
        except AemetError as exc:
            when = (f"se enseña la de {timezone.localtime(saved['updated_at']):%d/%m %H:%M}"
                    if saved else "sin previsión guardada")
            _log_aemet_error(exc, f"previsión del municipio {cod} ({when})")
            _remember_failure(retry_key, exc)
            failed = exc
        else:
            saved = {"daily": daily, "updated_at": now,
                     "fresh_until": now + (_FORECAST_PARTIAL_FRESH if partial else _FORECAST_FRESH)}
            cache.set(key, saved, _FORECAST_KEEP)
            return _forecast_result(saved, stale=False)
    if saved:
        return _forecast_result(saved, stale=True)
    raise failed


def _forecast_result(saved: dict, stale: bool) -> dict:
    return {"daily": saved["daily"], "updated_at": saved["updated_at"], "stale": stale}


def get_weather_summary(fields) -> dict:
    """Previsión de los municipios de las parcelas, una entrada por municipio.

    AEMET es municipal: las parcelas de un mismo municipio comparten previsión, así que se
    agrupan y se pide una sola vez. `errors` lista las parcelas sin previsión y el motivo.
    """
    deadline = time.monotonic() + SUMMARY_BUDGET
    groups: dict = {}
    errors: dict = {}
    catalogue_error = None   # si el catálogo falla, no se vuelve a pedir por cada parcela
    for field in fields:
        try:
            if catalogue_error:
                raise catalogue_error
            municipio = municipality_for_field(field)
        except AemetError as exc:
            catalogue_error = exc
            errors.setdefault(_user_reason(exc), []).append(field.name)
            continue
        if not municipio:
            errors.setdefault(REASON_LOCATION, []).append(field.name)
            continue
        group = groups.setdefault(municipio["cod"], {"name": municipio["nombre"], "fields": []})
        group["fields"].append({"id": field.id, "name": field.name})

    municipalities = []
    for cod, group in groups.items():
        try:
            forecast = get_forecast(cod, can_fetch=time.monotonic() < deadline)
        except AemetError as exc:
            errors.setdefault(_user_reason(exc), []).extend(f["name"] for f in group["fields"])
            continue
        municipalities.append({
            **group,
            "daily": forecast["daily"],
            "updated_at": forecast["updated_at"].isoformat(),
            "stale": forecast["stale"],
        })
    municipalities.sort(key=lambda m: (-len(m["fields"]), m["name"]))
    return {
        "municipalities": municipalities,
        "errors": [{"reason": reason, "fields": names} for reason, names in errors.items()],
    }
