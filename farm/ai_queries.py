from datetime import datetime, timedelta
from django.db.models import Q, Sum
from .models import Field, Product, Treatment, TreatmentProduct, ProductType, ExpenseType
from decimal import Decimal
import json


class FlowStep:
    """Clase base para representar un paso del flujo"""

    def __init__(self, processor):
        self.processor = processor
        self.user = processor.user

    def execute(self, context):
        """Ejecuta el paso y devuelve la respuesta"""
        raise NotImplementedError


class MenuStep(FlowStep):
    def execute(self, context):
        return {
            'type': 'menu',
            'title': '🌾 ¿Qué quieres consultar?',
            'message': 'Selecciona una opción para comenzar:',
            'options': [
                {'id': 'dosis', 'text': '💊 Calcular dosis de productos',
                 'description': 'Calcula cuánto producto necesitas'},
                {'id': 'precio', 'text': '💰 Consultar precios', 'description': 'Ve los precios de productos'},
                {'id': 'tratamiento', 'text': '🚜 Historial de tratamientos',
                 'description': 'Consulta tratamientos anteriores'},
                {'id': 'coste', 'text': '📊 Costes por parcela', 'description': 'Analiza gastos por parcela'},
            ]
        }


class ProductSelectionStep(FlowStep):
    def execute(self, context):
        # Filtrar productos según el contexto si es necesario
        application_filter = context.get('application_filter')

        queryset = Product.ownership_objects.get_queryset_for_user(self.user).order_by('name')

        if application_filter == 'spraying':
            products = [p for p in queryset if p.supports_spraying]
        elif application_filter == 'fertigation':
            products = [p for p in queryset if p.supports_fertigation]
        else:
            products = list(queryset)

        if not products:
            return {
                'type': 'error',
                'message': 'No tienes productos configurados. Añade productos primero.',
                'show_menu': True
            }

        return {
            'type': 'product_selection',
            'title': '💊 Seleccionar producto',
            'message': 'Elige el producto para el que quieres calcular la dosis:',
            'products': [self._format_product(p) for p in products],
            'searchable': len(products) > 5  # Mostrar buscador si hay más de 5 productos
        }

    def _format_product(self, product):
        # Solo mostrar los tipos de aplicación que realmente soporta
        applications = []
        if product.supports_spraying:
            applications.append('Pulverización')
        if product.supports_fertigation:
            applications.append('Fertirrigación')

        return {
            'id': product.id,
            'name': product.name,
            'type': product.product_type.name,
            'applications': applications,  # En lugar de supports_spraying/fertigation
            'price': float(product.price) if product.price else 0
        }


class DoseOptionsStep(FlowStep):
    def execute(self, context):
        product_id = context.get('product_id')

        try:
            product = Product.ownership_objects.get_queryset_for_user(self.user).get(id=product_id)
        except Product.DoesNotExist:
            return {'type': 'error', 'message': 'Producto no encontrado', 'show_menu': True}

        dose_info = self._get_dose_info(product)

        return {
            'type': 'dose_options',
            'title': f'💊 Dosis de {product.name}',
            'product': {
                'name': product.name,
                'type': product.product_type.name,
                'price': float(product.price) if product.price else 0
            },
            'dose_info': dose_info,
            'options': [
                {'id': 'hectares', 'text': '📏 Calcular para X hectáreas',
                 'description': 'Especifica el número de hectáreas'},
                {'id': 'field', 'text': '🏞️ Calcular para una parcela',
                 'description': 'Selecciona una parcela específica'},
                {'id': 'machine', 'text': '🚜 Calcular para una máquina',
                 'description': 'Calcula para una carga de máquina'},
            ]
        }

    def _get_dose_info(self, product):
        dose_info = []
        if product.supports_spraying:
            dose_info.append({
                'type': 'spraying',
                'label': 'Pulverización',
                'dose': float(product.spraying_dose),
                'dose_type': product.spraying_dose_type,
                'dose_display': product.get_dose_type_name('spraying')
            })

        if product.supports_fertigation:
            dose_info.append({
                'type': 'fertigation',
                'label': 'Fertirrigación',
                'dose': float(product.fertigation_dose),
                'dose_type': product.fertigation_dose_type,
                'dose_display': product.get_dose_type_name('fertigation')
            })

        return dose_info


class FieldSelectionStep(FlowStep):
    def execute(self, context):
        fields = Field.ownership_objects.get_queryset_for_user(self.user).order_by('name')

        return {
            'type': 'field_selection',
            'title': context.get('title', '🏞️ Seleccionar parcela'),
            'message': context.get('message', 'Elige la parcela:'),
            'fields': [
                {
                    'id': f.id,
                    'name': f.name,
                    'area': float(f.area),
                    'crop': f.crop,
                    'location': f.location
                }
                for f in fields
            ],
            'searchable': fields.count() > 5
        }


class NumberInputStep(FlowStep):
    def execute(self, context):
        return {
            'type': 'number_input',
            'title': context.get('title', 'Introducir valor'),
            'message': context.get('message', 'Introduce el valor:'),
            'input_type': 'number',
            'placeholder': context.get('placeholder', 'Ej: 5.5'),
            'min': context.get('min', 0.1),
            'step': context.get('step', 0.1)
        }


class DoseCalculator:
    """Calculadora de dosis separada de la lógica de flujo"""

    @staticmethod
    def calculate_for_hectares(product, hectares):
        results = []

        if product.supports_spraying:
            dose = product.spraying_dose
            dose_type = product.spraying_dose_type

            if dose_type in ['l_per_ha', 'kg_per_ha']:
                total = dose * hectares
                unit = 'L' if 'l_' in dose_type else 'kg'
                results.append({
                    'type': 'Pulverización',
                    'calculation': f"{dose} {product.get_dose_type_name('spraying')} × {hectares} ha",
                    'result': f"{total} {unit}",
                    'cost': float(product.price * total) if product.price else 0
                })

        if product.supports_fertigation:
            dose = product.fertigation_dose
            dose_type = product.fertigation_dose_type

            if dose_type in ['l_per_ha', 'kg_per_ha']:
                total = dose * hectares
                unit = 'L' if 'l_' in dose_type else 'kg'
                results.append({
                    'type': 'Fertirrigación',
                    'calculation': f"{dose} {product.get_dose_type_name('fertigation')} × {hectares} ha",
                    'result': f"{total} {unit}",
                    'cost': float(product.price * total) if product.price else 0
                })

        return results

    @staticmethod
    def calculate_for_machine(product, capacity):
        results = []

        if product.supports_spraying:
            dose = product.spraying_dose
            dose_type = product.spraying_dose_type

            if dose_type in ['l_per_1000l', 'kg_per_1000l']:
                total = (dose * capacity) / 1000
                unit = 'L' if 'l_' in dose_type else 'kg'
                results.append({
                    'type': 'Pulverización',
                    'calculation': f"{dose} {product.get_dose_type_name('spraying')} × {capacity}L ÷ 1000",
                    'result': f"{total} {unit}",
                    'cost': float(product.price * total) if product.price else 0
                })

            elif dose_type == 'pct':
                total = (dose * capacity) / 100
                results.append({
                    'type': 'Pulverización',
                    'calculation': f"{dose}% × {capacity}L ÷ 100",
                    'result': f"{total} L",
                    'cost': float(product.price * total) if product.price else 0
                })

        return results


class FlowRouter:
    """Router que gestiona los diferentes flujos"""

    def __init__(self, user):
        self.user = user
        self.steps = {
            'menu': MenuStep(self),
            'product_selection': ProductSelectionStep(self),
            'dose_options': DoseOptionsStep(self),
            'field_selection': FieldSelectionStep(self),
            'number_input': NumberInputStep(self),
        }

    def route(self, flow, step, context):
        """Enruta la petición al paso apropiado"""

        if flow == 'menu' or not flow:
            return self.steps['menu'].execute(context)

        elif flow == 'dosis':
            return self._handle_dose_flow(step, context)

        elif flow == 'precio':
            return self._handle_price_flow(step, context)

        elif flow == 'tratamiento':
            return self._handle_treatment_flow(step, context)

        elif flow == 'coste':
            return self._handle_cost_flow(step, context)

        return {'type': 'error', 'message': 'Flujo no reconocido', 'show_menu': True}

    def _handle_dose_flow(self, step, context):
        if step == 1:
            return self.steps['product_selection'].execute(context)

        elif step == 2:
            context['product_id'] = context.get('selection')
            return self.steps['dose_options'].execute(context)

        elif step == 3:
            calc_type = context.get('selection')
            context['calc_type'] = calc_type

            if calc_type == 'hectares':
                context.update({
                    'title': '📏 Número de hectáreas',
                    'message': 'Introduce el número de hectáreas:',
                    'placeholder': 'Ej: 5.5',
                    'min': 0.1,
                    'step': 0.1
                })
                return self.steps['number_input'].execute(context)

            elif calc_type == 'field':
                context.update({
                    'title': '🏞️ Seleccionar parcela',
                    'message': 'Elige la parcela:'
                })
                return self.steps['field_selection'].execute(context)

            elif calc_type == 'machine':
                context.update({
                    'title': '🚜 Capacidad de máquina',
                    'message': 'Introduce la capacidad de la máquina en litros:',
                    'placeholder': 'Ej: 2000',
                    'min': 100,
                    'step': 100
                })
                return self.steps['number_input'].execute(context)

        elif step == 4:
            return self._calculate_final_result(context)

        return {'type': 'error', 'message': 'Paso no válido', 'show_menu': True}

    def _calculate_final_result(self, context):
        product_id = context.get('product_id')
        calc_type = context.get('calc_type')
        selection = context.get('selection')

        try:
            product = Product.ownership_objects.get_queryset_for_user(self.user).get(id=product_id)
        except Product.DoesNotExist:
            return {'type': 'error', 'message': 'Producto no encontrado', 'show_menu': True}

        if calc_type == 'hectares':
            hectares = float(selection)
            results = DoseCalculator.calculate_for_hectares(product, hectares)
            area_info = f"{hectares} ha"

        elif calc_type == 'field':
            try:
                field = Field.ownership_objects.get_queryset_for_user(self.user).get(id=selection)
                results = DoseCalculator.calculate_for_hectares(product, field.area)
                area_info = f"{field.name} ({field.area} ha)"
            except Field.DoesNotExist:
                return {'type': 'error', 'message': 'Parcela no encontrada', 'show_menu': True}

        elif calc_type == 'machine':
            capacity = int(selection)
            results = DoseCalculator.calculate_for_machine(product, capacity)
            area_info = f"Máquina {capacity}L"

        else:
            return {'type': 'error', 'message': 'Tipo de cálculo no válido', 'show_menu': True}

        return {
            'type': 'dose_result',
            'title': f'💊 Resultado para {product.name}',
            'product': product.name,
            'area_info': area_info,
            'results': results,
            'show_menu': True,
            'show_new_calculation': True
        }

    def _handle_price_flow(self, step, context):
        if step == 1:
            products = Product.ownership_objects.get_queryset_for_user(self.user).filter(
                price__gt=0
            ).order_by('product_type__name', 'name')

            if not products.exists():
                return {
                    'type': 'error',
                    'message': 'No hay productos con precios configurados.',
                    'show_menu': True
                }

            # Agrupar por tipo
            by_type = {}
            for product in products:
                type_name = product.product_type.name
                if type_name not in by_type:
                    by_type[type_name] = []
                by_type[type_name].append({
                    'id': product.id,
                    'name': product.name,
                    'price': float(product.price)
                })

            return {
                'type': 'price_list',
                'title': '💰 Precios de productos',
                'products_by_type': by_type,
                'show_menu': True
            }

        return {'type': 'error', 'message': 'Paso no válido', 'show_menu': True}

    def _handle_treatment_flow(self, step, context):
        if step == 1:
            context.update({
                'title': '🚜 Seleccionar parcela',
                'message': 'Elige la parcela para ver su historial:'
            })
            return self.steps['field_selection'].execute(context)

        elif step == 2:
            field_id = context.get('selection')

            try:
                field = Field.ownership_objects.get_queryset_for_user(self.user).get(id=field_id)
            except Field.DoesNotExist:
                return {'type': 'error', 'message': 'Parcela no encontrada', 'show_menu': True}

            treatments = Treatment.ownership_objects.get_queryset_for_user(self.user).filter(
                field=field
            ).order_by('-date')[:10]

            treatment_list = []
            for treatment in treatments:
                products = treatment.products.all()
                treatment_list.append({
                    'id': treatment.id,
                    'name': treatment.name,
                    'date': treatment.date.strftime('%d/%m/%Y'),
                    'type': treatment.get_type_display(),
                    'status': treatment.status_display(),
                    'products': [p.name for p in products]
                })

            return {
                'type': 'treatment_history',
                'title': f'🚜 Historial de {field.name}',
                'field': field.name,
                'treatments': treatment_list,
                'show_menu': True
            }

        return {'type': 'error', 'message': 'Paso no válido', 'show_menu': True}

    def _handle_cost_flow(self, step, context):
        if step == 1:
            context.update({
                'title': '📊 Seleccionar parcela',
                'message': 'Elige la parcela para ver sus costes:'
            })
            return self.steps['field_selection'].execute(context)

        elif step == 2:
            field_id = context.get('selection')

            try:
                field = Field.ownership_objects.get_queryset_for_user(self.user).get(id=field_id)
            except Field.DoesNotExist:
                return {'type': 'error', 'message': 'Parcela no encontrada', 'show_menu': True}

            total_cost = field.get_treatments_cost()
            cost_by_type = list(field.get_cost_by_product_type())
            cost_per_ha = total_cost / field.area if field.area > 0 else 0

            return {
                'type': 'cost_analysis',
                'title': f'📊 Costes de {field.name}',
                'field': {
                    'name': field.name,
                    'area': float(field.area),
                    'crop': field.crop
                },
                'total_cost': float(total_cost),
                'cost_per_ha': float(cost_per_ha),
                'cost_by_type': [
                    {
                        'type': item['product__product_type__name'],
                        'cost': float(item['total'])
                    }
                    for item in cost_by_type
                ],
                'show_menu': True
            }

        return {'type': 'error', 'message': 'Paso no válido', 'show_menu': True}


class FarmFlowProcessor:
    """Procesador principal simplificado"""

    def __init__(self, user):
        self.user = user
        self.router = FlowRouter(user)

    def process_step(self, step_data):
        """Procesa un paso del flujo"""
        flow = step_data.get('flow', 'menu')
        step = step_data.get('step', 1)

        # Construir contexto unificado
        context = {
            'selection': step_data.get('selection'),
            'flow': flow,
            'step': step
        }

        # Añadir datos de pasos anteriores
        if 'data' in step_data and step_data['data']:
            context.update(step_data['data'])

        return self.router.route(flow, step, context)
