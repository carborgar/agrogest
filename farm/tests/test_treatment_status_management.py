import pytest

from farm.tests.factories import *
from farm.tests.mothers import FieldMothers


@pytest.mark.django_db
class TestTreatmentStatusManagement:
    """
    Tests para verificar la gestión de estados de Treatment
    """

    def test_new_treatment_is_pending_when_date_is_future(self):
        # Given: Un tratamiento programado para el futuro
        field = FieldMothers.small_olive_field()
        future_date = date.today() + timedelta(days=5)

        # When: Creamos el tratamiento
        treatment = TreatmentFactory(
            field=field,
            date=future_date,
            finish_date=None,
            organization=field.organization
        )

        # Then: El estado debe ser pendiente
        assert treatment.status == 'pending'
        assert treatment.is_pending()

    def test_treatment_becomes_delayed_when_date_passes(self):
        # Given: Un tratamiento programado para el pasado sin fecha de finalización
        field = FieldMothers.small_olive_field()
        past_date = date.today() - timedelta(days=2)

        # When: Creamos el tratamiento
        treatment = TreatmentFactory(
            field=field,
            date=past_date,
            finish_date=None,
            organization=field.organization
        )

        # Then: El estado debe ser atrasado
        assert treatment.status == 'delayed'
        assert treatment.is_delayed()

    def test_treatment_becomes_completed_when_finish_date_is_set(self):
        # Given: Un tratamiento con fecha de finalización
        field = FieldMothers.small_olive_field()
        past_date = date.today() - timedelta(days=2)
        finish_date = date.today() - timedelta(days=1)

        # When: Creamos el tratamiento con fecha de finalización
        treatment = TreatmentFactory(
            field=field,
            date=past_date,
            finish_date=finish_date,
            organization=field.organization
        )

        # Then: El estado debe ser completado
        assert treatment.status == 'completed'
        assert treatment.is_completed()
