from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from core.mixins import FeatureFlagMixin
from farm.models import Field


class WeatherOverviewView(FeatureFlagMixin, LoginRequiredMixin, TemplateView):
    feature_flag = 'WEATHER'
    template_name = "farm/weather_overview.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Parcelas con contorno de la organización del usuario (antes salían las de todas)
        fields = (
            Field.ownership_objects.get_queryset_for_user(self.request.user)
            .exclude(geometry="").order_by("name")
        )
        context["fields_with_geo"] = list(fields.values("id", "name", "crop", "area"))
        context["nav_weather"] = True
        return context

