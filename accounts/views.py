from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView
from django.shortcuts import render
from django.urls import reverse_lazy
from django.views.generic import ListView, UpdateView

from accounts.forms import NotificationPreferencesForm
from accounts.models import Notification, NotificationPreferences


class CustomLoginView(LoginView):
    template_name = 'accounts/login.html'
    redirect_authenticated_user = True

    def get_success_url(self):
        next_url = self.request.POST.get('next') or self.request.GET.get('next')
        return next_url or reverse_lazy('home')

    def form_valid(self, form):
        remember_me = self.request.POST.get('remember')
        if not remember_me:
            self.request.session.set_expiry(0)
        return super().form_valid(form)


class NotificationPreferencesView(LoginRequiredMixin, UpdateView):
    model = NotificationPreferences
    form_class = NotificationPreferencesForm
    template_name = 'accounts/notification_preferences.html'
    success_url = reverse_lazy('accounts:notification-preferences')

    def get_object(self, queryset=None):
        obj, _ = NotificationPreferences.objects.get_or_create(user=self.request.user)
        return obj

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Pasamos los valores como strings simples para evitar pasar BoundField a includes
        obj = self.object
        context['created_channel'] = obj.treatment_created_channel
        context['finished_channel'] = obj.treatment_finished_channel
        return context

    def form_valid(self, form):
        messages.success(self.request, 'Preferencias de notificación actualizadas.')
        return super().form_valid(form)


class NotificationInboxView(LoginRequiredMixin, ListView):
    template_name = 'accounts/inbox.html'
    context_object_name = 'notifications'

    def get_queryset(self):
        # Nota: NO aplicar slice aquí; se aplica en get() después de filtrar no-leídas
        return Notification.objects.filter(user=self.request.user).order_by('-created_at')

    def get(self, request, *args, **kwargs):
        base_qs = Notification.objects.filter(user=request.user)

        # Capturar IDs no-leídas ANTES de marcarlas (para resaltarlas en la plantilla)
        unread_pks = set(base_qs.filter(read=False).values_list('pk', flat=True))

        # Marcar todas como leídas
        base_qs.filter(read=False).update(read=True)

        # Las 50 más recientes
        notifications = list(base_qs.order_by('-created_at')[:50])
        for n in notifications:
            n.is_new = n.pk in unread_pks

        # Auto-purga: borrar todo lo que quede fuera de las 50 más recientes
        if len(notifications) == 50:
            kept_pks = [n.pk for n in notifications]
            base_qs.exclude(pk__in=kept_pks).delete()

        # MultipleObjectMixin requiere self.object_list antes de llamar get_context_data
        self.object_list = notifications
        context = self.get_context_data()
        return self.render_to_response(context)


@login_required
def dashboard_view(request):
    return render(request, 'accounts/dashboard.html', {'user': request.user})
