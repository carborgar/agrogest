"""Bucle del asistente con un proveedor falso: herramientas, vueltas, cupo y errores."""
import json

import pytest

from assistant import quota, service
from assistant.models import AssistantUsage
from assistant.providers import Completion, RateLimited, ToolCall
from farm.tests.factories import FieldFactory

pytestmark = pytest.mark.django_db


class FakeProvider:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def complete(self, messages, tools, timeout, tool_choice='auto'):
        self.calls.append({'messages': messages, 'tool_choice': tool_choice, 'timeout': timeout})
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def tool_reply(name, **args):
    call = ToolCall(id='c1', name=name, arguments=json.dumps(args))
    return Completion(content='', tool_calls=[call], input_tokens=100, output_tokens=10,
                      message={'role': 'assistant', 'content': '', 'tool_calls': [
                          {'id': 'c1', 'type': 'function', 'function': {'name': name, 'arguments': call.arguments}}]})


def text_reply(text):
    return Completion(content=text, input_tokens=120, output_tokens=20, message={'role': 'assistant', 'content': text})


def test_tool_then_answer(user, org, settings_assistant):
    FieldFactory(organization=org, name='Vegueta')
    provider = FakeProvider(tool_reply('historial_tratamientos', parcelas=['vegueta']), text_reply('Nada aún.'))
    turn = service.ask('¿qué hemos hecho en la vegueta?', [], user, provider=provider)
    assert turn.answer == 'Nada aún.'
    assert turn.understood == ['Vegueta']
    assert len(turn.tables) == 1
    assert provider.calls[1]['messages'][-1]['role'] == 'tool'
    usage = AssistantUsage.objects.get(organization=org)
    assert (usage.questions, usage.calls, usage.input_tokens) == (1, 2, 220)


def test_last_round_forces_text(user, settings_assistant):
    provider = FakeProvider(tool_reply('costes'), tool_reply('costes'), text_reply('Listo.'))
    turn = service.ask('gasto', [], user, provider=provider)
    assert [c['tool_choice'] for c in provider.calls] == ['auto', 'auto', 'none']
    assert turn.answer == 'Listo.'


def test_question_quota(user, settings_assistant):
    settings_assistant.ASSISTANT_DAILY_QUESTIONS = 1
    service.ask('una', [], user, provider=FakeProvider(text_reply('ok')))
    assert quota.remaining_questions() == 0
    turn = service.ask('otra', [], user, provider=FakeProvider())
    assert turn.error and 'preguntas de hoy' in turn.answer


def test_call_quota_stops_mid_question(user, settings_assistant):
    settings_assistant.ASSISTANT_DAILY_CALLS = 1
    turn = service.ask('gasto', [], user, provider=FakeProvider(tool_reply('costes')))
    assert 'preguntas de hoy' in turn.answer
    assert turn.tables  # lo ya calculado se enseña


def test_rate_limit_message(user, settings_assistant):
    turn = service.ask('hola', [], user, provider=FakeProvider(RateLimited()))
    assert turn.error and 'límite' in turn.answer


def test_global_deadline(user, settings_assistant):
    ticks = iter([0, 0, 30])
    provider = FakeProvider(tool_reply('costes'))
    turn = service.ask('gasto', [], user, provider=provider, clock=lambda: next(ticks))
    assert len(provider.calls) == 1
    assert 'tiempo' in turn.answer


def test_history_carries_candidates_not_tables(user, settings_assistant):
    history = [{'question': 'la de abajo', 'answer': '¿Cuál?', 'understood': [], 'tables': [{'x': 1}],
                'candidates': ['Huerta de abajo', 'Huerta vieja'], 'error': False}]
    provider = FakeProvider(text_reply('ok'))
    service.ask('la vieja', history, user, provider=provider)
    sent = provider.calls[0]['messages']
    assert 'Huerta vieja' in sent[2]['content']
    assert 'tables' not in json.dumps(sent)


def test_question_is_truncated(user, settings_assistant):
    provider = FakeProvider(text_reply('ok'))
    service.ask('x' * 2000, [], user, provider=provider)
    assert len(provider.calls[0]['messages'][-1]['content']) == service.MAX_QUESTION_CHARS


def test_unexpected_error_does_not_crash(user, settings_assistant):
    turn = service.ask('hola', [], user, provider=FakeProvider(RuntimeError('boom')))
    assert turn.error and 'Ha fallado' in turn.answer


def test_old_session_keys_are_ignored(user, settings_assistant):
    history = [{'question': 'a', 'answer': 'b', 'clave_antigua': 1}, {'raro': True}]
    provider = FakeProvider(text_reply('ok'))
    service.ask('c', history, user, provider=provider)
    assert [m['role'] for m in provider.calls[0]['messages']] == ['system', 'user', 'assistant', 'user']


def test_daily_429_detected():
    import io
    import urllib.error
    from unittest import mock

    from assistant.providers import DailyLimit, OpenAICompatibleProvider
    body = b'{"error":{"details":[{"quotaId":"GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}}'
    err = urllib.error.HTTPError('u', 429, 'Too Many', {}, io.BytesIO(body))
    with mock.patch('urllib.request.urlopen', side_effect=err):
        with pytest.raises(DailyLimit):
            OpenAICompatibleProvider('k', 'https://x', 'm').complete([], [], timeout=5)


def test_too_many_tools_in_one_round(user, settings_assistant):
    calls = [ToolCall(id=f'c{i}', name='costes', arguments='{}') for i in range(8)]
    reply = Completion(content='', tool_calls=calls, message={'role': 'assistant', 'content': None,
                                                              'tool_calls': []})
    provider = FakeProvider(reply, text_reply('ok'))
    turn = service.ask('todo', [], user, provider=provider)
    tool_msgs = [m for m in provider.calls[1]['messages'] if m['role'] == 'tool']
    assert len(tool_msgs) == 8
    assert sum('demasiadas' in m['content'] for m in tool_msgs) == 3
    assert len(turn.tables) == service.MAX_TABLES_PER_TURN
