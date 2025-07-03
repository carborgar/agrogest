from datetime import date as Datetime
from decimal import Decimal, ROUND_UP

from django import forms
from django.forms import BaseInlineFormSet
from django.forms import inlineformset_factory

from .models import Treatment, TreatmentProduct, Expense


class TreatmentForm(forms.ModelForm):
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
        model = Treatment
        fields = ['name', 'type', 'date', 'field', 'machine', 'water_per_ha', 'finish_date']

    def clean(self):
        cleaned_data = super().clean()
        treatment_type = cleaned_data.get('type')
        machine = cleaned_data.get('machine')
        water_per_ha = cleaned_data.get('water_per_ha')

        if treatment_type == 'spraying':
            if not machine:
                self.add_error('machine', 'Para tratamientos de pulverización, debe seleccionar una máquina')

            if not water_per_ha:
                self.add_error('water_per_ha', 'Para tratamientos de pulverización, debe indicar el volumen de caldo')

        # Para fertirrigación, asegurar que máquina sea None y water_per_ha sea 0
        if treatment_type == 'fertigation':
            cleaned_data['machine'] = None
            if water_per_ha is None:  # Solo establecer si es None para no sobreescribir valores existentes
                cleaned_data['water_per_ha'] = 0

        return cleaned_data


class TreatmentProductForm(forms.ModelForm):
    class Meta:
        model = TreatmentProduct
        fields = ['product', 'dose', 'total_dose']
        widgets = {
            'dose': forms.NumberInput(attrs={'step': '0.1'}),
            'total_dose': forms.NumberInput(attrs={'step': '0.1'}),
        }

    def clean_dose(self):
        dose = self.cleaned_data.get('dose')
        if dose is not None:
            # Redondear a 1 decimal
            dose = dose.quantize(Decimal('0.1'), rounding=ROUND_UP)
        return dose


class BaseTreatmentProductFormSet(BaseInlineFormSet):
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
            raise forms.ValidationError("Debe agregar al menos un producto al tratamiento.")


TreatmentProductFormSet = inlineformset_factory(
    Treatment,
    TreatmentProduct,
    form=TreatmentProductForm,
    formset=BaseTreatmentProductFormSet,
    can_delete=True,
    min_num=1,
    extra=0,
    validate_min=True
)


class ExpenseForm(forms.ModelForm):
    payment_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        initial=Datetime.today().strftime('%Y-%m-%d')
    )
    
    class Meta:
        model = Expense
        fields = ['field', 'expense_type', 'description', 'payment_date', 'amount']
        widgets = {
            'field': forms.Select(attrs={'class': 'form-select'}),
            'expense_type': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
        }
