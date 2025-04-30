from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect


def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        remember_me = request.POST.get('remember', None)

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)

            # Configurar la duración de la sesión si "recordarme" está activado
            if not remember_me:
                # Sesión expira cuando el usuario cierra el navegador
                request.session.set_expiry(0)
            else:
                # Sesión expira en 30 días (en segundos)
                request.session.set_expiry(60 * 60 * 24 * 30)

            return redirect('accounts:dashboard')
        else:
            messages.error(request, 'Usuario o contraseña incorrectos')

    return render(request, 'accounts/login.html')


@login_required
def dashboard_view(request):
    return render(request, 'accounts/dashboard.html', {'user': request.user})


def logout_view(request):
    logout(request)
    return redirect('accounts:login')
