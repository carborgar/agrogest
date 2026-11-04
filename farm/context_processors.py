def feature_flags(request):
    """
    Inyecta los feature flags en el contexto de todos los templates.
    Los lee de la BD (con caché) para que los cambios sean inmediatos
    sin necesidad de redesplegar.
    Cada flag WEATHER → feature_weather, HARVESTS → feature_harvests, etc.
    """
    from farm.navigation import request_flags
    flags = request_flags(request)
    return {f'feature_{k.lower()}': v for k, v in flags.items()}


def sidebar_state(request):
    return {
        'sidebar_collapsed': request.COOKIES.get('sidebar_collapsed', 'false') == 'true'
    }


def ai_configured(request):
    from django.conf import settings
    return {
        'gemini_configured': bool(getattr(settings, 'GEMINI_API_KEY', ''))
    }


def unread_notifications(request):
    if not request.user.is_authenticated:
        return {'unread_notifications_count': 0}
    from accounts.models import Notification
    count = Notification.objects.filter(user=request.user, read=False).count()
    return {'unread_notifications_count': count}

def active_nav(request):
    """
    Inyecta en el contexto un booleano por cada ítem del menú
    (nav_home, nav_treatments…) y el menú ya montado. Todo sale de farm/navigation.py.
    """
    from farm.navigation import active_flags, build_navigation
    ctx = active_flags(request)
    if not request.user.is_authenticated:
        return ctx
    ctx.update(build_navigation(request, ctx))
    return ctx
