"""Parseo de AEMET contra una respuesta de ejemplo con el formato real (Alcalá del Río, 41005).

`forecast_41005.json` es la salida esperada. Si un cambio la altera a propósito, se regenera
y se revisa el diff del JSON: así se ve exactamente qué cambia para el usuario.
"""
import json
from pathlib import Path

import pytest

from weather.aemet.parsers import _dominant_code, _periodo_range, build_days, parse_diaria, parse_horaria

FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_forecast_matches_the_expected_output():
    days = build_days(parse_horaria(load("aemet_horaria_41005.json")), parse_diaria(load("aemet_diaria_41005.json")))
    assert days == load("forecast_41005.json")


def test_only_daily_gives_synthetic_hours():
    days = build_days([], parse_diaria(load("aemet_diaria_41005.json")))
    assert len(days) == 7
    assert all(len(d["hours"]) == 16 for d in days)


def test_snow_icon_becomes_rain_when_it_is_warm():
    days = {d["date"]: d for d in build_days([], parse_diaria(load("aemet_diaria_41005.json")))}
    assert days["2026-10-30"]["icon"] == "fa-cloud-showers-heavy"   # 36: cubierto con lluvia
    assert days["2026-11-01"]["icon"] == "fa-snowflake"              # 46 con máxima de 5 °C: nieve


@pytest.mark.parametrize("raw", [None, [], {}, [{"prediccion": {}}]])
def test_empty_or_unexpected_answers_give_no_days(raw):
    assert parse_horaria(raw) == [] and parse_diaria(raw) == []


@pytest.mark.parametrize("periodo,expected", [
    ("0814", (8, 14)), ("2000", (20, 24)), ("00-06", (0, 6)), ("07", (7, 8)),
    ("", None), (None, None), ("xx", None), ("08xx", (8, 9)),
])
def test_periodo_range(periodo, expected):
    assert _periodo_range(periodo) == expected


def test_dominant_sky_on_a_tie_is_the_first_one():
    hours = [{"hour": f"{h:02d}:00", "weather_code": code} for h, code in ((8, "14"), (9, "12"), (10, "12"), (11, "14"))]
    assert _dominant_code(hours) == "14"
