"""
Servicio meteorológico usando AEMET OpenData (https://opendata.aemet.es/).
Requiere API key configurada en AEMET_API_KEY (settings).
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
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from django.conf import settings

logger = logging.getLogger(__name__)
AEMET_BASE = "https://opendata.aemet.es/opendata"
# Caché en memoria del catálogo de municipios
_municipios_cache: list | None = None
_municipios_ts: float = 0
_MUNICIPIOS_TTL = 86400 * 7  # refresca cada semana
# ── Iconos/labels por código AEMET estadoCielo ────────────────────────
_AEMET_SKY_ICONS = {
    "11": ("fa-sun", "Despejado"),
    "12": ("fa-cloud-sun", "Poco nuboso"),
    "13": ("fa-cloud-sun", "Intervalos nubosos"),
    "14": ("fa-cloud", "Nuboso"),
    "15": ("fa-cloud", "Muy nuboso"),
    "16": ("fa-cloud", "Cubierto"),
    "17": ("fa-cloud", "Nubes altas"),
    "23": ("fa-cloud-drizzle", "Intervalos nubosos con llovizna"),
    "24": ("fa-cloud-drizzle", "Nuboso con llovizna"),
    "25": ("fa-cloud-drizzle", "Muy nuboso con llovizna"),
    "26": ("fa-cloud-drizzle", "Cubierto con llovizna"),
    "33": ("fa-cloud-rain", "Intervalos nubosos con lluvia"),
    "34": ("fa-cloud-rain", "Nuboso con lluvia"),
    "35": ("fa-cloud-rain", "Muy nuboso con lluvia"),
    "36": ("fa-cloud-showers-heavy", "Cubierto con lluvia"),
    "43": ("fa-snowflake", "Intervalos nubosos con nieve escasa"),
    "44": ("fa-snowflake", "Nuboso con nieve escasa"),
    "45": ("fa-snowflake", "Muy nuboso con nieve escasa"),
    "46": ("fa-snowflake", "Cubierto con nieve escasa"),
    "51": ("fa-bolt", "Intervalos nubosos con tormenta"),
    "52": ("fa-bolt", "Nuboso con tormenta"),
    "53": ("fa-bolt", "Muy nuboso con tormenta"),
    "54": ("fa-bolt", "Cubierto con tormenta"),
    "61": ("fa-bolt", "Tormenta con lluvia"),
    "62": ("fa-bolt", "Tormenta con lluvia moderada"),
    "63": ("fa-bolt", "Tormenta con lluvia intensa"),
    "64": ("fa-bolt", "Tormenta con lluvia muy intensa"),
    "71": ("fa-smog", "Niebla"),
    "72": ("fa-smog", "Bruma"),
    "73": ("fa-sun", "Calima"),
    "74": ("fa-snowflake", "Ventisca"),
    "75": ("fa-snowflake", "Nevada con ventisca"),
    "76": ("fa-snowflake", "Nieve"),
    "77": ("fa-snowflake", "Nevada"),
    "81": ("fa-cloud-sun-rain", "Chubascos débiles"),
    "82": ("fa-cloud-sun-rain", "Chubascos moderados"),
    "83": ("fa-cloud-showers-heavy", "Chubascos fuertes"),
    "84": ("fa-bolt", "Chubascos con tormenta"),
}
_ADVERSE_CODES = {
    "23", "24", "25", "26", "33", "34", "35", "36",
    "43", "44", "45", "46", "51", "52", "53", "54",
    "61", "62", "63", "64", "71", "74", "75", "76", "77",
    "81", "82", "83", "84",
}
_DEFAULT_ICON = ("fa-cloud", "Sin datos")
DAY_NAMES = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]


def _sky_info(code: str) -> dict:
    """Convierte código AEMET estadoCielo a icon/label/adverse."""
    clean = (code or "").rstrip("n").lstrip("0")
    icon, label = _AEMET_SKY_ICONS.get(clean, _DEFAULT_ICON)
    adverse = clean in _ADVERSE_CODES
    return {"icon": icon, "label": label, "adverse": adverse}


# ── HTTP helpers ──────────────────────────────────────────────────────
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


def _aemet_fetch(path: str):
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
    raw = _aemet_fetch("/api/maestro/municipios")
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


# ── Parseo predicción horaria ─────────────────────────────────────────
def _periodo_start(periodo: str) -> int | None:
    if not periodo:
        return None
    p = str(periodo).replace("-", "").replace(":", "")
    if len(p) >= 2:
        try:
            return int(p[:2])
        except ValueError:
            pass
    return None


def _periodo_range(periodo: str) -> tuple[int, int] | None:
    """Devuelve (inicio, fin) en horas para un string de periodo AEMET como '0006' o '00-06'."""
    if not periodo:
        return None
    p = str(periodo).replace("-", "").replace(":", "")
    if len(p) >= 4:
        try:
            h_start = int(p[:2])
            h_end = int(p[2:4])
            if h_end == 0:
                h_end = 24
            return h_start, h_end
        except ValueError:
            pass
    if len(p) >= 2:
        try:
            h_start = int(p[:2])
            return h_start, h_start + 1
        except ValueError:
            pass
    return None


def _parse_float_precip(v) -> float | None:
    """Convierte valor de precipitación AEMET a float. 'Ip' (inapreciable) → 0.1 mm."""
    if v in (None, ""):
        return None
    s = str(v).strip()
    if s.lower() in ("ip", "inapreciable"):
        return 0.1
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def _interpolate_map(known: dict, h_start: int, h_end: int) -> dict:
    """Interpola linealmente los valores de temp/hum entre horas conocidas."""
    result = dict(known)
    hours = sorted(known.keys())
    if len(hours) < 2:
        return result
    for i in range(len(hours) - 1):
        h0, h1 = hours[i], hours[i + 1]
        if h1 <= h0:
            continue
        v0, v1 = known[h0], known[h1]
        for hh in range(h0 + 1, h1):
            t = (hh - h0) / (h1 - h0)
            result[hh] = round(v0 + (v1 - v0) * t, 1)
    return result


def _parse_horaria(raw_list) -> list:
    if not raw_list or not isinstance(raw_list, list):
        return []
    pred_root = raw_list[0]
    dias = pred_root.get("prediccion", {}).get("dia", [])
    hourly_list = []
    for dia in dias:
        fecha_str = (dia.get("fecha") or "")[:10]
        if not fecha_str:
            continue

        # ── Temperatura instante (puede venir cada 1 o 2 horas) ──
        temp_map_raw = {}
        for t in dia.get("temperatura", []):
            h = t.get("hora")
            v = t.get("value")
            if h is not None and v not in (None, ""):
                try:
                    temp_map_raw[int(h)] = float(v)
                except (ValueError, TypeError):
                    pass
        # Interpolar temperatura para todas las horas intermedias
        temp_map = _interpolate_map(temp_map_raw, 0, 24) if temp_map_raw else {}

        # ── Humedad instante ──
        hum_map_raw = {}
        for hm in dia.get("humedadRelativa", []):
            h = hm.get("hora")
            v = hm.get("value")
            if h is not None and v not in (None, ""):
                try:
                    hum_map_raw[int(h)] = float(v)
                except (ValueError, TypeError):
                    pass
        hum_map = _interpolate_map(hum_map_raw, 0, 24) if hum_map_raw else {}

        # ── Precipitación por periodo — expandir a todas las horas del bloque ──
        # El valor del periodo se reparte entre las horas (solo se muestra en la
        # hora de inicio del bloque para no inflar el total).
        precip_map = {}  # hora → mm (solo hora inicio del bloque)
        for p in dia.get("precipitacion", []):
            rng = _periodo_range(str(p.get("periodo", "")))
            v = _parse_float_precip(p.get("value"))
            if rng is not None and v is not None:
                h_start, h_end = rng
                # Asignar el total del bloque a la hora de inicio
                precip_map[h_start] = precip_map.get(h_start, 0.0) + v

        # ── Probabilidad precipitación — expandir bloques a horas ──
        prob_map = {}
        for p in dia.get("probPrecipitacion", []):
            rng = _periodo_range(str(p.get("periodo", "")))
            v = p.get("value")
            if rng is None or v in (None, ""):
                continue
            try:
                val = int(v)
            except (ValueError, TypeError):
                continue
            h_start, h_end = rng
            for hh in range(h_start, max(h_end, h_start + 1)):
                prob_map[hh] = val

        # ── Viento por periodo — expandir a todas las horas del bloque ──
        wind_map = {}
        gust_map = {}
        for w in dia.get("vientoAndRachaMax", []):
            rng = _periodo_range(str(w.get("periodo", "")))
            if rng is None:
                continue
            h_start, h_end = rng
            vels = w.get("velocidad", [])
            wind_val = None
            if vels:
                try:
                    wind_val = float(vels[0])
                except (ValueError, TypeError, IndexError):
                    pass
            racha = w.get("value")
            gust_val = None
            if racha is not None:
                try:
                    gust_val = float(racha)
                except (ValueError, TypeError):
                    pass
            for hh in range(h_start, max(h_end, h_start + 1)):
                if wind_val is not None:
                    wind_map[hh] = wind_val
                if gust_val is not None:
                    gust_map[hh] = gust_val

        # ── Estado cielo por periodo — expandir a todas las horas del bloque ──
        sky_map = {}
        for s in dia.get("estadoCielo", []):
            rng = _periodo_range(str(s.get("periodo", "")))
            v = s.get("value", "")
            if rng is not None and v:
                h_start, h_end = rng
                for hh in range(h_start, max(h_end, h_start + 1)):
                    if hh not in sky_map:  # no sobreescribir si ya hay dato más específico
                        sky_map[hh] = v

        # ── Generar horas 0-23 completas cuando hay datos de temperatura ──
        if temp_map:
            all_hours = list(range(24))
        else:
            all_hours = sorted(
                set(list(hum_map) + list(precip_map) + list(wind_map) + list(sky_map))
            )

        for hr in all_hours:
            sky_code = sky_map.get(hr, "")
            # Buscar sky_code en horas cercanas si no hay dato exacto
            if not sky_code:
                for delta in range(1, 7):
                    if hr - delta >= 0 and sky_map.get(hr - delta):
                        sky_code = sky_map[hr - delta]
                        break
            sky = _sky_info(sky_code)
            p_mm = precip_map.get(hr, 0.0)
            p_prob = prob_map.get(hr, 0)
            w_kmh = wind_map.get(hr, 0.0)
            # Para horas sin viento exacto, usar el más cercano anterior
            if w_kmh == 0.0 and hr > 0:
                for delta in range(1, 7):
                    if wind_map.get(hr - delta, 0.0) > 0:
                        w_kmh = wind_map[hr - delta]
                        break
            g_kmh = gust_map.get(hr, w_kmh)
            temp = temp_map.get(hr)
            hum = int(hum_map[hr]) if hr in hum_map else None
            wind_level = 0 if w_kmh <= 10 else 1 if w_kmh <= 15 else 2 if w_kmh < 20 else 3
            treatment_ok = p_prob < 20 and w_kmh <= 20.0
            hour_str = f"{hr:02d}:00"
            hourly_list.append({
                "datetime": f"{fecha_str}T{hour_str}",
                "date": fecha_str,
                "hour": hour_str,
                "precipitation": round(p_mm, 1),
                "precipitation_probability": p_prob,
                "wind_speed": round(w_kmh, 1),
                "wind_gusts": round(g_kmh, 1),
                "wind_level": wind_level,
                "temperature": round(temp, 1) if temp is not None else None,
                "humidity": hum,
                "weather_code": sky_code,
                "icon": sky["icon"],
                "label": sky["label"],
                "adverse": sky["adverse"],
                "treatment_ok": treatment_ok,
            })
    return hourly_list


# ── Parseo predicción diaria ──────────────────────────────────────────
def _parse_diaria(raw_list) -> list:
    if not raw_list or not isinstance(raw_list, list):
        return []
    pred_root = raw_list[0]
    dias = pred_root.get("prediccion", {}).get("dia", [])
    daily = []
    for dia in dias:
        fecha_str = (dia.get("fecha") or "")[:10]
        if not fecha_str:
            continue
        # Temperaturas
        temp_data = dia.get("temperatura", {})
        max_temp = min_temp = None
        if isinstance(temp_data, dict):
            try:
                max_temp = float(temp_data.get("maxima") or 0)
                min_temp = float(temp_data.get("minima") or 0)
            except (ValueError, TypeError):
                pass
        # Probabilidad precipitación máx
        prob_precip = 0
        for p in dia.get("probPrecipitacion", []):
            v = p.get("value")
            if v not in (None, ""):
                try:
                    prob_precip = max(prob_precip, int(v))
                except (ValueError, TypeError):
                    pass
        # Precipitación total (suma de todos los periodos del día)
        total_precip = 0.0
        max_precip = 0.0
        for p in dia.get("precipitacion", []):
            v = _parse_float_precip(p.get("value"))
            if v is not None:
                total_precip += v
                max_precip = max(max_precip, v)
        # Viento
        max_wind = 0.0
        for w in dia.get("viento", []):
            v = w.get("velocidad")
            if v not in (None, ""):
                try:
                    max_wind = max(max_wind, float(v))
                except (ValueError, TypeError):
                    pass
        max_gust = max_wind
        for r in (dia.get("rachaMax") or []):
            if not isinstance(r, dict):
                continue
            v = r.get("value")
            if v not in (None, ""):
                try:
                    max_gust = max(max_gust, float(v))
                except (ValueError, TypeError):
                    pass
        # Estado cielo dominante (diurno preferente)
        sky_code = ""
        for s in dia.get("estadoCielo", []):
            v = s.get("value", "")
            if v and not v.endswith("n"):
                sky_code = v
                break
        if not sky_code:
            for s in dia.get("estadoCielo", []):
                v = s.get("value", "")
                if v:
                    sky_code = v
                    break
        sky = _sky_info(sky_code)
        treatment_ok = prob_precip < 20 and max_wind <= 20.0
        # Amanecer / Atardecer
        sunrise = dia.get("orto") or None
        sunset = dia.get("ocaso") or None
        daily.append({
            "date": fecha_str,
            "min_temp": round(min_temp, 1) if min_temp is not None else None,
            "max_temp": round(max_temp, 1) if max_temp is not None else None,
            "max_precipitation_probability": prob_precip,
            "total_precipitation": round(total_precip, 1),
            "max_precipitation": round(max_precip, 1),
            "max_wind_speed": round(max_wind, 1),
            "max_wind_gusts": round(max_gust, 1),
            "dominant_code": sky_code,
            "icon": sky["icon"],
            "label_weather": sky["label"],
            "adverse": sky["adverse"],
            "treatment_ok": treatment_ok,
            "sunrise": sunrise,
            "sunset": sunset,
        })
    return daily


def _synthesize_hours(d_str: str, ds: dict) -> list:
    """Genera horas sintéticas (cada hora) para días sin predicción horaria."""
    p_prob = ds.get("max_precipitation_probability", 0)
    w_kmh = ds.get("max_wind_speed", 0.0)
    g_kmh = ds.get("max_wind_gusts", w_kmh)
    sky_code = ds.get("dominant_code", "")
    sky = _sky_info(sky_code)
    min_t = ds.get("min_temp")
    max_t = ds.get("max_temp")
    wind_level = 0 if w_kmh <= 10 else 1 if w_kmh <= 15 else 2 if w_kmh < 20 else 3
    treatment_ok = p_prob < 20 and w_kmh <= 20.0
    hours = []
    for hr in range(6, 22):  # 06:00 – 21:00, cada hora
        if min_t is not None and max_t is not None:
            factor = max(0.0, min(1.0, (hr - 6) / 9.0)) if hr <= 15 else max(0.0, 1.0 - (hr - 15) / 9.0)
            temp = round(min_t + (max_t - min_t) * factor, 1)
        else:
            temp = None
        hour_str = f"{hr:02d}:00"
        hours.append({
            "datetime": f"{d_str}T{hour_str}",
            "date": d_str, "hour": hour_str,
            "precipitation": 0.0,
            "precipitation_probability": p_prob,
            "wind_speed": round(w_kmh, 1),
            "wind_gusts": round(g_kmh, 1),
            "wind_level": wind_level,
            "temperature": temp,
            "humidity": None,
            "weather_code": sky_code,
            "icon": sky["icon"],
            "label": sky["label"],
            "adverse": sky["adverse"],
            "treatment_ok": treatment_ok,
        })
    return hours


def _interpolate_temps(hours: list, min_t, max_t) -> list:
    """Rellena temperaturas nulas usando una curva diurna simple (mín a las 6h, máx a las 15h)."""
    if min_t is None or max_t is None:
        return hours
    for h in hours:
        if h["temperature"] is None:
            hr = int(h["hour"][:2])
            factor = max(0.0, min(1.0, (hr - 6) / 9.0)) if hr <= 15 else max(0.0, 1.0 - (hr - 15) / 9.0)
            h["temperature"] = round(min_t + (max_t - min_t) * factor, 1)
    return hours


def _fix_snow_icon(entry: dict) -> dict:
    """Si la temperatura máxima es > 6 °C, reemplaza iconos de nieve por lluvia."""
    max_t = entry.get("max_temp")
    if max_t is None or max_t <= 6:
        return entry
    _snow_icons = {"fa-snowflake"}
    if entry.get("icon") in _snow_icons:
        entry["icon"] = "fa-cloud-rain"
        entry["label_weather"] = entry.get("label_weather", "").replace("nieve", "lluvia").replace("Nieve", "Lluvia")
    for h in entry.get("hours", []):
        if h.get("icon") in _snow_icons:
            h["icon"] = "fa-cloud-rain"
            h["label"] = h.get("label", "").replace("nieve", "lluvia").replace("Nieve", "Lluvia")
    return entry


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


# ── Función principal ─────────────────────────────────────────────────
def get_weather_for_field(field) -> dict | None:
    """
    Obtiene la previsión meteorológica para una parcela usando AEMET OpenData.
    Devuelve None si no hay coords, no hay API key, o la API falla.
    """
    api_key = getattr(settings, "AEMET_API_KEY", "")
    if not api_key:
        logger.warning("AEMET_API_KEY no configurada; sin previsión meteorológica")
        return None
    if not getattr(field, "geometry", None):
        return None
    coords = _get_centroid(field.geometry)
    if coords is None:
        return None
    lat, lon = coords
    municipio = _nearest_municipio(lat, lon)
    if not municipio:
        logger.warning("AEMET: no se encontró municipio para lat=%s lon=%s", lat, lon)
        return None
    cod = municipio["cod"]
    logger.debug("AEMET: municipio=%s (%s)", municipio["nombre"], cod)
    # ── Datos ──
    horaria_raw = _aemet_fetch(f"/api/prediccion/especifica/municipio/horaria/{cod}")
    hourly_list = _parse_horaria(horaria_raw) if horaria_raw else []
    diaria_raw = _aemet_fetch(f"/api/prediccion/especifica/municipio/diaria/{cod}")
    daily_summary = _parse_diaria(diaria_raw) if diaria_raw else []
    if not hourly_list and not daily_summary:
        logger.warning("AEMET: sin datos para municipio %s (%s)", municipio["nombre"], cod)
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
        sky = _sky_info(dom_code)
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
            "treatment_ok": max_prob < 20 and max_wind <= 20.0,
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
            entry["hours"] = _interpolate_temps(entry["hours"], entry["min_temp"], entry["max_temp"])
            entry = _fix_snow_icon(entry)
            combined_daily.append(entry)
        elif d_str in daily_summary_map:
            ds = daily_summary_map[d_str]
            year, month, day_num = map(int, d_str.split("-"))
            d_obj = date(year, month, day_num)
            entry = dict(ds)
            entry["label"] = f"{DAY_NAMES[d_obj.weekday()]} {day_num}"
            entry["hours"] = _synthesize_hours(d_str, ds)
            entry.setdefault("sunrise", ds.get("sunrise"))
            entry.setdefault("sunset", ds.get("sunset"))
            entry = _fix_snow_icon(entry)
            combined_daily.append(entry)
    if not combined_daily:
        return None

    # ── Debug info (siempre incluido para diagnóstico) ──
    sample_dia_raw = None
    if diaria_raw and isinstance(diaria_raw, list):
        dias_raw = diaria_raw[0].get("prediccion", {}).get("dia", [])
        if dias_raw:
            d0 = dias_raw[0]
            sample_dia_raw = {
                "fecha": d0.get("fecha", "")[:10],
                "precipitacion_entries": d0.get("precipitacion", []),
                "probPrecipitacion_entries": d0.get("probPrecipitacion", []),
            }
    sample_hora_raw = None
    if horaria_raw and isinstance(horaria_raw, list):
        dias_h = horaria_raw[0].get("prediccion", {}).get("dia", [])
        if dias_h:
            h0 = dias_h[0]
            sample_hora_raw = {
                "fecha": h0.get("fecha", "")[:10],
                "n_temp_entries": len(h0.get("temperatura", [])),
                "temp_horas": [t.get("hora") for t in h0.get("temperatura", [])],
                "precipitacion_entries": h0.get("precipitacion", []),
                "n_hours_generated": len([h for h in hourly_list if h["date"] == (h0.get("fecha", "")[:10])]),
            }

    return {
        "lat": round(lat, 5),
        "lon": round(lon, 5),
        "timezone": "Europe/Madrid",
        "source": "aemet",
        "municipality": municipio["nombre"],
        "hourly": hourly_list,
        "daily": combined_daily,
        "_debug": {
            "horaria_ok": horaria_raw is not None,
            "diaria_ok": diaria_raw is not None,
            "n_hourly_raw": len(hourly_list),
            "n_daily": len(combined_daily),
            "sample_diaria": sample_dia_raw,
            "sample_horaria": sample_hora_raw,
        },
    }
