from django.core.management.base import BaseCommand
from django.db.models import Q

from farm.models import TreatmentProduct


class Command(BaseCommand):
    help = 'Recalculates doses for all TreatmentProduct records'

    def add_arguments(self, parser):
        parser.add_argument(
            '--treatment-id',
            type=int,
            help='Recalculate doses only for a specific treatment ID',
        )
        parser.add_argument(
            '--product-id',
            type=int,
            help='Recalculate doses only for a specific product ID',
        )
        parser.add_argument(
            '--field-id',
            type=int,
            help='Recalculate doses only for treatments in a specific field',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Perform a dry run without saving changes',
        )

    def handle(self, *args, **options):
        treatment_id = options.get('treatment_id')
        product_id = options.get('product_id')
        field_id = options.get('field_id')
        dry_run = options.get('dry_run', False)

        # Build filter query
        filter_query = Q()

        if treatment_id:
            filter_query &= Q(treatment_id=treatment_id)
            self.stdout.write(f"Filtering by treatment ID: {treatment_id}")

        if product_id:
            filter_query &= Q(product_id=product_id)
            self.stdout.write(f"Filtering by product ID: {product_id}")

        if field_id:
            filter_query &= Q(treatment__field_id=field_id)
            self.stdout.write(f"Filtering by field ID: {field_id}")

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
                # Store old values for comparison and reporting
                old_total_dose = tp.total_dose
                old_dose_type = tp.dose_type
                old_total_dose_unit = tp.total_dose_unit

                # Calculate new dose
                tp.calculate_total_dose()

                # Check if anything changed
                if (old_total_dose != tp.total_dose or
                        old_dose_type != tp.dose_type or
                        old_total_dose_unit != tp.total_dose_unit):

                    if not dry_run:
                        tp.save(update_fields=['dose_type', 'total_dose', 'total_dose_unit'])

                    updated += 1

                    self.stdout.write(
                        f"Updated {tp.product.name} in treatment {tp.treatment.name}:\n"
                        f"  Total dose: {old_total_dose} {old_total_dose_unit} -> {tp.total_dose} {tp.total_dose_unit}\n"
                        f"  Dose type: {old_dose_type} -> {tp.dose_type}\n"
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
