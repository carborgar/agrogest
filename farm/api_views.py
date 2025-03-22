from django.http import JsonResponse

from .models import Field, Machine, Product, Task


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


def get_products(request):
    products = Product.objects.all()
    products_data = [
        {
            'id': product.id,
            'name': product.name,
            'type': product.type,
            'dose': product.dose,
            'dose_type': product.dose_type,
            'dose_type_display': product.dose_type_name(),

        }
        for product in products
    ]
    return JsonResponse(products_data, safe=False)


def get_calendar_tasks(request):
    """
    API para obtener tareas para el calendario
    """
    # Parámetros de filtro
    start_date = request.GET.get('start', None)
    end_date = request.GET.get('end', None)
    field_ids = request.GET.get('fields', '')
    task_types = request.GET.get('types', '')

    # Consulta base
    tasks = Task.objects.all()

    # Filtrar por fecha
    if start_date:
        tasks = tasks.filter(date__gte=start_date)
    if end_date:
        tasks = tasks.filter(date__lte=end_date)

    # Filtrar por campos
    if field_ids and field_ids != 'all':
        field_id_list = [int(id) for id in field_ids.split(',') if id.isdigit()]
        if field_id_list:
            tasks = tasks.filter(field_id__in=field_id_list)

    # Filtrar por tipo de tarea
    if task_types:
        type_list = task_types.split(',')
        if type_list:
            tasks = tasks.filter(type__in=type_list)

    # Preparar datos para el calendario
    result = []
    for task in tasks:
        task_data = {
            'id': task.id,
            'name': task.name,
            'date': task.date.isoformat(),
            'finish_date': task.finish_date.isoformat() if task.finish_date else None,
            'status': task.status(),
            'status_display': task.status_display(),
            'type': task.type,
            'type_display': dict(Task.TYPE_CHOICES).get(task.type, ''),
            'field': task.field_id,
            'field_name': task.field.name,
            'machine_name': str(task.machine) if task.machine else None,
            'water_per_ha': task.water_per_ha,
        }

        # Agregar productos
        products = []
        for tp in task.taskproduct_set.all():
            products.append({
                'id': tp.product.id,
                'name': tp.product.name,
                'dose': tp.dose,
                'dose_type': tp.dose_type,
                'dose_type_display': dict(tp.product.DOSE_TYPE_CHOICES).get(tp.dose_type, ''),
                'total_dose': tp.total_dose,
                'total_dose_unit': tp.total_dose_unit
            })
        task_data['products'] = products

        result.append(task_data)

    return JsonResponse(result, safe=False)
