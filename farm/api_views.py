from django.http import JsonResponse

from .models import Field, Machine, Product


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
