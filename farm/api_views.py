from django.http import JsonResponse

from .models import Field, Machine, Product, Treatment


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
            'type': product.type,
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
        treatment = Treatment.objects.select_related('field', 'machine').prefetch_related('treatmentproduct_set').get(id=treatment_id)
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
