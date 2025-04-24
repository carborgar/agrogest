from decimal import Decimal

from django.db.models import Sum

from .models import Field, Machine, Product, Treatment, TreatmentProduct


def get_fields(request):
    fields = Field.objects.all()
    fields_data = [
        {
            'id': field.id,
            'name': field.name,
            'area': field.area,
            'crop': field.crop
        }
        for field in fields
    ]
    return JsonResponse(fields_data, safe=False)


def get_machines(request):
    machines = Machine.objects.all()
    machines_data = [
        {
            'id': machine.id,
            'name': machine.name,
            'type': machine.type,
            'capacity': machine.capacity
        }
        for machine in machines
    ]
    return JsonResponse(machines_data, safe=False)


def get_products(request, application_type):
    products = Product.objects.all()
    products = [p for p in products if p.supports_application_type(application_type)]

    products_data = [
        {
            'id': product.id,
            'name': product.name,
            'dose': product.get_dose(application_type),
            'dose_type': product.get_dose_type(application_type),
            'dose_type_display': product.get_dose_type_name(application_type),

        }
        for product in products
    ]
    return JsonResponse(products_data, safe=False)


def get_calendar_treatments(request):
    """
    API para obtener tratamientos para el calendario
    """
    # Parámetros de filtro
    start_date = request.GET.get('start', None)
    end_date = request.GET.get('end', None)
    field_ids = request.GET.get('fields', '')
    treatment_types = request.GET.get('types', '')

    # Consulta base
    treatments = Treatment.objects.all()

    # Filtrar por fecha
    if start_date:
        treatments = treatments.filter(date__gte=start_date)
    if end_date:
        treatments = treatments.filter(date__lte=end_date)

    # Filtrar por campos
    if field_ids and field_ids != 'all':
        field_id_list = [int(id) for id in field_ids.split(',') if id.isdigit()]
        if field_id_list:
            treatments = treatments.filter(field_id__in=field_id_list)

    # Filtrar por tipo de tratamiento
    if treatment_types:
        type_list = treatment_types.split(',')
        if type_list:
            treatments = treatments.filter(type__in=type_list)

    # Preparar datos para el calendario
    result = []
    for t in treatments:
        treatment_data = {
            'id': t.id,
            'name': t.name,
            'date': t.finish_date.isoformat() if t.finish_date else t.date.isoformat(),
            'finish_date': t.finish_date.isoformat() if t.finish_date else None,
            'status': t.status,
            'status_display': t.status_display(),
            'type': t.type,
            'water_per_ha': t.water_per_ha,
        }

        result.append(treatment_data)

    return JsonResponse(result, safe=False)


def treatment_detail(request, treatment_id):
    try:
        treatment = Treatment.objects.select_related('field', 'machine').prefetch_related('treatmentproduct_set').get(
            id=treatment_id)
        products = treatment.treatmentproduct_set.all()

        return JsonResponse({
            'id': treatment.id,
            'name': treatment.name,
            'date': treatment.date.isoformat(),
            'finish_date': treatment.finish_date.isoformat() if treatment.finish_date else None,
            'status': treatment.status,
            'status_display': treatment.status_display(),
            'type': treatment.type,
            'type_display': dict(Treatment.TYPE_CHOICES).get(treatment.type, ''),
            'field': treatment.field_id,
            'field_name': treatment.field.name,
            'machine_name': str(treatment.machine) if treatment.machine else None,
            'water_per_ha': treatment.water_per_ha,
            'products': [
                {
                    'id': tp.product.id,
                    'name': tp.product.name,
                    'dose': tp.dose,
                    'dose_type': tp.dose_type,
                    'dose_type_display': dict(tp.product.ALL_DOSE_TYPE_CHOICES).get(tp.dose_type, ''),
                    'total_dose': tp.total_dose,
                    'total_dose_unit': tp.total_dose_unit
                } for tp in products
            ]
        })

    except Treatment.DoesNotExist:
        return JsonResponse({'error': 'Tratamiento no encontrado'}, status=404)


# Añadir a views.py
from django.http import JsonResponse
from django.utils.dateparse import parse_date
from datetime import datetime, timedelta


def field_costs_data(request):
    # Obtener fechas de filtro o usar valores predeterminados (último año)
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=365)

    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')

    if date_from:
        start_date = parse_date(date_from)
    if date_to:
        end_date = parse_date(date_to)

    # Obtener IDs de campos específicos o todos
    field_ids = request.GET.getlist('field_ids')
    fields = Field.objects.all()
    if field_ids:
        fields = fields.filter(id__in=field_ids)

    # Datos de costes por parcela
    field_costs = []
    for field in fields:
        total_cost = field.get_treatments_cost(start_date, end_date)
        cost_per_ha = total_cost / Decimal(field.area) if field.area > 0 else 0

        # Obtener desglose por tipo de producto
        product_types = field.get_cost_by_product_type(start_date, end_date)

        field_costs.append({
            'id': field.id,
            'name': field.name,
            'total_cost': float(total_cost),
            'cost_per_ha': float(cost_per_ha),
            'product_types': list(product_types.values('product__product_type__name', 'total')),
            'area': field.area
        })

    # Costes totales
    total_area = sum(field.area for field in fields)
    total_cost = sum(item['total_cost'] for item in field_costs)

    # Costes por tipo de producto (agregado)
    product_type_costs = TreatmentProduct.objects.filter(
        treatment__field__in=fields,
        treatment__date__gte=start_date,
        treatment__date__lte=end_date
    ).values(
        'product__product_type__name'
    ).annotate(
        total=Sum('total_price')
    ).order_by('-total')

    return JsonResponse({
        'fields': field_costs,
        'total_area': total_area,
        'total_cost': float(total_cost),
        'cost_per_ha': float(total_cost / total_area) if total_area > 0 else 0,
        'product_type_costs': list(product_type_costs)
    })
