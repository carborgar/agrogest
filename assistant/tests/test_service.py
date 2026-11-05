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


class ModelProviders:
    """Un FakeProvider por modelo, para probar el cambio de modelo."""

    def __init__(self, **by_model):
        self.by_model = by_model
        self.used = []

    def __call__(self, model):
        self.used.append(model)
        return self.by_model[model]


@pytest.fixture
def fresh_cache():
    from django.core.cache import cache
    cache.clear()
    yield
    cache.clear()


def test_exhausted_model_restarts_question_with_next(user, org, settings_assistant, monkeypatch, fresh_cache):
    from assistant import providers
    from assistant.providers import DailyLimit
    FieldFactory(organization=org, name='Vegueta')
    factory = ModelProviders(**{
        'modelo-a': FakeProvider(tool_reply('historial_tratamientos', parcelas=['vegueta']), DailyLimit()),
        'modelo-b': FakeProvider(tool_reply('historial_tratamientos', parcelas=['vegueta']), text_reply('Con B.')),
    })
    monkeypatch.setattr(providers, 'get_provider', factory)
    turn = service.ask('¿y la vegueta?', [], user)
    assert turn.answer == 'Con B.'
    assert len(turn.tables) == 1          # la pasada fallida no deja tablas repetidas
    assert providers.available_models() == ['modelo-b']

    # La siguiente pregunta ya no prueba el agotado
    factory.by_model['modelo-b'] = FakeProvider(text_reply('Otra vez B.'))
    factory.used.clear()
    assert service.ask('hola', [], user).answer == 'Otra vez B.'
    assert factory.used == ['modelo-b']


def test_missing_model_is_skipped(user, settings_assistant, monkeypatch, fresh_cache):
    from assistant import providers
    from assistant.providers import ModelUnavailable
    factory = ModelProviders(**{'modelo-a': FakeProvider(ModelUnavailable()),
                                'modelo-b': FakeProvider(text_reply('ok'))})
    monkeypatch.setattr(providers, 'get_provider', factory)
    assert service.ask('hola', [], user).answer == 'ok'


def test_all_models_exhausted(user, settings_assistant, monkeypatch, fresh_cache):
    from assistant import providers
    from assistant.providers import DailyLimit
    factory = ModelProviders(**{'modelo-a': FakeProvider(DailyLimit()), 'modelo-b': FakeProvider(DailyLimit())})
    monkeypatch.setattr(providers, 'get_provider', factory)
    turn = service.ask('hola', [], user)
    assert turn.error and 'cupo gratuito de hoy' in turn.answer
    # Y sin modelos disponibles ni se llama al proveedor
    factory.used.clear()
    assert 'cupo gratuito de hoy' in service.ask('otra', [], user).answer
    assert factory.used == []


def test_per_minute_limit_does_not_switch_model(user, settings_assistant, monkeypatch, fresh_cache):
    from assistant import providers
    factory = ModelProviders(**{'modelo-a': FakeProvider(RateLimited()), 'modelo-b': FakeProvider(text_reply('x'))})
    monkeypatch.setattr(providers, 'get_provider', factory)
    turn = service.ask('hola', [], user)
    assert 'Espera un minuto' in turn.answer
    assert providers.available_models() == ['modelo-a', 'modelo-b']


def test_seconds_until_reset_normal_day():
    from datetime import datetime

    from assistant.providers import QUOTA_RESET_TZ, seconds_until_reset
    from assistant.providers import RESET_MARGIN
    assert seconds_until_reset(datetime(2026, 11, 5, 23, 0, tzinfo=QUOTA_RESET_TZ)) == 3600 + RESET_MARGIN
    assert seconds_until_reset(datetime(2026, 11, 5, 23, 59, 50, tzinfo=QUOTA_RESET_TZ)) == 70


def test_model_list_from_settings(settings):
    from assistant.providers import configured_models
    settings.ASSISTANT_MODEL = ' a , b,, '
    assert configured_models() == ['a', 'b']


def test_404_raises_model_unavailable():
    import io
    import urllib.error
    from unittest import mock

    from assistant.providers import ModelUnavailable, OpenAICompatibleProvider
    err = urllib.error.HTTPError('u', 404, 'Not Found', {}, io.BytesIO(b'{}'))
    with mock.patch('urllib.request.urlopen', side_effect=err):
        with pytest.raises(ModelUnavailable):
            OpenAICompatibleProvider('k', 'https://x', 'm').complete([], [], timeout=5)


def test_reset_is_dst_safe():
    from datetime import datetime

    from assistant.providers import QUOTA_RESET_TZ, RESET_MARGIN, seconds_until_reset
    # 1 nov 2026 en California dura 25 h (cambio de hora)
    assert seconds_until_reset(datetime(2026, 11, 1, 0, 0, tzinfo=QUOTA_RESET_TZ)) == 25 * 3600 + RESET_MARGIN


def test_404_marks_model_for_one_hour_only(settings_assistant, monkeypatch):
    from assistant import providers
    seen = {}
    monkeypatch.setattr(providers.cache, 'set', lambda key, value, ttl: seen.update({key: ttl}))
    providers.mark_exhausted('modelo-a', 'no existe (404)')
    assert seen == {'assistant:exhausted:modelo-a': providers.UNAVAILABLE_TTL}


def test_empty_model_list_is_not_configured(user, settings_assistant, fresh_cache):
    from assistant import providers
    settings_assistant.ASSISTANT_MODEL = ' , '
    assert not providers.is_configured()
    turn = service.ask('hola', [], user, provider=FakeProvider())
    assert turn.error and 'cupo' not in turn.answer


def test_quota_counts_both_passes_once_per_question(user, org, settings_assistant, monkeypatch, fresh_cache):
    from assistant import providers
    from assistant.providers import DailyLimit
    factory = ModelProviders(**{'modelo-a': FakeProvider(tool_reply('costes'), DailyLimit()),
                                'modelo-b': FakeProvider(text_reply('ok'))})
    monkeypatch.setattr(providers, 'get_provider', factory)
    service.ask('gasto', [], user)
    usage = AssistantUsage.objects.get(organization=org)
    assert (usage.questions, usage.calls) == (1, 3)
