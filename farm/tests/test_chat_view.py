import json
from unittest.mock import patch

import pytest
from django.urls import reverse

from accounts.models import User
from farm.models import ChatMessage
from farm.tests.factories import OrganizationFactory

CHAT_AI = 'farm.views.chat_views.chat_with_ai'


@pytest.fixture
def setup(client):
    org = OrganizationFactory()
    user = User.objects.create_user(username='asistente', password='pass', organization=org)
    client.force_login(user)
    return client, org


def _session_id(client):
    return client.session['chat_session_id']


def _post(client, message):
    return client.post(reverse('chat'), data=json.dumps({'message': message}), content_type='application/json')


@pytest.mark.django_db
class TestChatPage:

    def test_anonymous_is_redirected_to_login(self, client):
        response = client.get(reverse('chat'))
        assert response.status_code == 302
        assert 'login' in response.url

    def test_empty_chat_shows_welcome_and_four_suggestions(self, setup):
        client, _ = setup
        html = client.get(reverse('chat')).content.decode()
        assert 'id="welcomeMsg"' in html
        assert 'id="suggestionsBar"' in html
        assert html.count('class="as-sug"') == 4

    def test_page_keeps_the_ids_the_script_depends_on(self, setup):
        client, _ = setup
        html = client.get(reverse('chat')).content.decode()
        for element_id in ('chatMessages', 'chatInput', 'btnSend', 'typingRow', 'quotaBanner', 'btnClearChat'):
            assert f'id="{element_id}"' in html

    def test_page_has_no_inline_style_block(self, setup):
        client, _ = setup
        html = client.get(reverse('chat')).content.decode()
        chat = html[html.index('card card-flat as-chat'):]  # solo el contenido del chat, no la base
        assert '<style' not in chat
        assert "classList.add('as-page')" in html

    def test_history_is_rendered_and_hides_welcome(self, setup):
        client, org = setup
        client.get(reverse('chat'))
        sid = _session_id(client)
        ChatMessage.objects.create(organization=org, session_id=sid, role='user', content='Hola <b>asistente</b>')
        ChatMessage.objects.create(organization=org, session_id=sid, role='assistant', content='Dosis: **6 L**')
        html = client.get(reverse('chat')).content.decode()
        assert 'as-bubble--user' in html
        assert 'Hola &lt;b&gt;asistente&lt;/b&gt;' in html  # el texto del usuario se escapa
        assert 'data-markdown="Dosis: **6 L**"' in html
        assert 'id="welcomeMsg"' not in html
        assert 'id="suggestionsBar"' not in html

    def test_markdown_attribute_escapes_html_and_quotes(self, setup):
        client, org = setup
        client.get(reverse('chat'))
        payload = '<img src=x onerror=alert(1)> " onmouseover="x'
        ChatMessage.objects.create(organization=org, session_id=_session_id(client), role='assistant', content=payload)
        html = client.get(reverse('chat')).content.decode()
        assert '<img src=x' not in html
        assert 'data-markdown="&lt;img src=x onerror=alert(1)&gt; &quot; onmouseover=&quot;x"' in html

    def test_page_loads_the_safe_markdown_renderer(self, setup):
        client, _ = setup
        html = client.get(reverse('chat')).content.decode()
        assert 'js/chat-markdown.js' in html

    def test_other_organization_and_session_messages_are_not_shown(self, setup):
        client, org = setup
        client.get(reverse('chat'))
        other_org = OrganizationFactory(name='Otra explotación')
        ChatMessage.objects.create(organization=other_org, session_id=_session_id(client), role='user', content='ajeno')
        ChatMessage.objects.create(organization=org, session_id='otra-sesion', role='user', content='otra sesion')
        html = client.get(reverse('chat')).content.decode()
        assert 'ajeno' not in html
        assert 'otra sesion' not in html
        assert 'id="welcomeMsg"' in html


@pytest.mark.django_db
class TestChatApi:

    def test_post_stores_both_messages_and_returns_response(self, setup):
        client, org = setup
        with patch(CHAT_AI, return_value=('Son **6 L**', None)) as ai:
            response = _post(client, '¿Cuánto Brotomax?')
        assert response.status_code == 200
        assert response.json() == {'response': 'Son **6 L**'}
        assert ai.call_count == 1
        roles = list(ChatMessage.objects.filter(organization=org).values_list('role', 'content'))
        assert roles == [('user', '¿Cuánto Brotomax?'), ('assistant', 'Son **6 L**')]

    def test_post_error_is_returned_without_storing_an_answer(self, setup):
        client, org = setup
        with patch(CHAT_AI, return_value=(None, 'Límite diario alcanzado.')):
            response = _post(client, 'hola')
        assert response.status_code == 200
        assert response.json() == {'error': 'Límite diario alcanzado.'}
        assert list(ChatMessage.objects.filter(organization=org).values_list('role', flat=True)) == ['user']

    def test_post_empty_message_is_rejected_without_calling_the_ai(self, setup):
        client, org = setup
        with patch(CHAT_AI) as ai:
            response = _post(client, '   ')
        assert response.status_code == 400
        assert ai.call_count == 0
        assert not ChatMessage.objects.filter(organization=org).exists()

    def test_delete_clears_history_and_starts_a_new_session(self, setup):
        client, org = setup
        with patch(CHAT_AI, return_value=('ok', None)):
            _post(client, 'hola')
        old_sid = _session_id(client)
        response = client.delete(reverse('chat'))
        assert response.json() == {'ok': True}
        assert not ChatMessage.objects.filter(organization=org).exists()
        assert _session_id(client) != old_sid

    def test_delete_does_not_touch_other_organizations(self, setup):
        client, org = setup
        other_org = OrganizationFactory(name='Otra explotación')
        client.get(reverse('chat'))
        ChatMessage.objects.create(organization=org, session_id=_session_id(client), role='user', content='mío')
        ajeno = ChatMessage.objects.create(organization=other_org, session_id=_session_id(client), role='user', content='ajeno')
        client.delete(reverse('chat'))
        assert not ChatMessage.objects.filter(organization=org).exists()
        assert list(ChatMessage.objects.filter(organization=other_org)) == [ajeno]
