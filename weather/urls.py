from django.urls import path

from weather import views

# Nombres sin namespace: los usan las plantillas de farm (Inicio, detalle de parcela, menús).
urlpatterns = [
    path('tiempo/', views.WeatherOverviewView.as_view(), name='weather-overview'),
    path('api/weather/summary/', views.weather_summary, name='api-weather-summary'),
]
