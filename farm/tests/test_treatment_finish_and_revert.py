"""
Tests TDD para los bugs de finalización y reversión de tratamientos:

Bug 1: Al editar un tratamiento completado y borrar finish_date, el real_water_per_ha
       se queda guardado aunque el tratamiento pase a 'pending'.

Bug 2: Al finalizar de nuevo un tratamiento (que antes fue revertido a pending),
       los costes no se actualizan porque real_water_per_ha seguía guardado del
       ciclo anterior, haciendo que needs_recalculation=False en Treatment.save().
"""
import pytest
from datetime import date, timedelta
from decimal import Decimal

from farm.tests.factories import *
from farm.tests.mothers import FieldMothers, TreatmentMothers, ProductMothers


@pytest.mark.django_db
class TestClearingFinishDateResetsRealWater:
    """
    Bug 1: Cuando se borra finish_date, real_water_per_ha debe limpiarse también.
    """

    def test_clearing_finish_date_clears_real_water_per_ha(self):
        """
        FALLA ESPERADA (Bug 1): Al borrar finish_date, real_water_per_ha debe quedar en None.
        """
        field = FieldMothers.cost_analysis_field()
        treatment = TreatmentMothers.pending_treatment_with_changeable_water(field)

        # Finalizamos el tratamiento con agua real
        treatment.finish_treatment(finish_date=date.today(), real_water_per_ha=600)
        treatment.refresh_from_db()

        assert treatment.status == 'completed'
        assert treatment.real_water_per_ha == 600

        # Ahora editamos: borramos finish_date (como hace el formulario de edición)
        treatment.finish_date = None
        treatment.save()
        treatment.refresh_from_db()

        # El status debe ser pending o delayed (no completed)
        assert treatment.status != 'completed'
        # CRÍTICO (Bug 1): real_water_per_ha debe haberse limpiado
        assert treatment.real_water_per_ha is None, (
            f"Bug 1: real_water_per_ha debería ser None tras borrar finish_date, "
            f"pero es {treatment.real_water_per_ha}"
        )

    def test_clearing_finish_date_recalculates_costs_to_planned_water(self):
        """
        FALLA ESPERADA (Bug 1 side-effect): Al borrar finish_date, los costes
        deben recalcularse usando water_per_ha (planificado), no real_water_per_ha.
        """
        field = FieldMothers.cost_analysis_field()  # 6 ha
        treatment = TreatmentMothers.pending_treatment_with_changeable_water(field)
        product = ProductMothers.standard_herbicide(field.organization)

        # Producto con dosis 2L/1000L, precio 50€/L
        # Con 400L/ha (planificado): total_dose = 2 * 400 * 6 / 1000 = 4.8L → 240€
        # Con 600L/ha (real):        total_dose = 2 * 600 * 6 / 1000 = 7.2L → 360€
        treatment_product = TreatmentProductFactory(
            treatment=treatment,
            product=product,
            dose=Decimal('2.0'),
            dose_type='l_per_1000l',
            unit_price=Decimal('50.00'),
            organization=field.organization
        )

        planned_total_dose = treatment_product.total_dose  # 4.8L
        planned_total_price = treatment_product.total_price  # 240€

        # Finalizamos con más agua → costes suben
        treatment.finish_treatment(finish_date=date.today(), real_water_per_ha=600)
        treatment_product.refresh_from_db()
        assert treatment_product.total_dose == Decimal('7.2')
        assert treatment_product.total_price == Decimal('360.00')

        # Borramos finish_date (revertimos a pending)
        treatment.finish_date = None
        treatment.save()
        treatment_product.refresh_from_db()

        # CRÍTICO (Bug 1): Los costes deben volver al agua planificada (400L/ha)
        assert treatment_product.total_dose == planned_total_dose, (
            f"Bug 1: Tras borrar finish_date, total_dose debería ser {planned_total_dose} "
            f"(agua planificada 400L/ha), pero es {treatment_product.total_dose}"
        )
        assert treatment_product.total_price == planned_total_price, (
            f"Bug 1: Tras borrar finish_date, total_price debería ser {planned_total_price}, "
            f"pero es {treatment_product.total_price}"
        )


@pytest.mark.django_db
class TestRefinishingAfterRevertUpdatesCorrectly:
    """
    Bug 2: Al finalizar un tratamiento que fue revertido a pending,
    los costes deben actualizarse con el nuevo real_water_per_ha.
    """

    def test_refinishing_after_revert_updates_costs(self):
        """
        FALLA ESPERADA (Bug 2): Si se finaliza → revierte → finaliza de nuevo,
        los costes deben reflejar el nuevo mojado real.

        Flujo exacto que reportó el usuario:
        1. Tratamiento pendiente con water_per_ha=400
        2. Se finaliza con real_water=600 → costes a 600L/ha
        3. Se edita y se borra finish_date → debería volver a 400L/ha
        4. Se vuelve a finalizar con real_water=600 → costes deben quedar en 600L/ha
        """
        field = FieldMothers.cost_analysis_field()  # 6 ha
        treatment = TreatmentMothers.pending_treatment_with_changeable_water(field)
        product = ProductMothers.standard_herbicide(field.organization)

        treatment_product = TreatmentProductFactory(
            treatment=treatment,
            product=product,
            dose=Decimal('2.0'),
            dose_type='l_per_1000l',
            unit_price=Decimal('50.00'),
            organization=field.organization
        )

        # Paso 2: Finalizar con real_water=600
        treatment.finish_treatment(finish_date=date.today(), real_water_per_ha=600)
        treatment_product.refresh_from_db()
        assert treatment_product.total_dose == Decimal('7.2')
        assert treatment_product.total_price == Decimal('360.00')

        # Paso 3: Revertir a pending (borrar finish_date)
        treatment.finish_date = None
        treatment.save()
        treatment_product.refresh_from_db()

        # Paso 4: Volver a finalizar con real_water=600
        treatment.refresh_from_db()
        treatment.finish_treatment(finish_date=date.today(), real_water_per_ha=600)
        treatment_product.refresh_from_db()

        # CRÍTICO (Bug 2): Los costes deben ser los correctos para 600L/ha
        assert treatment.is_completed()
        assert treatment_product.total_dose == Decimal('7.2'), (
            f"Bug 2: Tras re-finalizar, total_dose debería ser 7.2L (600L/ha), "
            f"pero es {treatment_product.total_dose}"
        )
        assert treatment_product.total_price == Decimal('360.00'), (
            f"Bug 2: Tras re-finalizar, total_price debería ser 360€, "
            f"pero es {treatment_product.total_price}"
        )

    def test_refinishing_with_different_water_updates_costs(self):
        """
        Caso adicional: Finalizar → revertir → finalizar con DISTINTO agua real.
        Los costes deben reflejar el nuevo valor.
        """
        field = FieldMothers.cost_analysis_field()  # 6 ha
        treatment = TreatmentMothers.pending_treatment_with_changeable_water(field)
        product = ProductMothers.standard_herbicide(field.organization)

        treatment_product = TreatmentProductFactory(
            treatment=treatment,
            product=product,
            dose=Decimal('2.0'),
            dose_type='l_per_1000l',
            unit_price=Decimal('50.00'),
            organization=field.organization
        )

        # Primera finalización con 600L/ha
        treatment.finish_treatment(finish_date=date.today(), real_water_per_ha=600)

        # Revertir
        treatment.finish_date = None
        treatment.save()

        # Segunda finalización con 800L/ha
        # Con 800L/ha: 2 * 800 * 6 / 1000 = 9.6L → 480€
        treatment.refresh_from_db()
        treatment.finish_treatment(finish_date=date.today(), real_water_per_ha=800)
        treatment_product.refresh_from_db()

        assert treatment_product.total_dose == Decimal('9.6'), (
            f"Tras re-finalizar con 800L/ha, total_dose debería ser 9.6L, "
            f"pero es {treatment_product.total_dose}"
        )
        assert treatment_product.total_price == Decimal('480.00')
