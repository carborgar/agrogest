import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import Organization
from farm.models import Field, StoragePoint

User = get_user_model()


class _ParcelasYCasetillasBase(TestCase):
    """Datos comunes: 1 casetilla con 2 parcelas, 1 casetilla vacía y 2 parcelas sueltas."""

    def setUp(self):
        self.organization = Organization.objects.create(name="Org Parcelas")
        self.user = User.objects.create_user(
            username="pl-user", email="pl@example.com", password="pass123",
            organization=self.organization,
        )
        self.client.force_login(self.user)
        self.sp = StoragePoint.objects.create(name="Casetilla Norte", organization=self.organization)
        self.sp_empty = StoragePoint.objects.create(name="Nave Vacía", organization=self.organization)

        self.make_field("Agrupada A", 3, self.sp)
        self.make_field("Agrupada B", 1, self.sp)
        self.make_field("Suelta 1", 2)
        self.make_field("Suelta 2", 1)

    def make_field(self, name, area, sp=None, org=None):
        return Field.objects.create(
            name=name, area=area, crop="Olivo", planting_year=2020,
            organization=org or self.organization, storage_point=sp,
        )



@pytest.mark.django_db
class FieldListGroupingTest(_ParcelasYCasetillasBase):
    """El listado de parcelas se agrupa por casetilla (punto de reparto)."""

    def get(self):
        response = self.client.get(reverse('field-list'))
        self.assertEqual(response.status_code, 200)
        return response

    def test_agrupa_parcelas_por_casetilla(self):
        groups = {g['storage_point'].name: g for g in self.get().context['storage_point_groups']}
        # De mayor a menor superficie
        self.assertEqual([f.name for f in groups['Casetilla Norte']['fields']], ['Agrupada A', 'Agrupada B'])
        self.assertEqual(groups['Casetilla Norte']['area'], 4)
        # Una casetilla vacía también aparece, para poder asignarle parcelas
        self.assertEqual(groups['Nave Vacía']['fields'], [])

    def test_parcelas_sin_casetilla_van_aparte(self):
        response = self.get()
        self.assertEqual([f.name for f in response.context['solo_fields']], ['Suelta 1', 'Suelta 2'])
        self.assertContains(response, 'El producto se deja en cada parcela')

    def test_puntos_de_reparto_suma_casetillas_y_parcelas_sueltas(self):
        # 2 casetillas + 2 parcelas sueltas, igual que en Preparar productos
        self.assertEqual(self.get().context['distribution_points_count'], 4)

    def test_no_muestra_parcelas_ni_casetillas_de_otra_organizacion(self):
        other = Organization.objects.create(name="Otra")
        other_sp = StoragePoint.objects.create(name="Ajena", organization=other)
        self.make_field("Parcela ajena", 9, other_sp, org=other)
        response = self.get()
        self.assertNotContains(response, 'Parcela ajena')
        self.assertNotContains(response, 'Ajena')
        self.assertEqual(response.context['total_fields'], 4)

    def test_listado_de_casetillas_redirige_a_parcelas(self):
        response = self.client.get(reverse('storage-point-list'))
        self.assertRedirects(response, reverse('field-list'))


@pytest.mark.django_db
class StoragePointAssignViewTest(_ParcelasYCasetillasBase):
    """Pantalla de asignar parcelas a una casetilla."""

    def test_ordena_propias_sueltas_y_de_otras_casetillas(self):
        self.make_field("De la vacía", 1, self.sp_empty)
        response = self.client.get(reverse('storage-point-detail', args=[self.sp.pk]))
        names = [f.name for f in response.context['all_fields']]
        self.assertEqual(names, ['Agrupada A', 'Agrupada B', 'Suelta 1', 'Suelta 2', 'De la vacía'])
        self.assertEqual(response.context['assigned_area'], 4)
        self.assertContains(response, 'Se moverá aquí')

    def test_guardar_asigna_y_quita_parcelas(self):
        suelta = Field.objects.get(name='Suelta 1')
        agrupada_b = Field.objects.get(name='Agrupada B')
        agrupada_a = Field.objects.get(name='Agrupada A')
        self.client.post(reverse('storage-point-detail', args=[self.sp.pk]),
                         {'field_ids': [agrupada_a.pk, suelta.pk]})
        self.assertEqual(set(self.sp.fields.values_list('name', flat=True)), {'Agrupada A', 'Suelta 1'})
        agrupada_b.refresh_from_db()
        self.assertIsNone(agrupada_b.storage_point)
