from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Q

from farm.models import TreatmentProduct


class Command(BaseCommand):
    help = 'Recalculates prices for all TreatmentProduct records based on current product prices'

    def add_arguments(self, parser):
        parser.add_argument(
            '--product-id',
            type=int,
            help='Recalculate prices only for a specific product ID',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Perform a dry run without saving changes',
        )

    def handle(self, *args, **options):
        product_id = options.get('product_id')
        dry_run = options.get('dry_run', False)

        # Build filter query
        filter_query = Q()

        if product_id:
            filter_query &= Q(product_id=product_id)
            self.stdout.write(f"Filtering by product ID: {product_id}")

        # Get treatment products to update
        treatment_products = TreatmentProduct.objects.filter(filter_query)
        count = treatment_products.count()

        if count == 0:
            self.stdout.write(self.style.WARNING('No TreatmentProduct records found matching the criteria'))
            return

        self.stdout.write(f"Found {count} TreatmentProduct records to update")

        # Track statistics
        updated = 0
        errors = 0
        unchanged = 0

        # Process all matching records
        for tp in treatment_products:
            try:
                # Get current product price
                current_price = tp.product.price
                old_unit_price = tp.unit_price
                old_total_price = tp.total_price
                old_price_per_ha = tp.price_per_ha

                # Only update if price has changed
                if old_unit_price != current_price:
                    # Update unit price
                    tp.unit_price = current_price

                    # Recalculate total price
                    tp.total_price = tp.unit_price * tp.total_dose

                    # Recalculate price per hectare
                    tp.price_per_ha = tp.total_price / Decimal(tp.treatment.field.area)

                    if not dry_run:
                        tp.save(update_fields=['unit_price', 'total_price', 'price_per_ha'])

                    updated += 1

                    self.stdout.write(
                        f"Updated {tp.product.name} in treatment {tp.treatment.name}: "
                        f"Unit price: {old_unit_price} -> {tp.unit_price}, "
                        f"Total price: {old_total_price} -> {tp.total_price}, "
                        f"Price per ha: {old_price_per_ha} -> {tp.price_per_ha}"
                    )
                else:
                    unchanged += 1

            except Exception as e:
                errors += 1
                self.stdout.write(
                    self.style.ERROR(f"Error updating treatment product ID {tp.id}: {str(e)}")
                )

        # Print summary
        if dry_run:
            self.stdout.write(self.style.SUCCESS(f"DRY RUN - Would update {updated} records"))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"Finished! Updated: {updated}, Unchanged: {unchanged}, Errors: {errors}"
            ))
