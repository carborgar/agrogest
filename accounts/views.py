from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.shortcuts import render
from django.urls import reverse_lazy


class CustomLoginView(LoginView):
    template_name = 'accounts/login.html'
    redirect_authenticated_user = True

    def get_success_url(self):
        # Obtener el valor 'next' o redirigir a la página principal
        next_url = self.request.POST.get('next') or self.request.GET.get('next')
        return next_url or reverse_lazy('home')  # Cambia 'home' a tu URL principal

    def form_valid(self, form):
        remember_me = self.request.POST.get('remember')

        if not remember_me:
            # La sesión expirará cuando el usuario cierre el navegador
            self.request.session.set_expiry(0)

        # Llamamos al método form_valid padre que maneja el login
        return super().form_valid(form)


@login_required
def dashboard_view(request):
    return render(request, 'accounts/dashboard.html', {'user': request.user})
