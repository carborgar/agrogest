"""Parseo de las predicciones municipales de AEMET (horaria y diaria) al formato de la app."""
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


def parse_horaria(raw_list) -> list:
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
            sky = sky_info(sky_code)
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
            w_level = wind_level(w_kmh)
            t_ok = treatment_ok(p_prob, w_kmh)
            hour_str = f"{hr:02d}:00"
            hourly_list.append({
                "datetime": f"{fecha_str}T{hour_str}",
                "date": fecha_str,
                "hour": hour_str,
                "precipitation": round(p_mm, 1),
                "precipitation_probability": p_prob,
                "wind_speed": round(w_kmh, 1),
                "wind_gusts": round(g_kmh, 1),
                "wind_level": w_level,
                "temperature": round(temp, 1) if temp is not None else None,
                "humidity": hum,
                "weather_code": sky_code,
                "icon": sky["icon"],
                "label": sky["label"],
                "adverse": sky["adverse"],
                "treatment_ok": t_ok,
                "level": treatment_level(p_prob, w_kmh),
            })
    return hourly_list


# ── Parseo predicción diaria ──────────────────────────────────────────
def parse_diaria(raw_list) -> list:
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
        sky = sky_info(sky_code)
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
            "treatment_ok": treatment_ok(prob_precip, max_wind),
            "level": treatment_level(prob_precip, max_wind),
            "wind_level": wind_level(max_wind),
            "sunrise": sunrise,
            "sunset": sunset,
        })
    return daily


def synthesize_hours(d_str: str, ds: dict) -> list:
    """Genera horas sintéticas (cada hora) para días sin predicción horaria."""
    p_prob = ds.get("max_precipitation_probability", 0)
    w_kmh = ds.get("max_wind_speed", 0.0)
    g_kmh = ds.get("max_wind_gusts", w_kmh)
    sky_code = ds.get("dominant_code", "")
    sky = sky_info(sky_code)
    min_t = ds.get("min_temp")
    max_t = ds.get("max_temp")
    w_level = wind_level(w_kmh)
    t_ok = treatment_ok(p_prob, w_kmh)
    level = treatment_level(p_prob, w_kmh)
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
            "wind_level": w_level,
            "temperature": temp,
            "humidity": None,
            "weather_code": sky_code,
            "icon": sky["icon"],
            "label": sky["label"],
            "adverse": sky["adverse"],
            "treatment_ok": t_ok,
            "level": level,
        })
    return hours


def interpolate_temps(hours: list, min_t, max_t) -> list:
    """Rellena temperaturas nulas usando una curva diurna simple (mín a las 6h, máx a las 15h)."""
    if min_t is None or max_t is None:
        return hours
    for h in hours:
        if h["temperature"] is None:
            hr = int(h["hour"][:2])
            factor = max(0.0, min(1.0, (hr - 6) / 9.0)) if hr <= 15 else max(0.0, 1.0 - (hr - 15) / 9.0)
            h["temperature"] = round(min_t + (max_t - min_t) * factor, 1)
    return hours


def fix_snow_icon(entry: dict) -> dict:
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
