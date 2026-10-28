"""Fechas «de campo»: el «hoy» que ven los usuarios, que no es el de UTC."""
from datetime import date
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.utils import timezone


def local_today() -> date:
    """
    Fecha de hoy en la zona horaria de las explotaciones (settings.FARM_TIME_ZONE, por defecto Europe/Madrid).

    TIME_ZONE del proyecto es UTC, así que date.today() y timezone.localdate() van por detrás de España entre
    las 00:00 y las 02:00: el formulario de tratamiento ofrecía «ayer» y rechazaba como futura la fecha de
    realización de «hoy». Esta función solo cambia el «hoy» (no TIME_ZONE ni cómo se guardan las fechas).
    Si el sistema no tiene la base de datos de zonas horarias, vuelve a la fecha de TIME_ZONE.
    """
    try:
        tz = ZoneInfo(getattr(settings, 'FARM_TIME_ZONE', 'Europe/Madrid'))
    except ZoneInfoNotFoundError:
        return timezone.localdate()
    return timezone.now().astimezone(tz).date()
