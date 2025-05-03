from django.db import models


class OwnershipManager(models.Manager):
    """
    Manager personalizado que filtra automáticamente los objetos
    según el usuario actual.
    """

    def get_queryset_for_user(self, user):
        """
        Devuelve un queryset filtrado por los permisos del usuario.
        """
        queryset = super().get_queryset()

        # Superuser ve todo
        if user.is_superuser:
            return queryset

        # Si el usuario no tiene organización asignada, no ve nada
        if not user.organization:
            return queryset.none()

        # Filtrar por organización del usuario
        return queryset.filter(organization=user.organization)
