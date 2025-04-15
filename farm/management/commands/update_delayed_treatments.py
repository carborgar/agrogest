from django.core.management.base import BaseCommand
from datetime import date, timedelta
from farm.models import Treatment


class Command(BaseCommand):
    help = 'Actualiza el estado de los tratamientos basado en sus fechas'

    def handle(self, *args, **options):
        today = date.today()
        # Procesa tratamientos con fecha en los últimos 3 días (por si se falla algún día)
        window_start = today - timedelta(days=3)
        treatments = Treatment.objects.filter(
            status='pending',
            finish_date__isnull=True,
            date__lte=today - timedelta(days=1),
            date__gte=window_start
        )
        count = treatments.count()
        for t in treatments:
            t.update_status()
            t.save(update_fields=['status'])
        self.stdout.write(f"{count} tratamientos actualizados como atrasadas.")
