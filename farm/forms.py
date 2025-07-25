from datetime import date as Datetime
from decimal import Decimal, ROUND_UP

from django import forms
from django.core.exceptions import ValidationError
from django.forms import BaseInlineFormSet
from django.forms import inlineformset_factory

from core.forms import NoPlaceholderModelForm
from .models import Treatment, TreatmentProduct, Expense, Product


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
            'dose': forms.NumberInput(attrs={'step': '0.01'}),
            'total_dose': forms.NumberInput(attrs={'step': '0.01'}),
        }

    def clean_dose(self):
        dose = self.cleaned_data.get('dose')
        if dose is not None:
            # Redondear a 2 decimales, que es la precisión que tiene el modelo
            dose = dose.quantize(Decimal('0.01'), rounding=ROUND_UP)
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
    class Meta:
        model = Expense
        fields = ['field', 'expense_type', 'description', 'payment_date', 'amount']
        widgets = {
            'field': forms.Select(attrs={'class': 'form-select'}),
            'expense_type': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'payment_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Solo establecer fecha inicial para nuevos gastos
        if not self.instance.pk:
            self.fields['payment_date'].initial = Datetime.today().strftime('%Y-%m-%d')
        # Formatear correctamente la fecha para el widget HTML5 date input cuando se edita
        elif self.instance.payment_date:
            self.initial['payment_date'] = self.instance.payment_date.strftime('%Y-%m-%d')


class ProductForm(NoPlaceholderModelForm):
    class Meta:
        model = Product
        fields = [
            'name', 'product_type', 'comments', 'price',
            'spraying_dose', 'spraying_dose_type',
            'fertigation_dose', 'fertigation_dose_type'
        ]
        labels = {
            'name': 'Nombre del producto',
            'product_type': 'Tipo de producto',
            'comments': 'Comentarios y notas',
            'price': 'Precio por unidad (€)',
            'spraying_dose': 'Dosis',
            'spraying_dose_type': 'Tipo de dosis',
            'fertigation_dose': 'Dosis',
            'fertigation_dose_type': 'Tipo de dosis',
        }
        help_texts = {
            'comments': 'Información adicional sobre el producto (opcional)',
            'price': 'Precio por litro o kilogramo según corresponda',
            'spraying_dose': 'Cantidad recomendada para pulverización',
            'fertigation_dose': 'Cantidad recomendada para fertirrigación',
        }
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'product_type': forms.Select(attrs={'class': 'form-select'}),
            'comments': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'spraying_dose': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'spraying_dose_type': forms.Select(attrs={'class': 'form-select'}),
            'fertigation_dose': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'fertigation_dose_type': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Configurar choices para los tipos de dosis
        self.fields['spraying_dose_type'].choices = [('', '---------')] + Product.SPRAYING_DOSE_TYPE_CHOICES
        self.fields['fertigation_dose_type'].choices = [('', '---------')] + Product.FERTIGATION_DOSE_TYPE_CHOICES

        # Hacer campos condicionales opcionales inicialmente
        self.fields['spraying_dose'].required = False
        self.fields['spraying_dose_type'].required = False
        self.fields['fertigation_dose'].required = False
        self.fields['fertigation_dose_type'].required = False

    def clean_spraying_dose(self):
        dose = self.cleaned_data.get('spraying_dose')
        if dose is not None and dose <= 0:
            raise ValidationError('La dosis debe ser mayor que cero.')
        return dose

    def clean_fertigation_dose(self):
        dose = self.cleaned_data.get('fertigation_dose')
        if dose is not None and dose <= 0:
            raise ValidationError('La dosis debe ser mayor que cero.')
        return dose

    def clean_price(self):
        price = self.cleaned_data.get('price')
        if price is not None and price < 0:
            raise ValidationError('El precio no puede ser negativo.')
        return price

    def clean(self):
        cleaned_data = super().clean()

        spraying_dose = cleaned_data.get('spraying_dose')
        spraying_dose_type = cleaned_data.get('spraying_dose_type')
        fertigation_dose = cleaned_data.get('fertigation_dose')
        fertigation_dose_type = cleaned_data.get('fertigation_dose_type')

        # Validar que al menos uno de los métodos esté configurado
        has_spraying = spraying_dose and spraying_dose_type
        has_fertigation = fertigation_dose and fertigation_dose_type

        if not has_spraying and not has_fertigation:
            raise ValidationError(
                'El producto debe tener al menos una configuración válida (pulverización o fertirrigación). '
                'Complete la dosis y el tipo de dosis para al menos uno de los métodos.'
            )

        # Validar pulverización: si tiene dosis, debe tener tipo y viceversa
        if spraying_dose and not spraying_dose_type:
            self.add_error('spraying_dose_type', 'Debe seleccionar el tipo de dosis para pulverización.')
        elif spraying_dose_type and not spraying_dose:
            self.add_error('spraying_dose', 'Debe especificar la dosis para pulverización.')

        # Validar fertirrigación: si tiene dosis, debe tener tipo y viceversa
        if fertigation_dose and not fertigation_dose_type:
            self.add_error('fertigation_dose_type', 'Debe seleccionar el tipo de dosis para fertirrigación.')
        elif fertigation_dose_type and not fertigation_dose:
            self.add_error('fertigation_dose', 'Debe especificar la dosis para fertirrigación.')

        return cleaned_data
