from django.utils.deprecation import MiddlewareMixin


class OrganizationMiddleware(MiddlewareMixin):
    """
    Middleware que asegura que los objetos creados durante una solicitud
    pertenecen a la organización del usuario autenticado.
    """

    def process_view(self, request, view_func, view_args, view_kwargs):
        # Solo procesar si el usuario está autenticado y tiene una organización
        if not request.user.is_authenticated:
            return None

        # Añadir la organización del usuario al request para fácil acceso
        if hasattr(request.user, 'organization'):
            request.organization = request.user.organization

        return None


def organization_processor(request):
    """
    Context processor que añade información de la organización a todas las plantillas.
    """
    context = {}

    if request.user.is_authenticated and hasattr(request.user, 'organization'):
        context['user_organization'] = request.user.organization
        context['is_org_admin'] = request.user.is_org_admin

    return context
