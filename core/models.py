from django.core.cache import cache
from django.db import models

_CACHE_KEY = 'feature_flags_all'
_CACHE_TTL = 60  # segundos — máximo que tarda en propagarse un cambio


# ── Catálogo de flags soportados ──────────────────────────────────────────────
# Añade aquí cualquier flag nuevo. El comando `sync_feature_flags` creará en BD
# los que no existan (con enabled=True), sin tocar los que ya estén configurados.
KNOWN_FLAGS: dict[str, str] = {
    'WEATHER': 'Módulo del tiempo (AEMET). Desactívalo si la API de AEMAT no responde.',
}


class FeatureFlag(models.Model):
    """
    Feature flag almacenado en base de datos.
    Permite activar/desactivar módulos desde el admin de Django
    sin necesidad de redesplegar la aplicación.

    Caché: los flags se cachean _CACHE_TTL segundos para no golpear
    la BD en cada petición. Al guardar/eliminar un flag la caché se
    invalida inmediatamente.
    """
    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Identificador interno del flag, en MAYÚSCULAS (ej: WEATHER).",
    )
    enabled = models.BooleanField(
        default=True,
        help_text="Desactiva para ocultar el módulo sin borrar el flag.",
    )
    description = models.TextField(
        blank=True,
        help_text="Descripción del módulo que controla este flag.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Feature Flag"
        verbose_name_plural = "Feature Flags"
        ordering = ['name']

    def __str__(self):
        status = "✅" if self.enabled else "❌"
        return f"{status} {self.name}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        cache.delete(_CACHE_KEY)

    def delete(self, *args, **kwargs):
        result = super().delete(*args, **kwargs)
        cache.delete(_CACHE_KEY)
        return result


# ── Helpers públicos ──────────────────────────────────────────────────────────

def get_all_flags() -> dict[str, bool]:
    """Devuelve {NAME: enabled} con caché."""
    flags = cache.get(_CACHE_KEY)
    if flags is None:
        flags = dict(FeatureFlag.objects.values_list('name', 'enabled'))
        cache.set(_CACHE_KEY, flags, _CACHE_TTL)
    return flags


def is_enabled(name: str, default: bool = True) -> bool:
    """Comprueba si un flag está activo. Si no existe en BD devuelve `default`."""
    return get_all_flags().get(name, default)

