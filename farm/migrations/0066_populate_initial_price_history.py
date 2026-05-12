"""
Data migration: crea una entrada inicial en ProductPriceHistory para cada
producto cuyo precio actual sea > 0, usando la fecha de creación del producto
como fecha efectiva (o hoy si created_at es null).
"""
from datetime import date

from django.db import migrations


def populate_price_history(apps, schema_editor):
    Product = apps.get_model('farm', 'Product')
    ProductPriceHistory = apps.get_model('farm', 'ProductPriceHistory')

    entries = []
    for product in Product.objects.filter(price__gt=0).select_related('organization'):
        effective = (
            product.created_at.date()
            if product.created_at
            else date.today()
        )
        entries.append(
            ProductPriceHistory(
                product=product,
                organization=product.organization,
                price=product.price,
                effective_date=effective,
            )
        )

    if entries:
        ProductPriceHistory.objects.bulk_create(entries)


def reverse_populate(apps, schema_editor):
    # On rollback: delete all auto-generated history entries.
    # We identify them as entries where there is no way to distinguish
    # so we just clear all history (safe in dev; in prod use with care).
    ProductPriceHistory = apps.get_model('farm', 'ProductPriceHistory')
    ProductPriceHistory.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('farm', '0065_remove_price_history_supplier_notes'),
    ]

    operations = [
        migrations.RunPython(populate_price_history, reverse_code=reverse_populate),
    ]

