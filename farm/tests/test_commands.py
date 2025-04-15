from datetime import date, timedelta
from unittest.mock import patch

from django.core.management import call_command

from farm.models import Treatment, Field


def test_update_delayed_treatments(db):
    field = Field.objects.create(name="Test", area=1, crop="Maíz", planting_year=2022)

    # Patch the update_status method to do nothing
    with patch.object(Treatment, 'update_status', lambda self: None):
        treatment = Treatment.objects.create(
            name="Tratamiento antiguo, pendiente",
            type="spraying",
            date=date.today() - timedelta(days=2),
            field=field,
            status='pending'
        )

    assert treatment.status == 'pending'

    call_command('update_delayed_treatments')
    treatment.refresh_from_db()
    assert treatment.status == 'delayed'
