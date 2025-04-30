from django.utils import timezone
from django.utils.deprecation import MiddlewareMixin


class UserTrackingMiddleware(MiddlewareMixin):
    """
    Middleware para rastrear la última actividad y dirección IP del usuario.
    """

    def process_request(self, request):
        if request.user.is_authenticated:
            # Obtener IP del usuario
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                ip = x_forwarded_for.split(',')[0]
            else:
                ip = request.META.get('REMOTE_ADDR')

            # Actualizar datos del usuario solo si ha pasado cierto tiempo (evita actualizaciones excesivas)
            if not request.user.last_activity or \
                    (timezone.now() - request.user.last_activity).seconds > 60:  # 1 minuto
                request.user.last_login_ip = ip
                request.user.update_last_activity()
        return None
   