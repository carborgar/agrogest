from datetime import date, timedelta

from django.core.management import call_command

from farm.models import Task, Field


def test_update_delayed_tasks(db):
    field = Field.objects.create(name="Test", area=1, crop="Maíz", planting_year=2022)
    task = Task.objects.create(name="Tarea vieja", type="spraying", date=date.today() - timedelta(days=2), field=field)
    assert task.status == 'pending'

    call_command('update_delayed_tasks')
    task.refresh_from_db()
    assert task.status == 'delayed'
