from django.utils import timezone


class UserTrackingMiddleware:
    """
    Middleware para rastrear la última actividad y dirección IP del usuario.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            ip = x_forwarded_for.split(',')[0] if x_forwarded_for else request.META.get('REMOTE_ADDR')

            # Evitar actualizaciones frecuentes
            last_activity = getattr(request.user, 'last_activity', None)
            if not last_activity or (timezone.now() - last_activity).seconds > 60:
                request.user.last_login_ip = ip
                request.user.update_last_activity()
        return self.get_response(request)
