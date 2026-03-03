"""
Servicio para obtener previsión meteorológica de una parcela.

Usa la API gratuita de Open-Meteo (https://open-meteo.com/).
No requiere API key. Incluye datos de lluvia y viento por horas,
ideales para planificar tratamientos fitosanitarios.
"""
import json
import logging
import ssl
from datetime import date

import urllib.request
import urllib.parse
import urllib.error

logger = logging.getLogger(__name__)

# Variables que pedimos a Open-Meteo (previsión horaria)
HOURLY_VARIABLES = [
    "precipitation",              # mm – lluvia acumulada en esa hora
    "precipitation_probability",  # % – probabilidad de precipitación
    "wind_speed_10m",             # km/h – viento a 10m
    "wind_gusts_10m",             # km/h – ráfagas
    "weather_code",               # WMO código de tiempo
    "temperature_2m",             # ºC
    "relative_humidity_2m",       # %
]

# Días de previsión a obtener (máximo 16 en tier free)
FORECAST_DAYS = 7


def _get_centroid(geometry_json: str) -> tuple[float, float] | None:
    """
    Devuelve (lat, lon) del centroide de un GeoJSON (Polygon/MultiPolygon).
    Si no puede calcularlo, devuelve None.
    """
    try:
        geojson = json.loads(geometry_json)
    except (json.JSONDecodeError, TypeError):
        return None

    geo_type = geojson.get("type")
    coords = geojson.get("coordinates")
    if not coords:
        return None

    # Aplanar a lista de (lon, lat) según tipo
    if geo_type == "Point":
        lon, lat = coords[0], coords[1]
        return lat, lon

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


# Mapeo básico de WMO weather codes a iconos FontAwesome y etiqueta en español
_WMO_ICONS = {
    0: ("fa-sun", "Despejado"),
    1: ("fa-sun", "Mayormente despejado"),
    2: ("fa-cloud-sun", "Parcialmente nublado"),
    3: ("fa-cloud", "Nublado"),
    45: ("fa-smog", "Niebla"),
    48: ("fa-smog", "Niebla helada"),
    51: ("fa-cloud-drizzle", "Llovizna ligera"),
    53: ("fa-cloud-drizzle", "Llovizna moderada"),
    55: ("fa-cloud-drizzle", "Llovizna densa"),
    61: ("fa-cloud-rain", "Lluvia ligera"),
    63: ("fa-cloud-rain", "Lluvia moderada"),
    65: ("fa-cloud-showers-heavy", "Lluvia intensa"),
    71: ("fa-snowflake", "Nevada ligera"),
    73: ("fa-snowflake", "Nevada moderada"),
    75: ("fa-snowflake", "Nevada intensa"),
    80: ("fa-cloud-sun-rain", "Chubascos ligeros"),
    81: ("fa-cloud-sun-rain", "Chubascos moderados"),
    82: ("fa-cloud-showers-heavy", "Chubascos intensos"),
    95: ("fa-bolt", "Tormenta"),
    96: ("fa-bolt", "Tormenta con granizo"),
    99: ("fa-bolt", "Tormenta intensa con granizo"),
}

_DEFAULT_ICON = ("fa-question", "Desconocido")


def _wmo_info(code: int) -> dict:
    icon, label = _WMO_ICONS.get(code, _DEFAULT_ICON)
    # Determina si el código implica condiciones adversas para tratamientos
    adverse = code in {45, 48, 51, 53, 55, 61, 63, 65, 71, 73, 75, 80, 81, 82, 95, 96, 99}
    return {"icon": icon, "label": label, "adverse": adverse}


def get_weather_for_field(field) -> dict | None:
    """
    Obtiene la previsión meteorológica para una parcela.

    Parámetros
    ----------
    field : Farm.Field con atributo `geometry` (GeoJSON string, puede estar vacío)

    Devuelve
    --------
    dict con estructura:
        {
            "lat": float,
            "lon": float,
            "timezone": str,
            "hourly": [
                {
                    "datetime": "2025-01-01T08:00",
                    "date": "2025-01-01",
                    "hour": "08:00",
                    "precipitation": float,    # mm
                    "wind_speed": float,       # km/h
                    "wind_gusts": float,       # km/h
                    "temperature": float,      # ºC
                    "humidity": int,           # %
                    "weather_code": int,
                    "icon": str,               # clase FA
                    "label": str,              # texto en español
                    "adverse": bool,           # condición adversa para tratar
                    "treatment_ok": bool,      # apto para tratar (sin lluvia y viento OK)
                },
                ...
            ],
            "daily": [
                {
                    "date": "2025-01-01",
                    "label": "Lun 1",
                    "max_precipitation": float,
                    "max_wind_speed": float,
                    "max_wind_gusts": float,
                    "min_temp": float,
                    "max_temp": float,
                    "dominant_code": int,
                    "icon": str,
                    "label_weather": str,
                    "adverse": bool,
                    "treatment_ok": bool,
                    "hours": [ ... ]  # lista de hourly de ese día
                },
                ...
            ]
        }
    o None si la parcela no tiene coordenadas o la API falla.
    """
    coords = None

    # Intentar extraer centroide del GeoJSON
    if field.geometry:
        coords = _get_centroid(field.geometry)

    if coords is None:
        return None

    lat, lon = coords

    params = urllib.parse.urlencode({
        "latitude": round(lat, 5),
        "longitude": round(lon, 5),
        "hourly": ",".join(HOURLY_VARIABLES),
        "forecast_days": FORECAST_DAYS,
        "timezone": "auto",
        "wind_speed_unit": "kmh",
    })

    url = f"https://api.open-meteo.com/v1/forecast?{params}"

    # En producción se usa el contexto SSL por defecto.
    # En macOS de desarrollo, Python a veces no tiene los certificados del sistema,
    # así que hacemos un segundo intento sin verificar si el primero falla.
    data = None
    for ctx in (ssl.create_default_context(), ssl._create_unverified_context()):  # noqa: S501
        try:
            with urllib.request.urlopen(url, timeout=5, context=ctx) as response:
                data = json.loads(response.read().decode())
            break
        except (urllib.error.URLError, OSError) as exc:
            logger.debug("Open-Meteo intento fallido: %s", exc)

    if data is None:
        logger.warning("No se pudieron obtener datos de Open-Meteo para lat=%s lon=%s", lat, lon)
        return None

    hourly = data.get("hourly", {})
    times = hourly.get("time", [])
    precip = hourly.get("precipitation", [])
    precip_prob = hourly.get("precipitation_probability", [])
    wind = hourly.get("wind_speed_10m", [])
    gusts = hourly.get("wind_gusts_10m", [])
    codes = hourly.get("weather_code", [])
    temps = hourly.get("temperature_2m", [])
    humidity = hourly.get("relative_humidity_2m", [])

    hourly_list = []
    for i, dt_str in enumerate(times):
        code = int(codes[i]) if i < len(codes) and codes[i] is not None else 0
        p = float(precip[i]) if i < len(precip) and precip[i] is not None else 0.0
        pp = int(precip_prob[i]) if i < len(precip_prob) and precip_prob[i] is not None else 0
        w = float(wind[i]) if i < len(wind) and wind[i] is not None else 0.0
        g = float(gusts[i]) if i < len(gusts) and gusts[i] is not None else 0.0
        t = float(temps[i]) if i < len(temps) and temps[i] is not None else None
        h = int(humidity[i]) if i < len(humidity) and humidity[i] is not None else None
        wmo = _wmo_info(code)

        # Nivel de viento: 0=verde(≤10), 1=amarillo(10-15), 2=naranja(15-20), 3=rojo(≥20)
        if w <= 10:
            wind_level = 0
        elif w <= 15:
            wind_level = 1
        elif w < 20:
            wind_level = 2
        else:
            wind_level = 3

        # Apto para tratar: prob lluvia < 20% y viento ≤ 20 km/h
        treatment_ok = pp < 20 and w <= 20.0

        date_part, hour_part = dt_str[:10], dt_str[11:16]
        hourly_list.append({
            "datetime": dt_str,
            "date": date_part,
            "hour": hour_part,
            "precipitation": p,
            "precipitation_probability": pp,
            "wind_speed": w,
            "wind_gusts": g,
            "wind_level": wind_level,
            "temperature": t,
            "humidity": h,
            "weather_code": code,
            "icon": wmo["icon"],
            "label": wmo["label"],
            "adverse": wmo["adverse"],
            "treatment_ok": treatment_ok,
        })

    # Agrupar por día
    days_map: dict[str, list] = {}
    for h in hourly_list:
        days_map.setdefault(h["date"], []).append(h)

    DAY_NAMES = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]

    daily_list = []
    for d_str, hours in days_map.items():
        year, month, day = map(int, d_str.split("-"))
        d = date(year, month, day)
        weekday_label = f"{DAY_NAMES[d.weekday()]} {day}"

        max_precip = max(h["precipitation"] for h in hours)
        total_precip = round(sum(h["precipitation"] for h in hours), 1)
        max_precip_prob = max(h["precipitation_probability"] for h in hours)
        max_wind = max(h["wind_speed"] for h in hours)
        max_gusts = max(h["wind_gusts"] for h in hours)
        temps_day = [h["temperature"] for h in hours if h["temperature"] is not None]
        min_temp = round(min(temps_day), 1) if temps_day else None
        max_temp = round(max(temps_day), 1) if temps_day else None

        # Código dominante: el más frecuente durante las horas diurnas (6–20h)
        daytime_codes = [h["weather_code"] for h in hours if 6 <= int(h["hour"][:2]) <= 20]
        if daytime_codes:
            dominant_code = max(set(daytime_codes), key=daytime_codes.count)
        else:
            dominant_code = hours[0]["weather_code"]

        wmo_day = _wmo_info(dominant_code)
        treatment_ok_day = max_precip_prob < 20 and max_wind <= 20.0

        daily_list.append({
            "date": d_str,
            "label": weekday_label,
            "total_precipitation": total_precip,
            "max_precipitation": round(max_precip, 1),
            "max_precipitation_probability": max_precip_prob,
            "max_wind_speed": round(max_wind, 1),
            "max_wind_gusts": round(max_gusts, 1),
            "min_temp": min_temp,
            "max_temp": max_temp,
            "dominant_code": dominant_code,
            "icon": wmo_day["icon"],
            "label_weather": wmo_day["label"],
            "adverse": wmo_day["adverse"],
            "treatment_ok": treatment_ok_day,
            "hours": hours,
        })

    return {
        "lat": lat,
        "lon": lon,
        "timezone": data.get("timezone", "auto"),
        "hourly": hourly_list,
        "daily": daily_list,
    }


