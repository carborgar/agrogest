"""
Cupo diario del asistente, para toda la instancia.

La clave del proveedor es única, así que el límite es global (hoy hay una sola organización;
el de cada organización se añadirá cuando haya usuarios externos: el uso ya se guarda por organización).

- Preguntas: lo que ve el usuario («Quedan N de 25 hoy»).
- Llamadas al modelo: hasta 3 por pregunta; es lo que cuenta el proveedor. Se comprueba antes de cada una.

La comprobación y el incremento no son atómicos: dos peticiones simultáneas pueden pasarse en una.
Es aceptable porque los límites se configuran con margen por debajo del gratuito, y el 429 del
proveedor sigue siendo la garantía final de no pagar.
"""
from django.conf import settings
from django.db.models import F, Sum
from django.utils import timezone

from assistant.models import AssistantUsage


class QuotaExceeded(Exception):
    pass


def _today():
    return timezone.localdate()


def _totals_today():
    agg = AssistantUsage.objects.filter(date=_today()).aggregate(q=Sum('questions'), c=Sum('calls'))
    return agg['q'] or 0, agg['c'] or 0


def daily_questions():
    return settings.ASSISTANT_DAILY_QUESTIONS


def remaining_questions():
    """Preguntas que quedan hoy. 0 también si se han agotado las llamadas."""
    questions, calls = _totals_today()
    if calls >= settings.ASSISTANT_DAILY_CALLS:
        return 0
    return max(0, settings.ASSISTANT_DAILY_QUESTIONS - questions)


def _bump(organization, **fields):
    row, _ = AssistantUsage.objects.get_or_create(organization=organization, date=_today())
    AssistantUsage.objects.filter(pk=row.pk).update(**{name: F(name) + value for name, value in fields.items()})


def start_question(organization):
    if remaining_questions() <= 0:
        raise QuotaExceeded
    _bump(organization, questions=1)


def reserve_call(organization):
    _, calls = _totals_today()
    if calls >= settings.ASSISTANT_DAILY_CALLS:
        raise QuotaExceeded
    _bump(organization, calls=1)


def record_tokens(organization, input_tokens, output_tokens):
    if input_tokens or output_tokens:
        _bump(organization, input_tokens=input_tokens or 0, output_tokens=output_tokens or 0)
