import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from assistant import service
from assistant.tests.test_service import FakeProvider, text_reply
from core.models import FeatureFlag

pytestmark = pytest.mark.django_db


@pytest.fixture
def enabled(settings_assistant):
    FeatureFlag.objects.create(name='ASSISTANT', enabled=True)
    return settings_assistant


def test_hidden_without_flag(client, user, settings_assistant):
    client.force_login(user)
    assert client.get(reverse('assistant')).status_code == 404


def test_hidden_without_key(client, user, enabled):
    enabled.ASSISTANT_API_KEY = ''
    client.force_login(user)
    assert client.get(reverse('assistant')).status_code == 404


def test_user_without_organization_forbidden(client, enabled):
    lone = get_user_model().objects.create_user('solo', 's@example.com', 'x')
    client.force_login(lone)
    assert client.get(reverse('assistant')).status_code == 403


def test_empty_page_shows_suggestions_and_quota(client, user, enabled):
    client.force_login(user)
    page = client.get(reverse('assistant')).content.decode()
    assert 'Quedan 5 de 5 hoy' in page
    assert 'Prueba con' in page


def test_post_answers_and_redirects(client, user, enabled, monkeypatch):
    from assistant import providers
    monkeypatch.setattr(providers, 'get_provider', lambda model: FakeProvider(text_reply('Hola <b>Carlos</b>')))
    client.force_login(user)
    response = client.post(reverse('assistant'), {'q': '¿qué tal?'})
    assert response.status_code == 302
    page = client.get(reverse('assistant')).content.decode()
    assert 'Hola &lt;b&gt;Carlos&lt;/b&gt;' in page  # texto del modelo escapado
    assert 'Quedan 4 de 5 hoy' in page
    client.post(reverse('assistant'), {'clear': '1'})
    assert 'Prueba con' in client.get(reverse('assistant')).content.decode()


def test_menu_entry_only_when_available(client, user, enabled):
    client.force_login(user)
    url = reverse('assistant')
    assert url in client.get(reverse('field_list')).content.decode()
    FeatureFlag.objects.filter(name='ASSISTANT').update(enabled=False)
    from django.core.cache import cache
    cache.clear()
    assert f'href="{url}"' not in client.get(reverse('field_list')).content.decode()


def test_post_with_flag_off_is_404(client, user, settings_assistant):
    client.force_login(user)
    assert client.post(reverse('assistant'), {'q': 'hola'}).status_code == 404


def test_anonymous_redirects_to_login(client, enabled):
    assert client.get(reverse('assistant')).status_code == 302


def test_csrf_required(user, enabled):
    from django.test import Client
    strict = Client(enforce_csrf_checks=True)
    strict.force_login(user)
    assert strict.post(reverse('assistant'), {'q': 'hola'}).status_code == 403


def test_table_cells_and_candidates_are_escaped(client, user, enabled):
    session = client.session
    client.force_login(user)
    session = client.session
    session['assistant_turns'] = [{
        'question': 'q', 'answer': 'a', 'understood': ['<i>x</i>'], 'error': False,
        'candidates': ['<script>c</script>'],
        'tables': [{'title': 't', 'columns': ['c'], 'rows': [['<b>parcela</b>']], 'notes': [], 'numeric': []}],
    }]
    session.save()
    page = client.get(reverse('assistant')).content.decode()
    assert '<b>parcela</b>' not in page and '&lt;b&gt;parcela&lt;/b&gt;' in page
    assert '<script>c</script>' not in page and '<i>x</i>' not in page


def test_flag_migration_creates_it_disabled_and_keeps_existing(db):
    import importlib

    from django.apps import apps
    migration = importlib.import_module('assistant.migrations.0002_feature_flag_apagado')
    migration.create_flag(apps, None)
    assert FeatureFlag.objects.get(name='ASSISTANT').enabled is False
    FeatureFlag.objects.filter(name='ASSISTANT').update(enabled=True)
    migration.create_flag(apps, None)
    assert FeatureFlag.objects.get(name='ASSISTANT').enabled is True


def test_sync_command_creates_assistant_disabled(db):
    from django.core.management import call_command
    call_command('sync_feature_flags', stdout=__import__('io').StringIO())
    assert FeatureFlag.objects.get(name='ASSISTANT').enabled is False
    assert FeatureFlag.objects.get(name='WEATHER').enabled is True
