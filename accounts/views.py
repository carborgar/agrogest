from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView
from django.shortcuts import render
from django.urls import reverse_lazy
from django.views.generic import UpdateView

from accounts.forms import NotificationPreferencesForm
from accounts.models import NotificationPreferences


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

    def form_valid(self, form):
        messages.success(self.request, 'Preferencias de notificación actualizadas.')
        return super().form_valid(form)


@login_required
def dashboard_view(request):
    return render(request, 'accounts/dashboard.html', {'user': request.user})
