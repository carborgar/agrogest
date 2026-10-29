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
  - Previsión de un municipio: se considera fresca 30 min, pero se guarda 2 días para
    enseñar la última buena (marcada como `stale`) si AEMET falla.
"""
import json
import logging
import re
from datetime import date, timedelta

from django.core.cache import cache
from django.utils import timezone

from weather.aemet.client import (
    AemetAuthError, AemetBadResponseError, AemetError, AemetNoDataError, AemetRateLimitError, aemet_fetch,
)
from weather.aemet.parsers import (
    DAY_NAMES, fix_snow_icon, interpolate_temps, parse_diaria, parse_horaria, sky_info, synthesize_hours,
)
from weather.treatment_rules import treatment_level, treatment_ok, wind_level

logger = logging.getLogger(__name__)

_MUNICIPIOS_KEY = "aemet:municipios"
_MUNICIPIOS_TTL = 86400 * 7
_NEAREST_TTL = 86400 * 90
_FORECAST_FRESH = timedelta(minutes=30)   # AEMET actualiza varias veces al día; 30 min sobra
_FORECAST_KEEP = 86400 * 2                # cuánto se guarda la última previsión buena
_FORECAST_RETRY_WAIT = 300                # tras un fallo, no se reintenta en cada carga

# Mensajes para el usuario según la causa (el detalle técnico va al log)
REASON_LOCATION = "No se pudo ubicar la parcela: revisa su contorno en el mapa."
REASON_AUTH = "AEMET rechaza la clave configurada: hay que revisar AEMET_API_KEY."
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
    """
    if isinstance(exc, (AemetAuthError, AemetBadResponseError)):
        logger.error("AEMET: %s: %s", what, exc, exc_info=isinstance(exc, AemetBadResponseError))
    else:
        logger.warning("AEMET: %s: %s", what, exc)


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


def _get_municipios() -> list:
    """Catálogo de municipios AEMET con coordenadas. Lanza `AemetError` si no se puede obtener."""
    municipios = cache.get(_MUNICIPIOS_KEY)
    if municipios:
        return municipios
    raw = aemet_fetch("/api/maestro/municipios")
    if not isinstance(raw, list):
        raise AemetBadResponseError("/api/maestro/municipios", f"se esperaba una lista: {str(raw)[:200]}")
    municipios = []
    for m in raw:
        lat = _parse_coord(m.get("latitud_dec") or m.get("latitud"))
        lon = _parse_coord(m.get("longitud_dec") or m.get("longitud"))
        if lat is None or lon is None:
            continue
        municipios.append({"cod": m.get("id", "").replace("id", ""), "nombre": m.get("nombre", ""),
                           "lat": lat, "lon": lon})
    if not municipios:
        raise AemetBadResponseError("/api/maestro/municipios", f"{len(raw)} municipios y ninguno con coordenadas")
    cache.set(_MUNICIPIOS_KEY, municipios, _MUNICIPIOS_TTL)
    logger.info("AEMET: catálogo de %d municipios cargado", len(municipios))
    return municipios


def _nearest_municipio(lat: float, lon: float) -> dict:
    """Municipio más cercano a unas coordenadas, recordado por coordenadas."""
    key = f"aemet:municipio:{lat:.5f},{lon:.5f}"
    municipio = cache.get(key)
    if municipio is None:
        municipio = min(_get_municipios(), key=lambda m: (m["lat"] - lat) ** 2 + (m["lon"] - lon) ** 2)
        municipio = {"cod": municipio["cod"], "nombre": municipio["nombre"]}
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


def _build_forecast(cod: str) -> list:
    """Previsión de 7 días de un municipio AEMET: lista de días, cada uno con sus horas.

    Combina la predicción horaria (48 h) con la diaria. Si solo falla una de las dos se usa
    la otra (y se registra el fallo). Si fallan las dos, o no dan días, lanza `AemetError`.
    """
    parts, failures = {}, []
    for kind, parse in (("horaria", parse_horaria), ("diaria", parse_diaria)):
        try:
            parts[kind] = _fetch_part(cod, kind, parse)
        except AemetError as exc:
            failures.append(exc)
            parts[kind] = []
    if failures and (parts["horaria"] or parts["diaria"]):
        for exc in failures:
            _log_aemet_error(exc, f"predicción incompleta del municipio {cod}, se sigue con la otra")
    elif failures:
        raise failures[0]
    daily = _combine(parts["horaria"], parts["diaria"])
    if not daily:
        raise AemetNoDataError(f"/api/prediccion/especifica/municipio/*/{cod}", "las predicciones no traen días")
    return daily


def _combine(hourly_list: list, daily_summary: list) -> list:
    """Une las horas (horaria) con el resumen de cada día (diaria) en una lista de días."""
    # ── Construir daily list ──
    days_map: dict[str, list] = {}
    for h in hourly_list:
        days_map.setdefault(h["date"], []).append(h)
    daily_from_hourly: dict[str, dict] = {}
    for d_str, hours in days_map.items():
        year, month, day_num = map(int, d_str.split("-"))
        d_obj = date(year, month, day_num)
        label = f"{DAY_NAMES[d_obj.weekday()]} {day_num}"
        max_precip = max(h["precipitation"] for h in hours)
        total_precip = round(sum(h["precipitation"] for h in hours), 1)
        max_prob = max(h["precipitation_probability"] for h in hours)
        max_wind = max(h["wind_speed"] for h in hours)
        max_gusts = max(h["wind_gusts"] for h in hours)
        temps = [h["temperature"] for h in hours if h["temperature"] is not None]
        min_temp = round(min(temps), 1) if temps else None
        max_temp = round(max(temps), 1) if temps else None
        daytime = [h["weather_code"] for h in hours if 6 <= int(h["hour"][:2]) <= 20]
        dom_code = max(set(daytime), key=daytime.count) if daytime else (hours[0]["weather_code"] if hours else "")
        sky = sky_info(dom_code)
        daily_from_hourly[d_str] = {
            "date": d_str,
            "label": label,
            "total_precipitation": total_precip,
            "max_precipitation": round(max_precip, 1),
            "max_precipitation_probability": max_prob,
            "max_wind_speed": round(max_wind, 1),
            "max_wind_gusts": round(max_gusts, 1),
            "min_temp": min_temp,
            "max_temp": max_temp,
            "dominant_code": dom_code,
            "icon": sky["icon"],
            "label_weather": sky["label"],
            "adverse": sky["adverse"],
            "treatment_ok": treatment_ok(max_prob, max_wind),
            "level": treatment_level(max_prob, max_wind),
            "wind_level": wind_level(max_wind),
            "sunrise": None,
            "sunset": None,
            "hours": hours,
        }
    daily_summary_map = {d["date"]: d for d in daily_summary}
    all_dates = sorted(set(list(daily_from_hourly.keys()) + list(daily_summary_map.keys())))[:7]
    combined_daily = []
    for d_str in all_dates:
        if d_str in daily_from_hourly:
            entry = daily_from_hourly[d_str]
            # Complementar desde diaria si falta en horaria
            if d_str in daily_summary_map:
                ds = daily_summary_map[d_str]
                if entry["min_temp"] is None:
                    entry["min_temp"] = ds.get("min_temp")
                if entry["max_temp"] is None:
                    entry["max_temp"] = ds.get("max_temp")
                if not entry.get("sunrise"):
                    entry["sunrise"] = ds.get("sunrise")
                if not entry.get("sunset"):
                    entry["sunset"] = ds.get("sunset")
                # Usar precipitación de la diaria si la horaria no la tiene
                if entry.get("total_precipitation", 0.0) == 0.0 and ds.get("total_precipitation", 0.0) > 0:
                    entry["total_precipitation"] = ds["total_precipitation"]
                    entry["max_precipitation"] = ds.get("max_precipitation", 0.0)
            # Interpolar temps horarias nulas usando min/max diario
            entry["hours"] = interpolate_temps(entry["hours"], entry["min_temp"], entry["max_temp"])
            entry = fix_snow_icon(entry)
            combined_daily.append(entry)
        elif d_str in daily_summary_map:
            ds = daily_summary_map[d_str]
            year, month, day_num = map(int, d_str.split("-"))
            d_obj = date(year, month, day_num)
            entry = dict(ds)
            entry["label"] = f"{DAY_NAMES[d_obj.weekday()]} {day_num}"
            entry["hours"] = synthesize_hours(d_str, ds)
            entry.setdefault("sunrise", ds.get("sunrise"))
            entry.setdefault("sunset", ds.get("sunset"))
            entry = fix_snow_icon(entry)
            combined_daily.append(entry)
    return combined_daily


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


def get_forecast(cod: str) -> dict:
    """Previsión de un municipio con caché.

    Devuelve {"daily", "updated_at", "stale"}: `stale` indica que es la última buena porque
    AEMET ha fallado. Lanza `AemetError` si falla y no hay ninguna guardada.
    """
    key, retry_key = f"aemet:forecast:{cod}", f"aemet:forecast-retry:{cod}"
    saved = cache.get(key)   # {"daily": [...], "updated_at": datetime}
    now = timezone.now()
    if saved and now - saved["updated_at"] < _FORECAST_FRESH:
        return {**saved, "stale": False}

    failed = cache.get(retry_key)   # fallo reciente: no se insiste hasta que pase la espera
    if failed is None:
        try:
            saved = {"daily": _build_forecast(cod), "updated_at": now}
            cache.set(key, saved, _FORECAST_KEEP)
            cache.delete(retry_key)
            return {**saved, "stale": False}
        except AemetError as exc:
            when = f"se enseña la de {timezone.localtime(saved['updated_at']):%d/%m %H:%M}" if saved else "sin previsión guardada"
            _log_aemet_error(exc, f"previsión del municipio {cod} ({when})")
            failed = exc
            cache.set(retry_key, exc, _FORECAST_RETRY_WAIT)
    if saved:
        return {**saved, "stale": True}
    raise failed


def get_weather_summary(fields) -> dict:
    """Previsión de los municipios de las parcelas, una entrada por municipio.

    AEMET es municipal: las parcelas de un mismo municipio comparten previsión, así que se
    agrupan y se pide una sola vez. `errors` lista las parcelas sin previsión y el motivo.
    """
    groups: dict = {}
    errors: dict = {}
    for field in fields:
        try:
            municipio = municipality_for_field(field)
        except AemetError as exc:
            _log_aemet_error(exc, f"catálogo de municipios (parcela {field.id})")
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
            forecast = get_forecast(cod)
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
