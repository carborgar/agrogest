from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views.generic import TemplateView

from core.decorators import api_login_required
from core.mixins import FeatureFlagMixin
from farm.models import Field
from weather import services


def _user_fields_with_geometry(user):
    """Parcelas con contorno de la organización del usuario."""
    return Field.ownership_objects.get_queryset_for_user(user).exclude(geometry='').order_by('name')


class WeatherOverviewView(FeatureFlagMixin, LoginRequiredMixin, TemplateView):
    feature_flag = 'WEATHER'
    template_name = "weather/overview.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        fields = _user_fields_with_geometry(self.request.user)
        context["fields_with_geo"] = list(fields.values("id", "name", "crop", "area"))
        context["nav_weather"] = True
        return context


@api_login_required
def weather_summary(request):
    """
    Previsión por municipio de las parcelas del usuario (una sola llamada para Inicio y El Tiempo).
    GET /api/weather/summary/ → {"municipalities": [{name, fields, daily}], "errors": [{reason, fields}]}
    """
    from core.models import is_enabled

    if not is_enabled('WEATHER'):
        return JsonResponse({"error": "Módulo desactivado"}, status=404)
    if not getattr(settings, 'AEMET_API_KEY', ''):
        return JsonResponse({"error": "Falta la clave de AEMET en la configuración."}, status=503)
    return JsonResponse(services.get_weather_summary(_user_fields_with_geometry(request.user)))
