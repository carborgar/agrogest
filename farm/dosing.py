"""
Fórmulas de dosis, en un solo sitio.

Las usan los modelos (total de un tratamiento, coste/ha, dosis por carga) y el asistente,
para que una misma pregunta dé siempre la misma cifra en cualquier pantalla.
Aritmética Decimal exacta; el redondeo lo decide quien llama.
"""
from decimal import Decimal

PER_HA = ('kg_per_ha', 'l_per_ha')
PER_1000L = ('kg_per_1000l', 'l_per_1000l')
PCT = 'pct'

# Carga parcial: solo cuenta si quedan más de estos litros
PARTIAL_LOAD_MIN_L = 50


def _d(value):
    """Número → Decimal por su representación decimal (ver farm.models._d)."""
    return value if isinstance(value, Decimal) else Decimal(str(value))


def unit_for(dose_type):
    """Unidad del producto según su tipo de dosis: kg para kg_*, L para el resto (incluido %)."""
    return 'kg' if dose_type and dose_type.startswith('kg_') else 'L'


def amount_per_ha(dose, dose_type, water_per_ha=None):
    """
    Producto (L o kg) por hectárea.

    Las dosis por hectárea no dependen del agua; las de caldo (por 1000 L y %) usan `water_per_ha`.
    None si el tipo no se conoce o falta el agua que necesita.
    """
    dose = _d(dose)
    if dose_type in PER_HA:
        return dose
    if dose_type in PER_1000L or dose_type == PCT:
        if not water_per_ha:
            return None
        water = _d(water_per_ha)
        return dose * water / 1000 if dose_type in PER_1000L else dose / Decimal(100) * water
    return None


def amount_for_water(dose, dose_type, water_l, water_per_ha=None):
    """
    Producto (L o kg) para `water_l` litros de caldo: una carga de máquina, la carga parcial…

    Las dosis por hectárea se reparten según el mojado (`water_per_ha`). Incluye el tipo antiguo
    «por 2000 L», que ya no se ofrece pero puede seguir en datos guardados.
    None si el tipo no se conoce o falta el mojado que necesita.
    """
    if not dose_type:
        return None
    dose, water = _d(dose), _d(water_l)
    if 'ha' in dose_type:
        return dose * water / _d(water_per_ha) if water_per_ha else None
    if '1000l' in dose_type:
        return dose * water / 1000
    if '2000l' in dose_type:
        return dose * water / 2000
    if 'pct' in dose_type:
        return dose * water / 100
    return None


def machine_loads(total_water, capacity):
    """Cargas completas y parcial para `total_water` litros con una máquina de `capacity` litros."""
    total_water, capacity = int(total_water), int(capacity)
    partial_water = total_water % capacity
    return {
        'total_water': total_water,
        'full_loads': total_water // capacity,
        'partial_load': partial_water > PARTIAL_LOAD_MIN_L,
        'partial_water': partial_water,
    }
