from django.core.management.base import BaseCommand
from datetime import date, timedelta
from farm.models import Task


class Command(BaseCommand):
    help = 'Actualiza el estado de las tareas basado en sus fechas'

    def handle(self, *args, **options):
        today = date.today()
        # Procesa tareas con fecha en los últimos 3 días (por si se falla algún día)
        window_start = today - timedelta(days=3)
        tasks = Task.objects.filter(
            status='pending',
            finish_date__isnull=True,
            date__lte=today - timedelta(days=1),
            date__gte=window_start
        )
        count = tasks.count()
        for task in tasks:
            task.update_status()
            task.save(update_fields=['status'])
        self.stdout.write(f"{count} tareas actualizadas como atrasadas.")
