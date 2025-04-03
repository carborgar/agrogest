from datetime import date as Datetime

from django import forms
from django.forms import BaseInlineFormSet
from django.forms import inlineformset_factory

from .models import Task, TaskProduct


class TaskForm(forms.ModelForm):
    water_per_ha = forms.FloatField(
        help_text="Litros de agua por hectárea",
        required=False  # We'll handle requirement conditionally
    )

    date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        initial=Datetime.today().strftime('%Y-%m-%d')
    )

    # must be in the past
    finish_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        required=False
    )

    class Meta:
        model = Task
        fields = ['name', 'type', 'date', 'field', 'machine', 'water_per_ha', 'finish_date']

    def clean(self):
        cleaned_data = super().clean()
        task_type = cleaned_data.get('type')
        machine = cleaned_data.get('machine')
        water_per_ha = cleaned_data.get('water_per_ha')

        if task_type == 'spraying':
            if not machine:
                self.add_error('machine', 'Para tratamientos de pulverización, debe seleccionar una máquina')

            if not water_per_ha:
                self.add_error('water_per_ha', 'Para tratamientos de pulverización, debe indicar el volumen de caldo')

        # Para fertirrigación, asegurar que máquina sea None y water_per_ha sea 0
        if task_type == 'fertigation':
            cleaned_data['machine'] = None
            if water_per_ha is None:  # Solo establecer si es None para no sobreescribir valores existentes
                cleaned_data['water_per_ha'] = 0

        return cleaned_data


class TaskProductForm(forms.ModelForm):
    class Meta:
        model = TaskProduct
        fields = ['product', 'dose']


class BaseTaskProductFormSet(BaseInlineFormSet):
    def clean(self):
        """
        Validate that at least one product is being used.
        """
        super().clean()

        valid_forms = 0

        for form in self.forms:
            if form.is_valid() and form.cleaned_data and not form.cleaned_data.get('DELETE', False):
                product = form.cleaned_data.get('product')
                dose = form.cleaned_data.get('dose')

                if product and dose:
                    valid_forms += 1

        if valid_forms < 1:
            raise forms.ValidationError("Debe agregar al menos un producto a la tarea.")


TaskProductFormSet = inlineformset_factory(
    Task,
    TaskProduct,
    form=TaskProductForm,
    formset=BaseTaskProductFormSet,
    can_delete=True,
    min_num=1,
    extra=0,
    validate_min=True
)
