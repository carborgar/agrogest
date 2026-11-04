"""Aislamiento por organización en vistas de borrado/modificación por pk (IDOR)
y mensajes de éxito de los DeleteView (Django 5.1 ya no llama a delete())."""
from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse

from farm.models import Expense, ExpenseType, Field, Harvest, ProductPriceHistory, Treatment
from farm.tests.factories import FieldFactory, OrganizationFactory, ProductFactory, TreatmentFactory

User = get_user_model()


@pytest.mark.django_db
class OrganizationIsolationTest(TestCase):
    def setUp(self):
        self.org = OrganizationFactory(name="Org Propia")
        self.other = OrganizationFactory(name="Org Ajena")
        self.user = User.objects.create_user(
            username="propio", email="p@example.com", password="x", organization=self.org)
        self.client.force_login(self.user)

        self.other_field = FieldFactory(organization=self.other)
        self.other_treatment = TreatmentFactory(organization=self.other, field=self.other_field)

    def _messages(self, response):
        return [str(m) for m in get_messages(response.wsgi_request)]

    def test_eliminar_tratamiento_ajeno_404(self):
        r = self.client.post(reverse('treatment-delete', args=[self.other_treatment.pk]))
        self.assertEqual(r.status_code, 404)
        self.assertTrue(Treatment.objects.filter(pk=self.other_treatment.pk).exists())

    def test_finalizar_tratamiento_ajeno_404(self):
        r = self.client.post(reverse('treatment-finish', args=[self.other_treatment.pk]),
                             {'finish_date': '2026-01-01'})
        self.assertEqual(r.status_code, 404)
        self.other_treatment.refresh_from_db()
        self.assertNotEqual(self.other_treatment.status, Treatment.STATUS_COMPLETED)

    def test_clonar_tratamiento_ajeno_404(self):
        url = reverse('treatment-clone', args=[self.other_treatment.pk])
        self.assertEqual(self.client.get(url).status_code, 404)
        own_field = FieldFactory(organization=self.org)
        r = self.client.post(url, {'field_id': [own_field.pk], 'date': '2026-01-01'})
        self.assertEqual(r.status_code, 404)
        self.assertEqual(Treatment.objects.count(), 1)

    def test_parcela_ajena_detalle_edicion_y_borrado_404(self):
        self.assertEqual(self.client.get(reverse('field-detail', args=[self.other_field.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('field-edit', args=[self.other_field.pk])).status_code, 404)
        r = self.client.post(reverse('field-delete', args=[self.other_field.pk]))
        self.assertEqual(r.status_code, 404)
        self.assertTrue(Field.objects.filter(pk=self.other_field.pk).exists())

    def test_historial_precios_ajeno_404(self):
        product = ProductFactory(organization=self.other)
        entry = ProductPriceHistory.objects.create(
            organization=self.other, product=product, price=1, effective_date=date.today())
        r = self.client.post(reverse('product-price-delete', args=[entry.pk]))
        self.assertEqual(r.status_code, 404)
        self.assertTrue(ProductPriceHistory.objects.filter(pk=entry.pk).exists())

    def test_gasto_tipo_gasto_y_cosecha_ajenos_404(self):
        etype = ExpenseType.objects.create(organization=self.other, name="Agua")
        expense = Expense.objects.create(
            organization=self.other, field=self.other_field, expense_type=etype,
            description="x", payment_date=date.today(), amount=10)
        harvest = Harvest.objects.create(
            organization=self.other, field=self.other_field, date=date.today(), amount=100)
        for name, obj in [('expense-delete', expense), ('expense-type-delete', etype), ('harvest-delete', harvest)]:
            r = self.client.post(reverse(name, args=[obj.pk]))
            self.assertEqual(r.status_code, 404, name)
            self.assertTrue(type(obj).objects.filter(pk=obj.pk).exists(), name)

    # ── Mensajes de éxito (DeleteView de Django 5.1 no llama a delete()) ──
    def test_borrar_gasto_muestra_mensaje(self):
        field = FieldFactory(organization=self.org)
        etype = ExpenseType.objects.create(organization=self.org, name="Agua")
        expense = Expense.objects.create(
            organization=self.org, field=field, expense_type=etype,
            description="x", payment_date=date.today(), amount=10)
        r = self.client.post(reverse('expense-delete', args=[expense.pk]))
        self.assertEqual(r.status_code, 302)
        self.assertFalse(Expense.objects.filter(pk=expense.pk).exists())
        self.assertIn('Gasto eliminado con éxito.', self._messages(r))

        r = self.client.post(reverse('expense-type-delete', args=[etype.pk]))
        self.assertIn('Tipo de gasto eliminado con éxito.', self._messages(r))

    def test_borrar_cosecha_y_parcela_muestran_mensaje(self):
        field = FieldFactory(organization=self.org)
        harvest = Harvest.objects.create(organization=self.org, field=field, date=date.today(), amount=5)
        r = self.client.post(reverse('harvest-delete', args=[harvest.pk]))
        self.assertIn('Cosecha eliminada correctamente.', self._messages(r))
        r = self.client.post(reverse('field-delete', args=[field.pk]))
        self.assertFalse(Field.objects.filter(pk=field.pk).exists())
        self.assertIn('Parcela eliminada con éxito.', self._messages(r))


@pytest.mark.django_db
class FieldDeleteAndCloneTest(TestCase):
    def setUp(self):
        self.org = OrganizationFactory(name="Org Propia")
        self.user = User.objects.create_user(
            username="propio2", email="p2@example.com", password="x", organization=self.org)
        self.client.force_login(self.user)
        self.field = FieldFactory(organization=self.org)

    def _delete_blocked(self):
        r = self.client.post(reverse('field-delete', args=[self.field.pk]))
        self.assertRedirects(r, reverse('field-detail', args=[self.field.pk]), fetch_redirect_response=False)
        self.assertTrue(Field.objects.filter(pk=self.field.pk).exists())
        self.assertIn('No se puede eliminar: la parcela tiene tratamientos, gastos o cosechas.',
                      [str(m) for m in get_messages(r.wsgi_request)])
        self.assertFalse(self.field.can_be_deleted())

    def test_parcela_con_gasto_no_se_borra(self):
        etype = ExpenseType.objects.create(organization=self.org, name="Agua")
        Expense.objects.create(organization=self.org, field=self.field, expense_type=etype,
                               description="x", payment_date=date.today(), amount=10)
        self._delete_blocked()

    def test_parcela_con_cosecha_no_se_borra(self):
        Harvest.objects.create(organization=self.org, field=self.field, date=date.today(), amount=5)
        self._delete_blocked()

    def test_parcela_con_tratamiento_no_se_borra(self):
        TreatmentFactory(organization=self.org, field=self.field)
        self._delete_blocked()

    def test_borrar_parcela_por_get_da_405(self):
        r = self.client.get(reverse('field-delete', args=[self.field.pk]))
        self.assertEqual(r.status_code, 405)

    def test_clonar_con_field_id_invalido_da_404(self):
        treatment = TreatmentFactory(organization=self.org, field=self.field)
        for bad in ['abc', '²']:
            r = self.client.post(reverse('treatment-clone', args=[treatment.pk]), {'field_id': bad})
            self.assertEqual(r.status_code, 404, bad)

    def test_clonar_a_parcela_ajena_da_404(self):
        other_field = FieldFactory(organization=OrganizationFactory(name="Otra"))
        treatment = TreatmentFactory(organization=self.org, field=self.field)
        r = self.client.post(reverse('treatment-clone', args=[treatment.pk]), {'field_id': other_field.pk})
        self.assertEqual(r.status_code, 404)

    def test_repetir_tratamiento_ajeno_da_404(self):
        other = OrganizationFactory(name="Otra2")
        treatment = TreatmentFactory(organization=other, field=FieldFactory(organization=other))
        r = self.client.post(reverse('treatment-repeat', args=[treatment.pk]), {'dates': '2026-11-10'})
        self.assertEqual(r.status_code, 404)
