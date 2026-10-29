"""Parseo de las predicciones municipales de AEMET (horaria y diaria) al formato de la app."""
from collections import Counter
from datetime import date

from weather.treatment_rules import treatment_level, treatment_ok, wind_level

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


def sky_info(code: str) -> dict:
    """Convierte código AEMET estadoCielo a icon/label/adverse."""
    clean = (code or "").rstrip("n").lstrip("0")
    icon, label = _AEMET_SKY_ICONS.get(clean, _DEFAULT_ICON)
    adverse = clean in _ADVERSE_CODES
    return {"icon": icon, "label": label, "adverse": adverse}


# ── Conversión de valores ─────────────────────────────────────────────
def _to_float(v) -> float | None:
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _to_int(v) -> int | None:
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


def _parse_float_precip(v) -> float | None:
    """Convierte valor de precipitación AEMET a float. 'Ip' (inapreciable) → 0.1 mm."""
    if v in (None, ""):
        return None
    s = str(v).strip()
    if s.lower() in ("ip", "inapreciable"):
        return 0.1
    return _to_float(s)


def _periodo_range(periodo) -> tuple[int, int] | None:
    """(inicio, fin) en horas de un periodo AEMET como '0006', '00-06' o '07' (una hora)."""
    p = str(periodo or "").replace("-", "").replace(":", "")
    if len(p) >= 4:
        h_start, h_end = _to_int(p[:2]), _to_int(p[2:4])
        if h_start is not None and h_end is not None:
            return h_start, h_end or 24
    if len(p) >= 2:
        h_start = _to_int(p[:2])
        if h_start is not None:
            return h_start, h_start + 1
    return None


def _block_hours(item: dict) -> range:
    """Horas que cubre el periodo de un dato AEMET (vacío si el periodo no se entiende)."""
    rng = _periodo_range(item.get("periodo", ""))
    if rng is None:
        return range(0)
    h_start, h_end = rng
    return range(h_start, max(h_end, h_start + 1))


def _first(values):
    """Primer elemento de una lista de AEMET (p. ej. `velocidad: ["10"]`), o None."""
    try:
        return values[0]
    except (TypeError, IndexError):
        return None


# ── Parseo predicción horaria ─────────────────────────────────────────
def _interpolate_map(known: dict) -> dict:
    """Interpola linealmente los valores de temp/hum entre horas conocidas."""
    result = dict(known)
    hours = sorted(known)
    for h0, h1 in zip(hours, hours[1:]):
        v0, v1 = known[h0], known[h1]
        for hh in range(h0 + 1, h1):
            t = (hh - h0) / (h1 - h0)
            result[hh] = round(v0 + (v1 - v0) * t, 1)
    return result


def _instant_map(items) -> dict:
    """Valores de una hora exacta (temperatura, humedad), interpolados entre las horas que faltan."""
    known = {}
    for item in items:
        hour, value = _to_int(item.get("hora")), _to_float(item.get("value"))
        if hour is not None and value is not None:
            known[hour] = value
    return _interpolate_map(known)


def _precip_map(items) -> dict:
    """mm por hora. El total del bloque va a su hora de inicio para no inflar el total del día."""
    precip = {}
    for item in items:
        rng = _periodo_range(item.get("periodo", ""))
        value = _parse_float_precip(item.get("value"))
        if rng is not None and value is not None:
            precip[rng[0]] = precip.get(rng[0], 0.0) + value
    return precip


def _prob_map(items) -> dict:
    """Probabilidad de lluvia por hora (cada bloque se extiende a todas sus horas)."""
    prob = {}
    for item in items:
        value = _to_int(item.get("value"))
        if value is not None:
            prob.update(dict.fromkeys(_block_hours(item), value))
    return prob


def _wind_maps(items) -> tuple[dict, dict]:
    """(viento, rachas) por hora. AEMET mezcla en la misma lista datos de viento y de racha."""
    wind, gusts = {}, {}
    for item in items:
        hours = _block_hours(item)
        wind_val = _to_float(_first(item.get("velocidad", [])))
        gust_val = _to_float(item.get("value"))
        if wind_val is not None:
            wind.update(dict.fromkeys(hours, wind_val))
        if gust_val is not None:
            gusts.update(dict.fromkeys(hours, gust_val))
    return wind, gusts


def _sky_map(items) -> dict:
    """Código de cielo por hora; si dos bloques se solapan manda el primero."""
    sky = {}
    for item in items:
        code = item.get("value", "")
        if code:
            for hh in _block_hours(item):
                sky.setdefault(hh, code)
    return sky


def _previous_value(values: dict, hr: int, default):
    """Valor de la hora o, si no lo hay, el de alguna de las 6 horas anteriores."""
    if values.get(hr):
        return values[hr]
    for delta in range(1, 7):
        if hr - delta >= 0 and values.get(hr - delta):
            return values[hr - delta]
    return default


def _wind_at(wind: dict, hr: int) -> float:
    """Viento de la hora; si no hay (o es 0), el más cercano anterior."""
    w_kmh = wind.get(hr, 0.0)
    if w_kmh or hr <= 0:
        return w_kmh
    return _previous_value({h: v for h, v in wind.items() if v > 0}, hr, w_kmh)


def _hour_entry(fecha: str, hr: int, maps: dict) -> dict:
    sky_code = _previous_value(maps["sky"], hr, "")
    sky = sky_info(sky_code)
    p_prob = maps["prob"].get(hr, 0)
    w_kmh = _wind_at(maps["wind"], hr)
    temp = maps["temp"].get(hr)
    hum = maps["hum"].get(hr)
    hour_str = f"{hr:02d}:00"
    return {
        "datetime": f"{fecha}T{hour_str}",
        "date": fecha,
        "hour": hour_str,
        "precipitation": round(maps["precip"].get(hr, 0.0), 1),
        "precipitation_probability": p_prob,
        "wind_speed": round(w_kmh, 1),
        "wind_gusts": round(maps["gusts"].get(hr, w_kmh), 1),
        "wind_level": wind_level(w_kmh),
        "temperature": round(temp, 1) if temp is not None else None,
        "humidity": int(hum) if hum is not None else None,
        "weather_code": sky_code,
        "icon": sky["icon"],
        "label": sky["label"],
        "adverse": sky["adverse"],
        "treatment_ok": treatment_ok(p_prob, w_kmh),
        "level": treatment_level(p_prob, w_kmh),
    }


def _parse_horaria_dia(fecha: str, dia: dict) -> list:
    wind, gusts = _wind_maps(dia.get("vientoAndRachaMax", []))
    maps = {
        "temp": _instant_map(dia.get("temperatura", [])),
        "hum": _instant_map(dia.get("humedadRelativa", [])),
        "precip": _precip_map(dia.get("precipitacion", [])),
        "prob": _prob_map(dia.get("probPrecipitacion", [])),
        "wind": wind,
        "gusts": gusts,
        "sky": _sky_map(dia.get("estadoCielo", [])),
    }
    # Con temperatura se dan las 24 horas; si no, solo las que traen algún dato
    if maps["temp"]:
        hours = range(24)
    else:
        hours = sorted(set(maps["hum"]) | set(maps["precip"]) | set(maps["wind"]) | set(maps["sky"]))
    return [_hour_entry(fecha, hr, maps) for hr in hours]


def _dias(raw_list) -> list:
    if not raw_list or not isinstance(raw_list, list):
        return []
    return raw_list[0].get("prediccion", {}).get("dia", [])


def parse_horaria(raw_list) -> list:
    """Predicción horaria de AEMET → lista de horas de todos los días."""
    hours = []
    for dia in _dias(raw_list):
        fecha = (dia.get("fecha") or "")[:10]
        if fecha:
            hours.extend(_parse_horaria_dia(fecha, dia))
    return hours


# ── Parseo predicción diaria ──────────────────────────────────────────
def _daily_temps(temp_data) -> tuple[float | None, float | None]:
    """(máxima, mínima). Sin máxima válida no se mira la mínima."""
    if not isinstance(temp_data, dict):
        return None, None
    max_temp = _to_float(temp_data.get("maxima") or 0)
    min_temp = _to_float(temp_data.get("minima") or 0) if max_temp is not None else None
    return max_temp, min_temp


def _max_of(values, start):
    return max([start, *(v for v in values if v is not None)])


def _daily_sky_code(items) -> str:
    """Estado del cielo del día: el primero diurno (sin «n») o, si no hay, el primero."""
    codes = [item.get("value", "") for item in items]
    day_codes = [c for c in codes if c and not c.endswith("n")]
    any_codes = [c for c in codes if c]
    return (day_codes or any_codes or [""])[0]


def _parse_diaria_dia(fecha: str, dia: dict) -> dict:
    max_temp, min_temp = _daily_temps(dia.get("temperatura", {}))
    prob_precip = _max_of((_to_int(p.get("value")) for p in dia.get("probPrecipitacion", [])), 0)
    precips = [v for v in (_parse_float_precip(p.get("value")) for p in dia.get("precipitacion", [])) if v is not None]
    max_wind = _max_of((_to_float(w.get("velocidad")) for w in dia.get("viento", [])), 0.0)
    gusts = (_to_float(r.get("value")) for r in (dia.get("rachaMax") or []) if isinstance(r, dict))
    max_gust = _max_of(gusts, max_wind)
    sky_code = _daily_sky_code(dia.get("estadoCielo", []))
    sky = sky_info(sky_code)
    return {
        "date": fecha,
        "min_temp": round(min_temp, 1) if min_temp is not None else None,
        "max_temp": round(max_temp, 1) if max_temp is not None else None,
        "max_precipitation_probability": prob_precip,
        "total_precipitation": round(sum(precips, 0.0), 1),
        "max_precipitation": round(_max_of(precips, 0.0), 1),
        "max_wind_speed": round(max_wind, 1),
        "max_wind_gusts": round(max_gust, 1),
        "dominant_code": sky_code,
        "icon": sky["icon"],
        "label_weather": sky["label"],
        "adverse": sky["adverse"],
        "treatment_ok": treatment_ok(prob_precip, max_wind),
        "level": treatment_level(prob_precip, max_wind),
        "wind_level": wind_level(max_wind),
        "sunrise": dia.get("orto") or None,
        "sunset": dia.get("ocaso") or None,
    }


def parse_diaria(raw_list) -> list:
    """Predicción diaria de AEMET → un resumen por día."""
    return [_parse_diaria_dia(fecha, dia) for dia in _dias(raw_list)
            if (fecha := (dia.get("fecha") or "")[:10])]


# ── Días sin horaria, temperaturas y nieve ────────────────────────────
def _diurnal_temp(hr: int, min_t: float, max_t: float) -> float:
    """Curva diurna simple: mínima a las 6 h, máxima a las 15 h."""
    if hr <= 15:
        factor = max(0.0, min(1.0, (hr - 6) / 9.0))
    else:
        factor = max(0.0, 1.0 - (hr - 15) / 9.0)
    return round(min_t + (max_t - min_t) * factor, 1)


def synthesize_hours(d_str: str, ds: dict) -> list:
    """Genera horas sintéticas (cada hora) para días sin predicción horaria."""
    p_prob = ds.get("max_precipitation_probability", 0)
    w_kmh = ds.get("max_wind_speed", 0.0)
    g_kmh = ds.get("max_wind_gusts", w_kmh)
    sky_code = ds.get("dominant_code", "")
    sky = sky_info(sky_code)
    min_t = ds.get("min_temp")
    max_t = ds.get("max_temp")
    has_temps = min_t is not None and max_t is not None
    hours = []
    for hr in range(6, 22):  # 06:00 – 21:00, cada hora
        hour_str = f"{hr:02d}:00"
        hours.append({
            "datetime": f"{d_str}T{hour_str}",
            "date": d_str, "hour": hour_str,
            "precipitation": 0.0,
            "precipitation_probability": p_prob,
            "wind_speed": round(w_kmh, 1),
            "wind_gusts": round(g_kmh, 1),
            "wind_level": wind_level(w_kmh),
            "temperature": _diurnal_temp(hr, min_t, max_t) if has_temps else None,
            "humidity": None,
            "weather_code": sky_code,
            "icon": sky["icon"],
            "label": sky["label"],
            "adverse": sky["adverse"],
            "treatment_ok": treatment_ok(p_prob, w_kmh),
            "level": treatment_level(p_prob, w_kmh),
        })
    return hours


def interpolate_temps(hours: list, min_t, max_t) -> None:
    """Rellena (en la propia lista) las temperaturas nulas con la curva diurna."""
    if min_t is None or max_t is None:
        return
    for h in hours:
        if h["temperature"] is None:
            h["temperature"] = _diurnal_temp(int(h["hour"][:2]), min_t, max_t)


def _rain_instead_of_snow(text: str) -> str:
    return text.replace("nieve", "lluvia").replace("Nieve", "Lluvia")


def fix_snow_icon(entry: dict) -> None:
    """Si la temperatura máxima es > 6 °C, cambia (en el propio día) los iconos de nieve por lluvia."""
    max_t = entry.get("max_temp")
    if max_t is None or max_t <= 6:
        return
    if entry.get("icon") == "fa-snowflake":
        entry["icon"] = "fa-cloud-rain"
        entry["label_weather"] = _rain_instead_of_snow(entry.get("label_weather", ""))
    for h in entry.get("hours", []):
        if h.get("icon") == "fa-snowflake":
            h["icon"] = "fa-cloud-rain"
            h["label"] = _rain_instead_of_snow(h.get("label", ""))


# ── Unión de horaria y diaria ─────────────────────────────────────────
def _day_label(d_str: str) -> str:
    year, month, day_num = map(int, d_str.split("-"))
    return f"{DAY_NAMES[date(year, month, day_num).weekday()]} {day_num}"


def _dominant_code(hours: list) -> str:
    """Cielo más repetido entre las 6 y las 20 h (en empate, el primero que aparece)."""
    daytime = [h["weather_code"] for h in hours if 6 <= int(h["hour"][:2]) <= 20]
    if daytime:
        return Counter(daytime).most_common(1)[0][0]
    return hours[0]["weather_code"] if hours else ""


def _day_from_hours(d_str: str, hours: list) -> dict:
    max_prob = max(h["precipitation_probability"] for h in hours)
    max_wind = max(h["wind_speed"] for h in hours)
    temps = [h["temperature"] for h in hours if h["temperature"] is not None]
    dom_code = _dominant_code(hours)
    sky = sky_info(dom_code)
    return {
        "date": d_str,
        "label": _day_label(d_str),
        "total_precipitation": round(sum(h["precipitation"] for h in hours), 1),
        "max_precipitation": round(max(h["precipitation"] for h in hours), 1),
        "max_precipitation_probability": max_prob,
        "max_wind_speed": round(max_wind, 1),
        "max_wind_gusts": round(max(h["wind_gusts"] for h in hours), 1),
        "min_temp": round(min(temps), 1) if temps else None,
        "max_temp": round(max(temps), 1) if temps else None,
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


def _complete_with_daily(entry: dict, ds: dict) -> None:
    """Rellena con la diaria lo que la horaria no trae (temperaturas, sol, lluvia)."""
    for key in ("min_temp", "max_temp"):
        if entry[key] is None:
            entry[key] = ds.get(key)
    for key in ("sunrise", "sunset"):
        if not entry.get(key):
            entry[key] = ds.get(key)
    if not entry.get("total_precipitation", 0.0) and ds.get("total_precipitation", 0.0) > 0:
        entry["total_precipitation"] = ds["total_precipitation"]
        entry["max_precipitation"] = ds.get("max_precipitation", 0.0)


def _day_from_daily(d_str: str, ds: dict) -> dict:
    entry = dict(ds)
    entry["label"] = _day_label(d_str)
    entry["hours"] = synthesize_hours(d_str, ds)
    entry.setdefault("sunrise", ds.get("sunrise"))
    entry.setdefault("sunset", ds.get("sunset"))
    return entry


def build_days(hourly_list: list, daily_summary: list) -> list:
    """Une las horas (horaria) con el resumen de cada día (diaria): hasta 7 días con sus horas."""
    by_date: dict[str, list] = {}
    for h in hourly_list:
        by_date.setdefault(h["date"], []).append(h)
    from_hours = {d_str: _day_from_hours(d_str, hours) for d_str, hours in by_date.items()}
    summary = {d["date"]: d for d in daily_summary}
    days = []
    for d_str in sorted(set(from_hours) | set(summary))[:7]:
        if d_str in from_hours:
            entry = from_hours[d_str]
            if d_str in summary:
                _complete_with_daily(entry, summary[d_str])
            interpolate_temps(entry["hours"], entry["min_temp"], entry["max_temp"])
        else:
            entry = _day_from_daily(d_str, summary[d_str])
        fix_snow_icon(entry)
        days.append(entry)
    return days
