from datetime import date

from django import forms
from django.forms import BaseInlineFormSet
from django.forms import inlineformset_factory

from .models import Task, TaskProduct


class TaskForm(forms.ModelForm):
    water_per_ha = forms.FloatField(
        initial=1000,
        help_text="Litros de agua por hectárea"
    )

    date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        initial=date.today().strftime('%Y-%m-%d')
    )

    class Meta:
        model = Task
        fields = ['name', 'type', 'date', 'field', 'machine', 'water_per_ha']


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
