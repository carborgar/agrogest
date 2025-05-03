from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.views import redirect_to_login
from django.shortcuts import redirect

from accounts.models import AuditLog


class OwnershipRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """
    Mixin que verifica si el usuario es el propietario del objeto o
    pertenece a la misma organización o es superadmin.
    """

    def test_func(self):
        """Verifica si el usuario tiene permiso para acceder al objeto."""
        # Superuser siempre tiene acceso
        if self.request.user.is_superuser:
            return True

        # Obtener el objeto si estamos en detalle/edición/eliminación
        if hasattr(self, 'get_object'):
            obj = self.get_object()

            if not obj:
                return True # creación

            # Verificar si el usuario es propietario
            if hasattr(obj, 'owner') and obj.owner == self.request.user:
                return True

            # Verificar si el usuario pertenece a la misma organización que el objeto
            if (hasattr(obj, 'organization') and obj.organization is not None
                    and self.request.user.organization == obj.organization):
                return True

            return False

        # Si estamos en listado, la verificación se hará en get_queryset
        return True

    def handle_no_permission(self):
        # Si el usuario no está autenticado, usar redirect_to_login que preserva el 'next'
        if not self.request.user.is_authenticated:
            return redirect_to_login(
                self.request.get_full_path(),
                self.get_login_url(),
                self.get_redirect_field_name()
            )

        return redirect('home')


class QuerysetFilterMixin:
    """
    Mixin que filtra automáticamente los querysets según la organización del usuario
    """

    def get_queryset(self):
        return self.model.ownership_objects.get_queryset_for_user(self.request.user)


class AuditableMixin:
    """
    Mixin para registrar la creación/actualización de objetos.
    """

    def form_valid(self, form):
        obj = form.save(commit=False)

        # Registrar usuario en creación
        if not obj.pk:
            if hasattr(obj, 'created_by'):
                obj.created_by = self.request.user
            if hasattr(obj, 'owner') and obj.owner is None:
                obj.owner = self.request.user
            if hasattr(obj, 'organization') and obj.organization is None:
                obj.organization = self.request.user.organization

        # Registrar usuario en actualización
        if hasattr(obj, 'updated_by'):
            obj.updated_by = self.request.user

        # Guardar objeto
        obj.save()
        form.save_m2m()

        # Determinar si es creación o actualización
        action = 'create' if not hasattr(self, 'object') else 'update'

        # Obtener IP
        x_forwarded_for = self.request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = self.request.META.get('REMOTE_ADDR')

        # Crear registro de auditoría
        AuditLog.objects.create(
            user=self.request.user,
            action=action,
            model_name=obj._meta.model_name,
            object_id=obj.pk,
            object_repr=str(obj),
            ip_address=ip
        )

        return super().form_valid(form)
