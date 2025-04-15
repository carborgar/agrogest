from farm.models import Task, Product


def create_treatment(field, machine, product_id, type, date, status="pending"):
    """Crea un tratamiento copiando la dosis y el tipo de dosis del producto."""
    product = Product.objects.get(pk=product_id)

    task = Task.objects.create(
        field=field,
        machine=machine,
        type=type,
        date=date,
        status=status,
        product=product,
        dose=product.dose,  # Copia la dosis del producto
        dose_type=product.dose_type
    )

    return task
