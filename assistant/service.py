"""
Bucle de una pregunta: modelo ↔ herramientas, con plazo y cupo.

- Máx. 3 vueltas; en la última se fuerza texto (tool_choice="none").
- Plazo global por pregunta (ASSISTANT_TIMEOUT); cada llamada usa lo que quede.
- El cupo se reserva antes de cada llamada al modelo.
- Se ejecutan como mucho MAX_TOOLS_PER_ROUND tool_calls por respuesta.
- Varios modelos (ASSISTANT_MODEL): si uno agota su cupo diario o ya no existe, se apunta como agotado
  y la pregunta se repite desde el principio con el siguiente. Desde el principio porque los modelos 3.x
  firman sus llamadas a herramientas y otro modelo podría rechazar esa firma.
"""
import logging
import time
from dataclasses import asdict, dataclass, field

from django.conf import settings
from django.utils import timezone

from assistant import providers, quota
from assistant.prompts import system_prompt
from assistant.providers import DailyLimit, ModelUnavailable, ProviderError
from assistant.tools import ToolContext, available_tools, run_tool

logger = logging.getLogger(__name__)

MAX_ROUNDS = 3
HISTORY_TURNS = 4
MAX_QUESTION_CHARS = 500
MIN_SECONDS_FOR_CALL = 3
MAX_TOOLS_PER_ROUND = 5
MAX_TABLES_PER_TURN = 4

QUOTA_MESSAGE = 'Has usado las preguntas de hoy. El asistente vuelve mañana; el resto de AgroGest sigue funcionando.'


@dataclass
class Turn:
    question: str
    answer: str = ''
    understood: list = field(default_factory=list)
    tables: list = field(default_factory=list)
    candidates: list = field(default_factory=list)
    error: bool = False

    def as_dict(self):
        return asdict(self)

    def history_text(self):
        """Lo que se reenvía al modelo en el historial: la respuesta y los candidatos, sin tablas."""
        text = self.answer
        if self.candidates:
            text += '\n(Candidatos: ' + ', '.join(self.candidates) + ')'
        return text


def _history_messages(history):
    messages = []
    for turn in history[-HISTORY_TURNS:]:
        if turn.get('error') or 'question' not in turn:
            continue
        known = {k: v for k, v in turn.items() if k in Turn.__dataclass_fields__}
        messages.append({'role': 'user', 'content': turn['question']})
        messages.append({'role': 'assistant', 'content': Turn(**known).history_text()})
    return messages


def _run(provider, base_messages, turn, ctx, deadline, clock):
    """Una pasada completa de la pregunta con un modelo. Lanza DailyLimit/ModelUnavailable para cambiar."""
    tools = available_tools()
    by_name = {t.name: t for t in tools}
    schemas = [t.schema() for t in tools]
    messages = list(base_messages)
    for round_ in range(MAX_ROUNDS):
        remaining = deadline - clock()
        if remaining < MIN_SECONDS_FOR_CALL:
            turn.answer = turn.answer or 'Se ha acabado el tiempo para esta pregunta. Prueba a hacerla más concreta.'
            turn.error = not turn.tables
            return
        quota.reserve_call(ctx.organization)
        last = round_ == MAX_ROUNDS - 1
        completion = provider.complete(messages, schemas, timeout=remaining,
                                       tool_choice='none' if last else 'auto')
        quota.record_tokens(ctx.organization, completion.input_tokens, completion.output_tokens)
        if not completion.tool_calls or last:
            turn.answer = completion.content.strip() or turn.answer
            return
        messages.append(completion.message)
        for i, call in enumerate(completion.tool_calls):
            if i >= MAX_TOOLS_PER_ROUND:  # cada tool_call necesita respuesta, aunque no se ejecute
                messages.append({'role': 'tool', 'tool_call_id': call.id,
                                 'content': 'ERROR: demasiadas consultas a la vez; agrúpalas.'})
                continue
            res = run_tool(by_name, call.name, call.arguments, ctx)
            messages.append({'role': 'tool', 'tool_call_id': call.id, 'content': res.text})
            for item in res.understood:
                if item not in turn.understood:
                    turn.understood.append(item)
            if res.table and len(turn.tables) < MAX_TABLES_PER_TURN:
                turn.tables.append(res.table)
            turn.candidates += [c for c in res.candidates if c not in turn.candidates]


def ask(question, history, user, provider=None, clock=time.monotonic):
    """`provider`: solo para tests (se usa con todos los modelos de la lista)."""
    question = question.strip()[:MAX_QUESTION_CHARS]
    turn = Turn(question=question)
    organization = user.organization
    try:
        quota.start_question(organization)
    except quota.QuotaExceeded:
        turn.answer, turn.error = QUOTA_MESSAGE, True
        return turn

    deadline = clock() + settings.ASSISTANT_TIMEOUT
    ctx = ToolContext(user=user, organization=organization, today=timezone.localdate(),
                      remaining=lambda: deadline - clock())
    base_messages = [{'role': 'system', 'content': system_prompt(ctx.today)}, *_history_messages(history),
                     {'role': 'user', 'content': question}]

    models = providers.available_models()
    try:
        for model in models:
            try:
                _run(provider or providers.get_provider(model), base_messages, turn, ctx, deadline, clock)
                break
            except DailyLimit:
                providers.mark_exhausted(model)
                turn = Turn(question=question)  # se repite entera con el siguiente modelo
            except ModelUnavailable:
                providers.mark_exhausted(model, 'no existe (404); ¿nombre mal escrito en ASSISTANT_MODEL?')
                turn = Turn(question=question)
        else:
            if not providers.configured_models():
                logger.error('Asistente: ASSISTANT_MODEL está vacío.')
                turn.answer, turn.error = providers.ProviderError.user_message, True
            else:
                turn.answer, turn.error = DailyLimit.user_message, True
    except quota.QuotaExceeded:
        turn.answer, turn.error = QUOTA_MESSAGE, not turn.tables
    except ProviderError as exc:
        turn.answer, turn.error = exc.user_message, not turn.tables
    except Exception:  # noqa: BLE001 — que un fallo nuestro no deje la página en error 500
        logger.exception('Asistente: fallo inesperado')
        turn.answer, turn.error = 'Ha fallado algo al responder. Inténtalo de nuevo.', not turn.tables

    if not turn.answer:
        turn.answer = 'Aquí tienes lo que he encontrado.' if turn.tables else 'No he sabido responder a eso.'
    return turn
