"""Umbrales para decidir si se puede tratar según lluvia y viento (únicos para toda la app)."""
# «ok»: se puede pulverizar; «bad»: lluvia probable o viento fuerte; «warn»: en medio.
OK_RAIN_PROB = 20
OK_WIND_KMH = 20
BAD_RAIN_PROB = 50
BAD_WIND_KMH = 25


def wind_level(kmh: float) -> int:
    """0-3 para colorear el viento: ≤10, ≤15, <20, ≥20 km/h."""
    return 0 if kmh <= 10 else 1 if kmh <= 15 else 2 if kmh < 20 else 3


def treatment_ok(rain_prob: float, wind_kmh: float) -> bool:
    return rain_prob < OK_RAIN_PROB and wind_kmh <= OK_WIND_KMH


def treatment_level(rain_prob: float, wind_kmh: float) -> str:
    if treatment_ok(rain_prob, wind_kmh):
        return "ok"
    if rain_prob >= BAD_RAIN_PROB or wind_kmh > BAD_WIND_KMH:
        return "bad"
    return "warn"
