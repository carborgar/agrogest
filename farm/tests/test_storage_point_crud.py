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


@pytest.mark.django_db
class StoragePointScreensTest(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="Org Pantallas")
        self.user = User.objects.create_user(
            username="screens-user", email="screens@example.com", password="pass123",
            organization=self.organization,
        )
        self.client.force_login(self.user)
        self.sp = StoragePoint.objects.create(name="Injeros", organization=self.organization)
        self.other_sp = StoragePoint.objects.create(name="Pitas", organization=self.organization)
        self.mine = Field.objects.create(name="Cartuja", area=2.5, crop="Olivo", planting_year=2020,
                                         organization=self.organization, storage_point=self.sp)
        self.solo = Field.objects.create(name="Pozo", area=0.8, crop="Olivo", planting_year=2020,
                                         organization=self.organization)
        self.elsewhere = Field.objects.create(name="Vegueta", area=3, crop="Olivo", planting_year=2020,
                                              organization=self.organization, storage_point=self.other_sp)

    def test_detalle_muestra_filas_y_resumen(self):
        response = self.client.get(reverse('storage-point-detail', args=[self.sp.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="tl-item sp-row"', count=3)
        self.assertContains(response, 'Independiente')
        self.assertContains(response, 'En Pitas')
        self.assertEqual(response.context['assigned_count'], 1)
        self.assertEqual(response.context['assigned_area'], 2.5)

    def test_detalle_no_usa_estilos_propios(self):
        response = self.client.get(reverse('storage-point-detail', args=[self.sp.pk]))
        self.assertNotContains(response, 'class="sa-')
        self.assertNotContains(response, '.sa-tile')

    def test_eliminar_solo_aparece_si_la_casetilla_esta_vacia(self):
        con_parcelas = self.client.get(reverse('storage-point-detail', args=[self.sp.pk]))
        self.assertNotContains(con_parcelas, 'Eliminar casetilla')
        vacia = StoragePoint.objects.create(name="Cortijo", organization=self.organization)
        sin_parcelas = self.client.get(reverse('storage-point-detail', args=[vacia.pk]))
        self.assertContains(sin_parcelas, 'Eliminar casetilla')

    def test_detalle_sin_parcelas_muestra_estado_vacio(self):
        Field.objects.all().delete()
        response = self.client.get(reverse('storage-point-detail', args=[self.sp.pk]))
        self.assertContains(response, 'Aún no tienes parcelas')
        self.assertNotContains(response, 'assignmentForm')

    def test_asignar_parcelas_mueve_y_libera(self):
        response = self.client.post(reverse('storage-point-detail', args=[self.sp.pk]),
                                    {'field_ids': [self.solo.pk, self.elsewhere.pk]})
        self.assertRedirects(response, reverse('storage-point-detail', args=[self.sp.pk]))
        for f in (self.mine, self.solo, self.elsewhere):
            f.refresh_from_db()
        self.assertIsNone(self.mine.storage_point)
        self.assertEqual(self.solo.storage_point, self.sp)
        self.assertEqual(self.elsewhere.storage_point, self.sp)

    def test_asignar_ignora_parcelas_de_otra_organizacion(self):
        otra_org = Organization.objects.create(name="Otra Org")
        ajena = Field.objects.create(name="Ajena", area=1, crop="Olivo", planting_year=2020,
                                     organization=otra_org)
        self.client.post(reverse('storage-point-detail', args=[self.sp.pk]),
                         {'field_ids': [self.solo.pk, ajena.pk]})
        ajena.refresh_from_db()
        self.solo.refresh_from_db()
        self.assertIsNone(ajena.storage_point)
        self.assertEqual(self.solo.storage_point, self.sp)

    def test_asignar_con_digitos_no_ascii_no_falla(self):
        response = self.client.post(reverse('storage-point-detail', args=[self.sp.pk]),
                                    {'field_ids': ['\u00b2', str(self.solo.pk)]})
        self.assertEqual(response.status_code, 302)
        self.solo.refresh_from_db()
        self.assertEqual(self.solo.storage_point, self.sp)

    def test_formulario_resume_parcelas_que_agrupa(self):
        response = self.client.get(reverse('storage-point-edit', args=[self.sp.pk]))
        self.assertEqual(response.context['field_count'], 1)
        self.assertEqual(response.context['field_area'], 2.5)
        self.assertContains(response, '1 parcela · 2,50 ha')

    def test_formulario_nuevo_no_calcula_resumen(self):
        response = self.client.get(reverse('storage-point-create'))
        self.assertNotIn('field_count', response.context)
        self.assertContains(response, 'Después podrás asignarle parcelas')

    def test_formulario_con_error_muestra_aviso_y_error_de_campo(self):
        response = self.client.post(reverse('storage-point-create'), {'name': 'injeros', 'notes': ''})
        self.assertContains(response, 'Revisa los campos marcados.')
        self.assertContains(response, 'Ya tienes una casetilla con ese nombre.')
        self.assertContains(response, 'aria-invalid="true"')
