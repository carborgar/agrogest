from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from farm.models import Field


class WeatherOverviewView(LoginRequiredMixin, TemplateView):
    template_name = "farm/weather_overview.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Parcelas con geometría del usuario
        fields = Field.objects.filter(
            geometry__isnull=False
        ).exclude(geometry="").order_by("name")
        context["fields_with_geo"] = list(fields.values("id", "name", "crop", "area"))
        context["nav_weather"] = True
        return context

