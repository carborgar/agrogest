from functools import wraps

from django.http import JsonResponse


def api_login_required(view):
    """Como login_required, pero responde 401 en JSON en vez de redirigir al login."""
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'No autenticado'}, status=401)
        return view(request, *args, **kwargs)
    return wrapper
