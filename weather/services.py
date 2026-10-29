"""
Previsión meteorológica de las parcelas usando AEMET OpenData.
Flujo:
  1. Calcula el centroide de la parcela (lat/lon).
  2. Descarga el catálogo de municipios de AEMET y lo cachea en memoria.
  3. Encuentra el municipio más cercano a las coordenadas.
  4. Obtiene predicción horaria (48 h) y diaria (7 días) para ese municipio.
  5. Construye un dict unificado con datos diarios y horarios.
"""
import json
import logging
import re
import time
from datetime import date

from django.core.cache import cache

from weather.aemet.client import aemet_fetch
from weather.aemet.parsers import (
    DAY_NAMES, fix_snow_icon, interpolate_temps, parse_diaria, parse_horaria, sky_info, synthesize_hours,
)
from weather.treatment_rules import treatment_level, treatment_ok, wind_level

logger = logging.getLogger(__name__)
# Caché en memoria del catálogo de municipios
_municipios_cache: list | None = None
_municipios_ts: float = 0
_MUNICIPIOS_TTL = 86400 * 7  # refresca cada semana


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
    global _municipios_cache, _municipios_ts
    now = time.time()
    if _municipios_cache is not None and (now - _municipios_ts) < _MUNICIPIOS_TTL:
        return _municipios_cache
    raw = aemet_fetch("/api/maestro/municipios")
    if not raw or not isinstance(raw, list):
        logger.warning("AEMET: no se pudo obtener lista de municipios")
        return _municipios_cache or []
    parsed = []
    for m in raw:
        mid = m.get("id", "")
        cod = mid.replace("id", "")
        lat = _parse_coord(m.get("latitud_dec") or m.get("latitud"))
        lon = _parse_coord(m.get("longitud_dec") or m.get("longitud"))
        if lat is None or lon is None:
            continue
        parsed.append({"cod": cod, "nombre": m.get("nombre", ""), "lat": lat, "lon": lon})
    if parsed:
        _municipios_cache = parsed
        _municipios_ts = now
        logger.info("AEMET: %d municipios cargados", len(parsed))
    return _municipios_cache or []


def _nearest_municipio(lat: float, lon: float) -> dict | None:
    municipios = _get_municipios()
    if not municipios:
        return None
    return min(municipios, key=lambda m: (m["lat"] - lat) ** 2 + (m["lon"] - lon) ** 2)


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
def _build_forecast(cod: str) -> list | None:
    """Previsión de 7 días de un municipio AEMET: lista de días, cada uno con sus horas.

    Combina la predicción horaria (48 h) con la diaria. Devuelve None si AEMET no da datos.
    """
    # ── Datos ──
    horaria_raw = aemet_fetch(f"/api/prediccion/especifica/municipio/horaria/{cod}")
    hourly_list = parse_horaria(horaria_raw) if horaria_raw else []
    diaria_raw = aemet_fetch(f"/api/prediccion/especifica/municipio/diaria/{cod}")
    daily_summary = parse_diaria(diaria_raw) if diaria_raw else []
    if not hourly_list and not daily_summary:
        logger.warning("AEMET: sin datos para municipio %s", cod)
        return None
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
    if not combined_daily:
        return None

    return combined_daily


# ── Previsión por municipio de las parcelas (Inicio y El Tiempo) ───────
_FORECAST_TTL = 1800       # AEMET actualiza varias veces al día; 30 min sobra
_FORECAST_FAIL_TTL = 300   # si falla, no se reintenta en cada carga (límite de consultas de AEMET)


def municipality_for_field(field) -> dict | None:
    """Municipio AEMET ({'cod', 'nombre', ...}) más cercano al centro de la parcela, o None."""
    if not getattr(field, "geometry", None):
        return None
    coords = _get_centroid(field.geometry)
    if coords is None:
        return None
    return _nearest_municipio(*coords)


def get_forecast(cod: str) -> list | None:
    """Previsión de un municipio con caché. None si AEMET no responde."""
    key = f"aemet:forecast:{cod}"
    cached = cache.get(key)
    if cached is not None:
        return cached or None   # [] = fallo reciente guardado
    daily = _build_forecast(cod)
    cache.set(key, daily or [], _FORECAST_TTL if daily else _FORECAST_FAIL_TTL)
    return daily


def get_weather_summary(fields) -> dict:
    """Previsión de los municipios de las parcelas, una entrada por municipio.

    AEMET es municipal: las parcelas de un mismo municipio comparten previsión, así que se
    agrupan y se pide una sola vez. `errors` lista las parcelas sin previsión y el motivo.
    """
    groups: dict = {}
    errors: dict = {}
    for field in fields:
        municipio = municipality_for_field(field)
        if not municipio:
            errors.setdefault("No se pudo ubicar la parcela: revisa su contorno en el mapa.", []).append(field.name)
            continue
        group = groups.setdefault(municipio["cod"], {"name": municipio["nombre"], "fields": []})
        group["fields"].append({"id": field.id, "name": field.name})

    municipalities = []
    for cod, group in groups.items():
        daily = get_forecast(cod)
        if not daily:
            errors.setdefault("AEMET no ha dado la previsión. Inténtalo en unos minutos.", []).extend(
                f["name"] for f in group["fields"])
            continue
        municipalities.append({**group, "daily": daily})
    municipalities.sort(key=lambda m: (-len(m["fields"]), m["name"]))
    return {
        "municipalities": municipalities,
        "errors": [{"reason": reason, "fields": names} for reason, names in errors.items()],
    }
