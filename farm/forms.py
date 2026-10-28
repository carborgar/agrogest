import datetime
from datetime import date as Datetime
from decimal import Decimal, ROUND_HALF_EVEN, ROUND_UP

from django import forms
from django.core.exceptions import ValidationError
from django.forms import BaseInlineFormSet
from django.forms import inlineformset_factory

from core.forms import NoPlaceholderModelForm
from .timeutils import local_today
from .models import Treatment, TreatmentProduct, Expense, Product, Harvest, ProductType, Field, Machine, StoragePoint


class TreatmentForm(forms.ModelForm):
    water_per_ha = forms.FloatField(
        help_text="Litros de agua por hectárea",
        required=False  # We'll handle requirement conditionally
    )

    date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        initial=lambda: local_today().strftime('%Y-%m-%d')
    )

    # No puede ser futura (se valida en clean)
    finish_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        required=False
    )

    # Mojado realmente usado (L/ha). Solo cuenta en pulverización con fecha de realización.
    real_water_per_ha = forms.IntegerField(
        required=False,
        help_text="Mojado real usado por hectárea (en litros)",
    )

    # Solo al crear: parcelas adicionales (una copia del tratamiento por parcela).
    # `field` sigue siendo la primera parcela.
    extra_fields = forms.ModelMultipleChoiceField(
        queryset=Field.objects.none(),
        required=False,
    )

    class Meta:
        model = Treatment
        fields = ['name', 'type', 'date', 'field', 'machine', 'water_per_ha', 'finish_date',
                  'real_water_per_ha', 'applied_area', 'zone_notes']
        widgets = {
            'applied_area': forms.NumberInput(attrs={'step': '0.01'}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)

        # Parcelas y máquinas solo de la organización del usuario (sin usuario, ninguna).
        if user is not None:
            fields_qs = Field.ownership_objects.get_queryset_for_user(user)
            machines_qs = Machine.ownership_objects.get_queryset_for_user(user)
        else:
            fields_qs = Field.objects.none()
            machines_qs = Machine.objects.none()
        self.fields['field'].queryset = fields_qs
        self.fields['machine'].queryset = machines_qs
        self.fields['extra_fields'].queryset = fields_qs
        if self.instance.pk:
            del self.fields['extra_fields']

        # Only default to today on creation; in edit keep stored model values.
        if not self.instance.pk:
            self.fields['date'].initial = local_today().strftime('%Y-%m-%d')
        elif self.instance.date:
            self.initial['date'] = self.instance.date.strftime('%Y-%m-%d')

        if self.instance.pk and self.instance.finish_date:
            self.initial['finish_date'] = self.instance.finish_date.strftime('%Y-%m-%d')

    def clean_applied_area(self):
        area = self.cleaned_data.get('applied_area')
        if area is not None and area <= 0:
            raise ValidationError('El área parcial tiene que ser mayor que 0')
        return area

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

        if water_per_ha is not None and water_per_ha < 0:
            self.add_error('water_per_ha', 'El mojado tiene que ser mayor que 0')

        # Para fertirrigación, asegurar que máquina sea None y water_per_ha sea 0
        if treatment_type == 'fertigation':
            cleaned_data['machine'] = None
            if water_per_ha is None:  # Solo establecer si es None para no sobreescribir valores existentes
                cleaned_data['water_per_ha'] = 0

        applied_area = cleaned_data.get('applied_area')
        field = cleaned_data.get('field')
        if applied_area and field and applied_area > field.area:
            self.add_error(
                'applied_area',
                f'El área parcial ({applied_area} ha) no puede superar el área de la parcela ({field.area} ha)'
            )

        # La fecha de realización no puede ser futura
        finish_date = cleaned_data.get('finish_date')
        if finish_date and finish_date > local_today():
            self.add_error('finish_date', 'La fecha de realización no puede ser futura')

        # Mojado real: solo en pulverización ya realizada, y mayor que 0.
        # En cualquier otro caso se descarta (el modelo también lo limpia).
        real_water = cleaned_data.get('real_water_per_ha')
        if self.instance.pk and 'real_water_per_ha' not in self.data:
            # Cliente que no envía el campo: conservar el valor guardado
            real_water = cleaned_data['real_water_per_ha'] = self.instance.real_water_per_ha
        if treatment_type == 'spraying' and finish_date:
            if real_water is not None and real_water <= 0:
                self.add_error('real_water_per_ha', 'El mojado real tiene que ser mayor que 0')
        else:
            cleaned_data['real_water_per_ha'] = None

        # Varias parcelas (solo al crear): la parcela principal no se repite y no hay
        # tratamiento parcial (cada parcela se trata entera).
        if 'extra_fields' in self.fields:
            extras = [f for f in (cleaned_data.get('extra_fields') or []) if f != field]
            cleaned_data['extra_fields'] = extras
            if extras:
                if applied_area:
                    self.add_error('applied_area', 'Con varias parcelas no se puede indicar un área parcial')
                if cleaned_data.get('zone_notes'):
                    self.add_error('zone_notes', 'Con varias parcelas no se puede indicar una zona')

        return cleaned_data


def _normalize_dose(value, decimals=3):
    """Dosis como texto sin ceros finales y con `decimals` decimales como máximo.

    Dosis a 3 decimales siempre (tecleada o derivada del total a mano), igual que la versión anterior."""
    if value is None:
        return value
    return f"{value:.{decimals}f}".rstrip('0').rstrip('.')


class TreatmentProductForm(forms.ModelForm):
    # Si es True, el usuario puso el total a mano y la dosis se deriva de él.
    total_overridden = forms.BooleanField(required=False, widget=forms.HiddenInput)

    # Orden de la línea dentro del tratamiento (lo decide el formulario; si no llega, el orden de las filas)
    position = forms.IntegerField(required=False, min_value=0, widget=forms.HiddenInput)

    class Meta:
        model = TreatmentProduct
        fields = ['product', 'dose', 'total_dose', 'total_overridden', 'position']
        widgets = {
            'dose': forms.NumberInput(attrs={'step': '0.001'}),
            'total_dose': forms.NumberInput(attrs={'step': '0.001'}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Solo productos de la organización del usuario (sin usuario, ninguno)
        if user is not None:
            self.fields['product'].queryset = Product.ownership_objects.get_queryset_for_user(user)
        else:
            self.fields['product'].queryset = Product.objects.none()
        # El total solo es obligatorio si viene puesto a mano; si no, el backend lo calcula
        self.fields['total_dose'].required = False
        # Normalizar visualización de dosis para no mostrar ceros finales (ej: 0.075 en vez de 0.0750)
        if self.instance and self.instance.pk:
            if self.instance.dose:
                self.initial['dose'] = _normalize_dose(self.instance.dose)
            if self.instance.total_dose is not None:
                # total_dose se muestra con 2 decimales en el formulario
                self.initial['total_dose'] = f"{self.instance.total_dose:.2f}"

    def validate_unique(self):
        """
        Omitir la validación de unicidad a nivel de formulario individual.
        El formset gestiona la detección de duplicados en clean(), y la
        restricción unique_together del modelo se aplica a nivel de BD.
        Al guardar, las eliminaciones se procesan ANTES que las inserciones,
        por lo que borrar y volver a añadir el mismo producto funciona correctamente.
        """
        pass

    def clean_dose(self):
        dose = self.cleaned_data.get('dose')
        if dose is not None and dose <= 0:
            raise ValidationError('La dosis tiene que ser mayor que 0')
        if dose is not None:
            # Redondear a 3 decimales (ej: 0.075 kg/1000L)
            dose = dose.quantize(Decimal('0.001'), rounding=ROUND_UP)
        return dose

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('total_overridden'):
            total = cleaned_data.get('total_dose')
            if total is not None:
                # Total a mano: 2 decimales (mitad al par, como el modelo y la vista previa)
                total = total.quantize(Decimal('0.01'), rounding=ROUND_HALF_EVEN)
                cleaned_data['total_dose'] = total
            if 'total_dose' not in self.errors and (total is None or total <= 0):
                self.add_error('total_dose', 'El total a mano tiene que ser mayor que 0')
        elif cleaned_data.get('total_dose') is None and 'total_dose' not in self.errors:
            # Sin total a mano el modelo lo recalcula desde la dosis al guardar
            cleaned_data['total_dose'] = Decimal('0')
        return cleaned_data


class BaseTreatmentProductFormSet(BaseInlineFormSet):
    def clean(self):
        """
        Valida que:
        - Al menos un producto esté siendo usado.
        - No haya productos duplicados entre los formularios no eliminados.
        """
        super().clean()

        seen_products = {}
        valid_forms = 0
        flagged = False  # alguna línea marcada con error aquí (no repetir «añade un producto»)

        # El tipo de tratamiento llega en el mismo POST que el formset
        treatment_type = self.data.get('type') if self.is_bound else None
        # Varias parcelas al crear: el total a mano no tiene sentido (cada parcela tiene su área).
        # La vista pasa las parcelas extra YA validadas (sin la principal); si no, se leen del POST
        # descontando la parcela principal.
        extra_ids = getattr(self, 'extra_field_ids', None)
        if extra_ids is None and self.is_bound:
            main = self.data.get('field')
            extra_ids = [v for v in self.data.getlist('extra_fields') if v and v != main]
        multi_field = self.is_bound and self.instance.pk is None and bool(extra_ids)

        for form in self.forms:
            if not form.is_valid() or not form.cleaned_data:
                continue
            if form.cleaned_data.get('DELETE', False):
                continue
            product = form.cleaned_data.get('product')
            dose = form.cleaned_data.get('dose')

            if product and treatment_type in ('spraying', 'fertigation') \
                    and not product.supports_application_type(treatment_type):
                label = 'pulverización' if treatment_type == 'spraying' else 'fertirrigación'
                form.add_error('product', f"'{product.name}' no tiene dosis para {label}")
                flagged = True
                continue

            if multi_field and form.cleaned_data.get('total_overridden'):
                form.add_error('total_dose', 'Con varias parcelas no se puede fijar el total a mano')
                flagged = True
                continue

            if product and dose:
                if product.pk in seen_products:
                    raise forms.ValidationError(
                        f"El producto '{product.name}' está duplicado. "
                        f"Cada producto solo puede aparecer una vez en el tratamiento."
                    )
                seen_products[product.pk] = True
                valid_forms += 1

        if valid_forms < 1 and not flagged:
            raise forms.ValidationError("Debe agregar al menos un producto al tratamiento.")

    def save(self, commit=True):
        """
        Asigna el campo `position` a cada instancia antes de delegar el guardado al padre:
        el orden que indique el formulario (campo `position`) o, si no llega, el orden de las
        filas; siempre renumerado de 0 a n-1 sin huecos. Esto garantiza el orden correcto
        independientemente del ID asignado por la BD (crítico en PostgreSQL con connection
        pooling, donde los IDs no son estrictamente secuenciales).
        """
        active = []
        for index, form in enumerate(self.forms):
            if not getattr(form, 'cleaned_data', None):
                continue
            if form.cleaned_data.get('DELETE', False):
                continue
            if not form.cleaned_data.get('product'):
                continue
            posted = form.cleaned_data.get('position')
            active.append((posted if posted is not None else index, index, form))
        for position, (_, _, form) in enumerate(sorted(active, key=lambda item: (item[0], item[1]))):
            form.instance.position = position
        return super().save(commit=commit)


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
        fields = [
            'field', 'expense_type', 'description', 'payment_date',
            'calculation_mode', 'quantity', 'unit_price', 'price_per_ha', 'amount'
        ]
        widgets = {
            'field': forms.Select(attrs={'class': 'form-select'}),
            'expense_type': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'payment_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'calculation_mode': forms.Select(attrs={'class': 'form-select', 'id': 'id_calculation_mode'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'price_per_ha': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
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

        # Hacer que los campos condicionales no sean obligatorios inicialmente
        self.fields['quantity'].required = False
        self.fields['unit_price'].required = False
        self.fields['price_per_ha'].required = False
        self.fields['amount'].required = False

    def clean(self):
        cleaned_data = super().clean()
        calculation_mode = cleaned_data.get('calculation_mode', 'total')
        quantity = cleaned_data.get('quantity')
        unit_price = cleaned_data.get('unit_price')
        price_per_ha = cleaned_data.get('price_per_ha')
        amount = cleaned_data.get('amount')
        field = cleaned_data.get('field')

        # Validaciones según el modo de cálculo
        if calculation_mode == 'quantity_price':
            if not quantity:
                self.add_error('quantity', 'La cantidad es obligatoria cuando se usa cantidad × precio.')
            if not unit_price:
                self.add_error('unit_price', 'El precio unitario es obligatorio cuando se usa cantidad × precio.')
            if quantity and unit_price:
                # Calcular el amount automáticamente redondeado a 2 decimales
                cleaned_data['amount'] = round(quantity * unit_price, 2)
            # Limpiar campos no utilizados
            cleaned_data['price_per_ha'] = None

        elif calculation_mode == 'price_per_ha':
            if not price_per_ha:
                self.add_error('price_per_ha', 'El precio por hectárea es obligatorio en este modo.')
            if not field:
                self.add_error('field', 'La parcela es obligatoria para calcular por hectárea.')
            if price_per_ha and field:
                from decimal import Decimal

                field_area = Decimal(str(field.area))
                cleaned_data['amount'] = round(price_per_ha * field_area, 2)

                # Guardar el snapshot del área para futura referencia
                cleaned_data['field_area_snapshot'] = field_area
            # Limpiar campos no utilizados
            cleaned_data['quantity'] = None
            cleaned_data['unit_price'] = None

        elif calculation_mode == 'total':
            if not amount:
                self.add_error('amount', 'El importe total es obligatorio en este modo.')
            # Limpiar campos no utilizados
            cleaned_data['quantity'] = None
            cleaned_data['unit_price'] = None
            cleaned_data['price_per_ha'] = None

        return cleaned_data

    def clean_quantity(self):
        quantity = self.cleaned_data.get('quantity')
        if quantity is not None and quantity <= 0:
            raise ValidationError('La cantidad debe ser mayor que cero.')
        return quantity

    def clean_unit_price(self):
        unit_price = self.cleaned_data.get('unit_price')
        if unit_price is not None and unit_price < 0:
            raise ValidationError('El precio unitario no puede ser negativo.')
        return unit_price

    def clean_price_per_ha(self):
        price_per_ha = self.cleaned_data.get('price_per_ha')
        if price_per_ha is not None and price_per_ha < 0:
            raise ValidationError('El precio por hectárea no puede ser negativo.')
        return price_per_ha

    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        if amount is not None and amount < 0:
            raise ValidationError('El importe no puede ser negativo.')
        return amount


class ProductTypeForm(NoPlaceholderModelForm):
    class Meta:
        model = ProductType
        fields = ['name', 'description']
        labels = {
            'name': 'Nombre',
            'description': 'Descripción',
        }
        help_texts = {
            'description': 'Opcional. Breve descripción de los productos que incluye esta categoría.',
        }
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def clean_name(self):
        # Sin distinguir mayúsculas: «Fungicida» y «fungicida» serían el mismo chip de filtro.
        name = (self.cleaned_data.get('name') or '').strip()
        organization_id = self.instance.organization_id
        if organization_id and ProductType.objects.filter(
            organization_id=organization_id, name__iexact=name
        ).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('Ya tienes un tipo con ese nombre.')
        return name


class ProductForm(NoPlaceholderModelForm):
    class Meta:
        model = Product
        fields = [
            'name', 'product_type', 'comments', 'price', 'is_active',
            'spraying_dose', 'spraying_dose_type',
            'fertigation_dose', 'fertigation_dose_type'
        ]
        labels = {
            'name': 'Nombre del producto',
            'product_type': 'Tipo de producto',
            'comments': 'Comentarios y notas',
            'price': 'Precio por unidad (€)',
            'is_active': 'Producto activo',
            'spraying_dose': 'Dosis',
            'spraying_dose_type': 'Tipo de dosis',
            'fertigation_dose': 'Dosis',
            'fertigation_dose_type': 'Tipo de dosis',
        }
        help_texts = {
            'comments': 'Información adicional sobre el producto (opcional)',
            'price': 'Precio por litro o kilogramo según corresponda',
            'is_active': 'Desactívalo para archivarlo sin eliminar el historial de tratamientos',
            'spraying_dose': 'Cantidad recomendada para pulverización',
            'fertigation_dose': 'Cantidad recomendada para fertirrigación',
        }
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'product_type': forms.Select(attrs={'class': 'form-select'}),
            'comments': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input', 'role': 'switch'}),
            'spraying_dose': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.001', 'min': '0'}),
            'spraying_dose_type': forms.Select(attrs={'class': 'form-select'}),
            'fertigation_dose': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.001', 'min': '0'}),
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

        # Normalizar visualización de dosis: quitar ceros finales (ej: 0.075, no 0.0750)
        if self.instance and self.instance.pk:
            if self.instance.spraying_dose:
                self.initial['spraying_dose'] = _normalize_dose(self.instance.spraying_dose)
            if self.instance.fertigation_dose:
                self.initial['fertigation_dose'] = _normalize_dose(self.instance.fertigation_dose)

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



class HarvestForm(NoPlaceholderModelForm):
    class Meta:
        model = Harvest
        # No guardamos área por cosecha: solo kg. El kg/ha se calculará en el resumen por parcela.
        fields = ['field', 'date', 'amount', 'sale_price_per_kg', 'price_pending', 'notes']
        labels = {
            'field': 'Parcela',
            'date': 'Fecha',
            'amount': 'Cantidad (kg)',
            'sale_price_per_kg': 'Precio de venta (€/kg)',
            'price_pending': 'Precio aún no conocido',
            'notes': 'Notas',
        }
        widgets = {
            'field': forms.Select(attrs={'class': 'form-select'}),
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '1', 'min': '0'}),
            'sale_price_per_kg': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'price_pending': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.fields['date'].initial = Datetime.today().strftime('%Y-%m-%d')
        elif self.instance.date:
            self.initial['date'] = self.instance.date.strftime('%Y-%m-%d')

    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        if amount is None or amount < 0:
            raise ValidationError('La cantidad recogida debe ser un número entero positivo')
        return amount

    def clean(self):
        cleaned = super().clean()
        price_pending = cleaned.get('price_pending')
        price = cleaned.get('sale_price_per_kg')

        if price_pending and price:
            # Si el usuario marca pending, ignorar el precio y dejarlo vacío
            cleaned['sale_price_per_kg'] = None

        # Prevent future dates by default (keep consistent with other forms)
        date = cleaned.get('date')
        if date and date > Datetime.today():
            self.add_error('date', 'La fecha de cosecha no puede ser en el futuro')

        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)
        # organization asignada en model.save()
        if commit:
            obj.save()
        return obj


_current_year = datetime.datetime.now().year
_year_choices = [(y, y) for y in range(_current_year, _current_year - 10, -1)]


class FieldForm(NoPlaceholderModelForm):
    class Meta:
        model = Field
        fields = ['name', 'crop', 'area', 'planting_year', 'storage_point', 'geometry']
        labels = {
            'name': 'Nombre',
            'crop': 'Cultivo',
            'planting_year': 'Año de siembra',
            'area': 'Superficie (ha)',
            'storage_point': 'Casetilla de riego',
            'geometry': 'Geometría',
        }
        help_texts = {
            'area': 'Se usa para cálculos de costos y tratamientos.',
            'storage_point': 'Opcional. Si la dejas vacía, la parcela es independiente: el producto se deja en ella.',
        }
        widgets = {
            'planting_year': forms.Select(choices=_year_choices),
            'storage_point': forms.Select(attrs={'class': 'form-select'}),
            'geometry': forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-control'})
        self.fields['geometry'].required = False
        self.fields['area'].widget.attrs['id'] = 'id_area'
        self.fields['storage_point'].required = False
        self.fields['storage_point'].widget.attrs['class'] = 'form-select'

        if user and getattr(user, 'organization', None):
            self.fields['storage_point'].queryset = StoragePoint.objects.filter(
                organization=user.organization
            ).order_by('name')
        else:
            self.fields['storage_point'].queryset = StoragePoint.objects.none()


class StoragePointForm(NoPlaceholderModelForm):
    class Meta:
        model = StoragePoint
        fields = ['name', 'notes']
        labels = {
            'name': 'Nombre',
            'notes': 'Notas',
        }
        help_texts = {
            'name': 'Ej: Injeros, Vegueta, Pitas.',
            'notes': 'Opcional. Referencias útiles para el operario.',
        }
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def clean_name(self):
        # La restricción única (organización, nombre) no la valida Django porque
        # «organization» no está en el formulario: sin esto, un nombre repetido daba un 500.
        # Se compara sin distinguir mayúsculas para evitar «Injeros» e «injeros».
        name = (self.cleaned_data.get('name') or '').strip()
        organization_id = self.instance.organization_id
        if organization_id and StoragePoint.objects.filter(
            organization_id=organization_id, name__iexact=name
        ).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('Ya tienes una casetilla con ese nombre.')
        return name


class TreatmentCostRangeForm(forms.Form):
    start_date = forms.DateField(
        label='Desde',
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
    )
    end_date = forms.DateField(
        label='Hasta',
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
    )

    def clean(self):
        cleaned = super().clean()
        start_date = cleaned.get('start_date')
        end_date = cleaned.get('end_date')
        if start_date and end_date and start_date > end_date:
            raise ValidationError('La fecha de inicio no puede ser posterior a la fecha fin.')
        return cleaned


class TreatmentCostProductForm(forms.Form):
    product = forms.ModelChoiceField(
        queryset=Product.objects.none(),
        label='Producto',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    def __init__(self, *args, **kwargs):
        product_queryset = kwargs.pop('product_queryset', Product.objects.none())
        super().__init__(*args, **kwargs)
        self.fields['product'].queryset = product_queryset




