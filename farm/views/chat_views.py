import json
import uuid

from django.http import JsonResponse
from django.shortcuts import render
from django.views import View

from farm.ai_service import chat_with_ai
from farm.mixins import OwnershipRequiredMixin
from farm.models import ChatMessage


class ChatView(OwnershipRequiredMixin, View):
    """
    Vista del asistente de IA.

    GET  /asistente/  → página de chat con historial de la sesión actual
    POST /asistente/  → endpoint AJAX; recibe {message} y devuelve {response} o {error}
    DELETE /asistente/ → borra el historial de la sesión actual
    """

    template_name = 'farm/chat.html'
    MAX_HISTORY = 20  # mensajes que se envían al modelo como contexto

    # OwnershipRequiredMixin no llama a get_object() para esta vista → pasamos el test
    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.organization is not None

    def handle_no_permission(self):
        from django.shortcuts import redirect
        if not self.request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(self.request.get_full_path())
        return redirect('field_list')

    # ── helpers ──────────────────────────────────────────────────────────────
    def _get_or_create_session(self, request) -> str:
        if 'chat_session_id' not in request.session:
            request.session['chat_session_id'] = str(uuid.uuid4())
        return request.session['chat_session_id']

    # ── GET ───────────────────────────────────────────────────────────────────
    def get(self, request, *args, **kwargs):
        session_id = self._get_or_create_session(request)
        organization = request.user.organization

        messages = ChatMessage.objects.filter(
            organization=organization,
            session_id=session_id,
        ).order_by('created_at')

        return render(request, self.template_name, {
            'chat_messages': messages,
            'session_id': session_id,
        })

    # ── POST ──────────────────────────────────────────────────────────────────
    def post(self, request, *args, **kwargs):
        # Leer mensaje (JSON o form-data)
        try:
            data = json.loads(request.body)
            user_message = data.get('message', '').strip()
        except (json.JSONDecodeError, AttributeError):
            user_message = request.POST.get('message', '').strip()

        if not user_message:
            return JsonResponse({'error': 'El mensaje no puede estar vacío.'}, status=400)

        organization = request.user.organization
        session_id = self._get_or_create_session(request)

        # Historial reciente para contexto (antes de guardar el nuevo mensaje)
        # Django no soporta índices negativos en querysets: ordenamos desc, cortamos y revertimos
        history = list(
            ChatMessage.objects.filter(
                organization=organization,
                session_id=session_id,
            ).order_by('-created_at')[:self.MAX_HISTORY]
        )[::-1]

        # Guardar mensaje del usuario
        ChatMessage.objects.create(
            organization=organization,
            session_id=session_id,
            role='user',
            content=user_message,
        )

        # Llamada a la IA
        response_text, error = chat_with_ai(organization, user_message, history)

        if error:
            # Devolvemos el error como texto de respuesta del asistente (código 200)
            # para que el frontend lo muestre en el chat sin tratarlo como fallo HTTP
            return JsonResponse({'error': error})

        # Guardar respuesta del asistente
        ChatMessage.objects.create(
            organization=organization,
            session_id=session_id,
            role='assistant',
            content=response_text,
        )

        return JsonResponse({'response': response_text})

    # ── DELETE ────────────────────────────────────────────────────────────────
    def delete(self, request, *args, **kwargs):
        """Borra el historial de la sesión actual y genera un nuevo session_id."""
        session_id = request.session.get('chat_session_id')
        organization = request.user.organization
        if session_id and organization:
            ChatMessage.objects.filter(
                organization=organization,
                session_id=session_id,
            ).delete()
        # Forzar nueva sesión
        request.session['chat_session_id'] = str(uuid.uuid4())
        return JsonResponse({'ok': True})

