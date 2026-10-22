import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import Organization
from farm.models import Field, StoragePoint

User = get_user_model()


@pytest.mark.django_db
class StoragePointListViewTest(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="Org Casetillas")
        self.user = User.objects.create_user(
            username="sp-user", email="sp@example.com", password="pass123",
            organization=self.organization,
        )
        self.client.force_login(self.user)
        self.sp = StoragePoint.objects.create(name="Casetilla Norte", organization=self.organization)

        def field(name, sp=None):
            return Field.objects.create(
                name=name, area=1, crop="Olivo", planting_year=2020,
                organization=self.organization, storage_point=sp,
            )

        field("Agrupada A", self.sp)
        field("Agrupada B", self.sp)
        field("Suelta 1")
        field("Suelta 2")

    def test_lista_parcelas_sueltas_como_casetilla_propia(self):
        response = self.client.get(reverse('storage-point-list'))
        self.assertEqual(response.status_code, 200)
        names = [f.name for f in response.context['unassigned_fields']]
        self.assertEqual(names, ['Suelta 1', 'Suelta 2'])
        self.assertContains(response, 'Casetilla propia')

    def test_puntos_de_reparto_suma_casetillas_y_parcelas_sueltas(self):
        response = self.client.get(reverse('storage-point-list'))
        # 1 casetilla + 2 parcelas sueltas = 3 puntos, igual que en Preparar productos
        self.assertEqual(response.context['distribution_points_count'], 3)
        self.assertContains(response, '3 puntos de reparto')

    def test_casetilla_muestra_hectareas_de_sus_parcelas(self):
        Field.objects.filter(name='Agrupada A').update(area=3)
        response = self.client.get(reverse('storage-point-list'))
        self.assertEqual(response.context['storage_points'][0].total_area, 4)
        # Parcelas de mayor a menor superficie
        self.assertEqual([f.name for f in response.context['storage_points'][0].fields.all()], ['Agrupada A', 'Agrupada B'])

    def test_sin_casetillas_explica_que_no_es_obligatorio(self):
        self.sp.fields.update(storage_point=None)
        self.sp.delete()
        response = self.client.get(reverse('storage-point-list'))
        self.assertContains(response, 'No es obligatorio')
        self.assertEqual(response.context['distribution_points_count'], 4)
