from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View

from assistant import providers, quota, service

SESSION_KEY = 'assistant_turns'
SHOWN_TURNS = 6  # en pantalla; al modelo solo van los últimos service.HISTORY_TURNS

SUGGESTIONS = (
    ('fa-solid fa-flask', '¿Cuánto va a la máquina de cada producto y cuánto cuesta por ha a 1.500 L/ha?'),
    ('fa-regular fa-clock', '¿Cuándo tratamos por última vez cada parcela?'),
    ('fa-solid fa-chart-column', '¿Cuánto llevamos gastado este año por parcela?'),
    ('fa-solid fa-boxes-packing', '¿Qué tengo que comprar para lo pendiente?'),
)


def assistant_available(request=None):
    """Flag ASSISTANT encendido (sin flag = apagado) y clave configurada."""
    from core.models import is_enabled
    return is_enabled('ASSISTANT', default=False) and providers.is_configured()


class AssistantView(LoginRequiredMixin, View):
    template_name = 'assistant/chat.html'

    def dispatch(self, request, *args, **kwargs):
        if not assistant_available():
            raise Http404('Asistente desactivado.')
        if request.user.is_authenticated and not getattr(request.user, 'organization', None):
            raise PermissionDenied('El asistente necesita una organización.')
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        return render(request, self.template_name, {
            'turns': request.session.get(SESSION_KEY, []),
            'remaining': quota.remaining_questions(),
            'daily': quota.daily_questions(),
            'suggestions': SUGGESTIONS,
            'max_chars': service.MAX_QUESTION_CHARS,
            'nav_assistant': True,
        })

    def post(self, request):
        if 'clear' in request.POST:
            request.session.pop(SESSION_KEY, None)
            return redirect('assistant')
        question = request.POST.get('q', '').strip()
        if question:
            turns = request.session.get(SESSION_KEY, [])
            turn = service.ask(question, turns, request.user)
            request.session[SESSION_KEY] = (turns + [turn.as_dict()])[-SHOWN_TURNS:]
        return redirect(reverse('assistant') + '#pregunta')
