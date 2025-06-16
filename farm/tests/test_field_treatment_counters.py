import pytest

from farm.tests.factories import *
from farm.tests.mothers import FieldMothers


@pytest.mark.django_db
class TestFieldTreatmentCounters:
    """
    Tests para verificar los contadores de tratamientos en Field.
    Usamos factories para crear escenarios específicos de estado.
    """

    def test_field_counts_treatments_by_status(self):
        # Given: Un campo con tratamientos en diferentes estados
        field = FieldMothers.small_olive_field()

        # Tratamiento pendiente (futuro)
        TreatmentFactory(
            field=field,
            date=date.today() + timedelta(days=5),
            finish_date=None,
            organization=field.organization
        )

        # Tratamiento atrasado (pasado, sin finalizar)
        TreatmentFactory(
            field=field,
            date=date.today() - timedelta(days=5),
            finish_date=None,
            organization=field.organization
        )

        # Tratamiento completado (con fecha de finalización)
        TreatmentFactory(
            field=field,
            date=date.today() - timedelta(days=3),
            finish_date=date.today() - timedelta(days=1),
            organization=field.organization
        )

        # When & Then: Los contadores deben ser correctos
        assert field.pending_treatments_count() == 1
        assert field.delayed_treatments_count() == 1
        assert field.completed_treatments_count() == 1

    def test_field_can_be_deleted_when_no_treatments(self):
        # Given: Un campo sin tratamientos
        field = FieldMothers.small_olive_field()

        # When & Then: Debe poder eliminarse
        assert field.can_be_deleted() is True

        # When: Agregamos un tratamiento
        TreatmentFactory(
            field=field,
            organization=field.organization
        )

        # Then: Ya no debe poder eliminarse
        assert field.can_be_deleted() is False
