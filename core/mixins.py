from django.http import Http404


class FeatureFlagMixin:
    """
    Mixin que devuelve 404 si el feature flag correspondiente está desactivado.
    Lee el flag de la BD (con caché) para que los cambios sean inmediatos
    sin necesidad de redesplegar.
    Uso: definir `feature_flag = 'WEATHER'` en la vista.
    """
    feature_flag: str = ''

    def dispatch(self, request, *args, **kwargs):
        if self.feature_flag:
            from core.models import is_enabled
            if not is_enabled(self.feature_flag):
                raise Http404(f"Módulo '{self.feature_flag}' desactivado.")
        return super().dispatch(request, *args, **kwargs)
