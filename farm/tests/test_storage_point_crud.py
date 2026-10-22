import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import Organization
from farm.models import Field, StoragePoint

User = get_user_model()


@pytest.mark.django_db
class StoragePointCrudTest(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="Org CRUD")
        self.user = User.objects.create_user(
            username="crud-user", email="crud@example.com", password="pass123",
            organization=self.organization,
        )
        self.client.force_login(self.user)
        self.sp = StoragePoint.objects.create(name="Injeros", organization=self.organization)

    def test_crear_con_nombre_repetido_muestra_error_en_formulario(self):
        response = self.client.post(reverse('storage-point-create'), {'name': 'injeros', 'notes': ''})
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context['form'], 'name', 'Ya tienes una casetilla con ese nombre.')
        self.assertEqual(StoragePoint.objects.count(), 1)

    def test_mismo_nombre_en_otra_organizacion_esta_permitido(self):
        StoragePoint.objects.create(name="Vegueta", organization=Organization.objects.create(name="Otra"))
        response = self.client.post(reverse('storage-point-create'), {'name': 'Vegueta', 'notes': ''})
        self.assertRedirects(response, reverse('field-list'))
        self.assertTrue(StoragePoint.objects.filter(organization=self.organization, name='Vegueta').exists())

    def test_editar_sin_cambiar_nombre_no_choca_consigo_misma(self):
        response = self.client.post(reverse('storage-point-edit', args=[self.sp.pk]), {'name': 'Injeros', 'notes': 'Junto al pozo'})
        self.assertRedirects(response, reverse('field-list'))
        self.sp.refresh_from_db()
        self.assertEqual(self.sp.notes, 'Junto al pozo')

    def test_borrar_casetilla(self):
        response = self.client.post(reverse('storage-point-delete', args=[self.sp.pk]))
        self.assertRedirects(response, reverse('field-list'))
        self.assertFalse(StoragePoint.objects.filter(pk=self.sp.pk).exists())

    def test_borrar_casetilla_deja_sus_parcelas_independientes(self):
        field = Field.objects.create(name="P", area=1, crop="Olivo", planting_year=2020,
                                     organization=self.organization, storage_point=self.sp)
        self.client.post(reverse('storage-point-delete', args=[self.sp.pk]))
        field.refresh_from_db()
        self.assertIsNone(field.storage_point)
