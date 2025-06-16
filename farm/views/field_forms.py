import datetime

from django import forms

from core.forms import NoPlaceholderModelForm
from farm.models import Field

current_year = datetime.datetime.now().year
year_choices = [(y, y) for y in range(current_year, current_year - 10, -1)]


class FieldForm(NoPlaceholderModelForm):
    class Meta:
        model = Field
        fields = ['name', 'crop', 'area', 'planting_year', 'location']
        labels = {
            'name': 'Nombre',
            'crop': 'Cultivo',
            'location': 'Ubicación',
            'planting_year': 'Año de siembra',
            'area': 'Superficie (ha)',
        }
        help_texts = {
            'location': '(Opcional) - dirección o referencia geográfica.',
            'area': 'Tamaño del campo en hectáreas. Se usa para cálculos de costos y tratamientos.',
        }
        widgets = {
            'planting_year': forms.Select(choices=year_choices)
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-control'})
