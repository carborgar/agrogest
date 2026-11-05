"""
Cliente de cualquier proveedor compatible con OpenAI (`POST {base_url}/chat/completions`).

Gemini, Groq u OpenRouter aceptan este formato con herramientas: cambiar de proveedor es cambiar
ASSISTANT_BASE_URL, ASSISTANT_API_KEY y ASSISTANT_MODEL. Sin SDK: urllib, igual que weather/aemet/client.py.
Sin reintentos: reintentar gasta cupo.
"""
import json
import logging
import socket
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import certifi
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

MAX_OUTPUT_TOKENS = 700


class ProviderError(Exception):
    """Fallo del proveedor. `user_message` es lo que se enseña."""
    user_message = 'El asistente no está disponible ahora mismo. Inténtalo más tarde.'


class RateLimited(ProviderError):
    user_message = 'El proveedor ha llegado a su límite. Espera un minuto y vuelve a intentarlo.'


class DailyLimit(RateLimited):
    user_message = 'El proveedor ha agotado su cupo gratuito de hoy. El asistente vuelve mañana.'


class ModelUnavailable(ProviderError):
    """El modelo no existe o se ha retirado (404): se salta igual que uno agotado."""


class ProviderTimeout(ProviderError):
    user_message = 'El asistente ha tardado demasiado en responder. Inténtalo de nuevo.'


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str


@dataclass
class Completion:
    content: str
    tool_calls: list = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    message: dict = field(default_factory=dict)  # mensaje del asistente tal cual, para reenviarlo


class OpenAICompatibleProvider:
    def __init__(self, api_key, base_url, model, reasoning_effort=''):
        self.api_key = api_key
        self.url = base_url.rstrip('/') + '/chat/completions'
        self.model = model
        self.reasoning_effort = reasoning_effort

    def complete(self, messages, tools, timeout, tool_choice='auto'):
        body = {'model': self.model, 'messages': messages, 'max_tokens': MAX_OUTPUT_TOKENS}
        if tools:
            body['tools'] = tools
            body['tool_choice'] = tool_choice
        if self.reasoning_effort:
            body['reasoning_effort'] = self.reasoning_effort
        request = urllib.request.Request(
            self.url,
            data=json.dumps(body).encode(),
            headers={'Authorization': f'Bearer {self.api_key}', 'Content-Type': 'application/json'},
            method='POST',
        )
        context = ssl.create_default_context(cafile=certifi.where())
        try:
            with urllib.request.urlopen(request, timeout=max(1.0, timeout), context=context) as response:
                data = json.load(response)
        except urllib.error.HTTPError as exc:
            detail = exc.read()[:300].decode(errors='replace') if exc.fp else ''
            logger.warning('Asistente: HTTP %s del proveedor: %s', exc.code, detail)
            if exc.code == 429:
                # Gemini indica qué cuota se ha agotado (p. ej. «…PerDay…») en el cuerpo del error
                raise (DailyLimit() if 'perday' in detail.lower().replace(' ', '') else RateLimited()) from exc
            if exc.code == 404:
                raise ModelUnavailable() from exc
            raise ProviderError() from exc
        except (TimeoutError, socket.timeout) as exc:
            raise ProviderTimeout() from exc
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                raise ProviderTimeout() from exc
            logger.warning('Asistente: error de red: %s', exc)
            raise ProviderError() from exc
        except (OSError, ValueError) as exc:
            logger.warning('Asistente: error de red o respuesta no válida: %s', exc)
            raise ProviderError() from exc
        return self._parse(data)

    @staticmethod
    def _parse(data):
        try:
            message = data['choices'][0]['message']
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError() from exc
        calls = [
            ToolCall(id=c.get('id', ''), name=c.get('function', {}).get('name', ''),
                     arguments=c.get('function', {}).get('arguments') or '{}')
            for c in message.get('tool_calls') or []
        ]
        usage = data.get('usage') or {}
        clean = {'role': 'assistant', 'content': message.get('content') or ''}
        if message.get('tool_calls'):
            # Tal cual: lleva los campos extra del proveedor (p. ej. la firma de razonamiento de Gemini)
            clean['tool_calls'] = message['tool_calls']
            clean['content'] = message.get('content')  # null, como en el formato de OpenAI
        return Completion(
            content=message.get('content') or '',
            tool_calls=calls,
            input_tokens=usage.get('prompt_tokens') or 0,
            output_tokens=usage.get('completion_tokens') or 0,
            message=clean,
        )


def is_configured():
    return bool(settings.ASSISTANT_API_KEY and configured_models())


def get_provider(model):
    return OpenAICompatibleProvider(
        settings.ASSISTANT_API_KEY, settings.ASSISTANT_BASE_URL, model, settings.ASSISTANT_REASONING_EFFORT,
    )


# ── Varios modelos: cuando uno se agota, el siguiente ─────────────────────────
# El cupo diario de Gemini se renueva a medianoche de California.
QUOTA_RESET_TZ = ZoneInfo('America/Los_Angeles')


def configured_models():
    return [m.strip() for m in settings.ASSISTANT_MODEL.split(',') if m.strip()]


def _exhausted_key(model):
    return f'assistant:exhausted:{model}'


# Un 404 puede ser un nombre mal escrito o un fallo puntual: se vuelve a probar antes que un cupo agotado.
UNAVAILABLE_TTL = 3600
RESET_MARGIN = 60  # no volver a probar justo en el segundo del reset


def seconds_until_reset(now=None):
    """Segundos hasta la próxima medianoche de California (en UTC, para que los cambios de hora no descuadren)."""
    now = now or datetime.now(QUOTA_RESET_TZ)
    midnight = (now.astimezone(QUOTA_RESET_TZ) + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    delta = midnight.astimezone(timezone.utc) - now.astimezone(timezone.utc)
    return max(60, int(delta.total_seconds()) + RESET_MARGIN)


def mark_exhausted(model, reason='cupo diario agotado'):
    """Apunta el modelo para no volver a probarlo: hasta el reset del cupo, o una hora si no existe (404)."""
    unavailable = reason != 'cupo diario agotado'
    logger.warning('Asistente: modelo %s: %s; se pasa al siguiente.', model, reason)
    cache.set(_exhausted_key(model), True, UNAVAILABLE_TTL if unavailable else seconds_until_reset())


def available_models():
    """Modelos de la lista que no están apuntados como agotados, en orden."""
    return [m for m in configured_models() if not cache.get(_exhausted_key(m))]
