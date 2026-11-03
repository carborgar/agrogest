import json
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import Organization
from farm.forms import FieldForm
from farm.models import Field, Machine, Product, ProductType, StoragePoint, Treatment, TreatmentProduct

User = get_user_model()


class _Base(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Org Parcelas")
        self.user = User.objects.create_user(username="fp", email="fp@example.com", password="x", organization=self.org)
        self.client.force_login(self.user)
        self.field = Field.objects.create(name="Cartuja", area=2.53, crop="Olivo", planting_year=2010, organization=self.org)
        self.other_org = Organization.objects.create(name="Otra")
        self.alien = Field.objects.create(name="Ajena", area=1, crop="Olivo", planting_year=2015, organization=self.other_org)

    def treatment(self, name, d, done=False, field=None):
        t = Treatment(name=name, field=field or self.field, type='fertigation', date=d, organization=self.org)
        if done:
            t.finish_date = d
            t.status = Treatment.STATUS_COMPLETED
        t.save()
        return t


@pytest.mark.django_db
class FieldDetailTest(_Base):
    def test_resumen_y_grupos(self):
        today = date.today()
        self.treatment("Atrasado", today - timedelta(days=3))
        self.treatment("Proximo", today + timedelta(days=2))
        self.treatment("Hecho", today - timedelta(days=30), done=True)
        r = self.client.get(reverse('field-detail', args=[self.field.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context['total_treatments'], 3)
        self.assertEqual([t.name for t in r.context['pending_treatments']], ['Atrasado', 'Proximo'])
        self.assertEqual([t.name for t in r.context['done_treatments']], ['Hecho'])
        self.assertContains(r, 'Pendientes · 2')
        self.assertContains(r, 'Plantado en 2010')

    def test_contadores_y_listas_usan_el_mismo_criterio(self):
        today = date.today()
        self.treatment("A", today - timedelta(days=3))
        self.treatment("B", today + timedelta(days=2))
        self.treatment("C", today - timedelta(days=30), done=True)
        r = self.client.get(reverse('field-detail', args=[self.field.pk]))
        self.assertEqual(r.context['pending_total'], len(r.context['pending_treatments']))
        self.assertEqual(r.context['completed_count'], len(r.context['done_treatments']))
        # Un tratamiento con fecha de fin pero estado pendiente cuenta como pendiente en cifra y lista
        odd = self.treatment("D", today)
        Treatment.objects.filter(pk=odd.pk).update(finish_date=today)
        r = self.client.get(reverse('field-detail', args=[self.field.pk]))
        self.assertEqual(r.context['pending_total'], len(r.context['pending_treatments']))
        self.assertIn('D', [t.name for t in r.context['pending_treatments']])

    def test_sin_tratamientos_muestra_estado_vacio(self):
        r = self.client.get(reverse('field-detail', args=[self.field.pk]))
        self.assertContains(r, 'Sin tratamientos todavía')

    def test_casetilla_independiente_y_asignada(self):
        r = self.client.get(reverse('field-detail', args=[self.field.pk]))
        self.assertContains(r, 'Independiente')
        sp = StoragePoint.objects.create(name="Casetilla Norte", organization=self.org)
        self.field.storage_point = sp
        self.field.save()
        self.assertContains(self.client.get(reverse('field-detail', args=[self.field.pk])), 'Casetilla Norte')

    def test_parcela_ajena_da_404(self):
        for name in ('field-detail', 'field-edit'):
            self.assertEqual(self.client.get(reverse(name, args=[self.alien.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('field-delete', args=[self.alien.pk])).status_code, 404)
        self.assertTrue(Field.objects.filter(pk=self.alien.pk).exists())


@pytest.mark.django_db
class FieldDeleteTest(_Base):
    def test_get_no_borra_ni_muestra_pantalla(self):
        # La interfaz borra con un formulario POST (field_detail/field_list); un GET no es válido
        self.assertEqual(self.client.get(reverse('field-delete', args=[self.field.pk])).status_code, 405)
        self.assertTrue(Field.objects.filter(pk=self.field.pk).exists())

    def test_borra_parcela_sin_tratamientos(self):
        r = self.client.post(reverse('field-delete', args=[self.field.pk]), follow=True)
        self.assertFalse(Field.objects.filter(pk=self.field.pk).exists())
        self.assertContains(r, 'Parcela eliminada con éxito.')

    def test_con_tratamientos_no_borra_ni_da_500(self):
        self.treatment("T", date.today())
        r = self.client.post(reverse('field-delete', args=[self.field.pk]), follow=True)
        self.assertTrue(Field.objects.filter(pk=self.field.pk).exists())
        self.assertContains(r, 'No se puede eliminar una parcela con tratamientos.')


@pytest.mark.django_db
class FieldFormTest(_Base):
    def data(self, **over):
        d = {'name': 'Nueva', 'crop': 'Olivo', 'area': '1.5', 'planting_year': '2012', 'storage_point': '', 'geometry': ''}
        d.update(over)
        return d

    def test_edicion_conserva_un_ano_antiguo(self):
        # Antes el año era una lista de 10 años: una parcela de 2010 se guardaba como el año en curso
        r = self.client.get(reverse('field-edit', args=[self.field.pk]))
        self.assertContains(r, 'value="2010"')
        self.client.post(reverse('field-edit', args=[self.field.pk]), self.data(name='Cartuja', planting_year='2010', area='2.53'))
        self.field.refresh_from_db()
        self.assertEqual(self.field.planting_year, 2010)

    def test_crea_parcela(self):
        r = self.client.post(reverse('field-create'), self.data())
        self.assertRedirects(r, reverse('field-list'))
        self.assertTrue(Field.objects.filter(name='Nueva', organization=self.org).exists())

    def test_superficie_debe_ser_positiva(self):
        for bad in ('0', '-3'):
            r = self.client.post(reverse('field-create'), self.data(area=bad))
            self.assertEqual(r.status_code, 200)
            self.assertContains(r, 'La superficie debe ser mayor que 0.')
        self.assertFalse(Field.objects.filter(name='Nueva').exists())

    def test_ano_fuera_de_rango(self):
        for bad in ('1850', str(date.today().year + 1)):
            form = FieldForm(self.data(planting_year=bad), user=self.user)
            self.assertFalse(form.is_valid())
            self.assertIn('planting_year', form.errors)

    def test_errores_muestran_aviso_general(self):
        r = self.client.post(reverse('field-create'), self.data(name=''))
        self.assertContains(r, 'Revisa los campos marcados.')
        self.assertContains(r, 'tf-err')

    POLY = {'type': 'Polygon', 'coordinates': [[[-4.5, 37.5], [-4.4, 37.5], [-4.4, 37.6], [-4.5, 37.5]]]}

    def test_geometria_valida_se_guarda_y_se_recarga(self):
        for geom in (self.POLY, {'type': 'Feature', 'properties': {}, 'geometry': self.POLY},
                     {'type': 'MultiPolygon', 'coordinates': [self.POLY['coordinates']]}):
            Field.objects.filter(name='Nueva').delete()
            self.client.post(reverse('field-create'), self.data(geometry=json.dumps(geom)))
            f = Field.objects.get(name='Nueva')
            self.assertEqual(json.loads(f.geometry), geom)
        r = self.client.get(reverse('field-edit', args=[f.pk]))
        self.assertContains(r, 'id_geometry')
        r = self.client.get(reverse('field-detail', args=[f.pk]))
        self.assertEqual(r.context['geometry_data'], geom)
        self.assertContains(r, 'id="field-geometry"')

    def test_geometria_invalida_da_error(self):
        bad = ['no json', '[]', '{"type": "Point", "coordinates": [1, 2]}', '{"type": "Polygon", "coordinates": []}',
               '{"type": "Polygon", "coordinates": [[[1, 2], [3, 4]]]}', '{"type": "Polygon", "coordinates": [[["a", 1]] ]}',
               '<script>alert(1)</script>']
        for raw in bad:
            r = self.client.post(reverse('field-create'), self.data(geometry=raw))
            self.assertEqual(r.status_code, 200, raw)
            self.assertContains(r, 'El contorno no es válido')
        self.assertFalse(Field.objects.filter(name='Nueva').exists())

    def test_script_en_el_nombre_no_rompe_el_detalle(self):
        evil = '</script><script>alert(1)</script>'
        f = Field.objects.create(name=evil, crop='<img src=x onerror=alert(1)>', area=1, planting_year=2010,
                                 organization=self.org, geometry=json.dumps(self.POLY))
        r = self.client.get(reverse('field-detail', args=[f.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, '</script><script>alert(1)')
        self.assertContains(r, 'id="field-popup"')

    def test_casetillas_solo_de_la_organizacion(self):
        mine = StoragePoint.objects.create(name="Mía", organization=self.org)
        StoragePoint.objects.create(name="Ajena", organization=self.other_org)
        form = FieldForm(user=self.user)
        self.assertEqual(list(form.fields['storage_point'].queryset), [mine])


@pytest.mark.django_db
class FieldCostsTest(_Base):
    def setUp(self):
        super().setUp()
        ptype = ProductType.objects.create(name="Fungicida", organization=self.org)
        product = Product.objects.create(name="Cobre", product_type=ptype, organization=self.org, price=Decimal('10'),
                                         spraying_dose=2.0, spraying_dose_type='l_per_1000l',
                                         fertigation_dose=5.0, fertigation_dose_type='l_per_ha')
        self.today = date.today()
        old = self.treatment("Antiguo", date(self.today.year - 1, 3, 1), done=True)
        recent = self.treatment("Reciente", self.today - timedelta(days=5), done=True)
        for t, total in ((old, 100), (recent, 40)):
            TreatmentProduct.objects.create(treatment=t, product=product, dose=Decimal('2'), dose_type='l_per_1000l',
                                            total_dose=Decimal('4'), total_dose_unit='L', unit_price=Decimal('10'),
                                            total_price=Decimal(total), organization=self.org)
        self.url = reverse('api-field-costs-data')

    def test_pagina_con_pestanas_de_periodo(self):
        r = self.client.get(reverse('field-costs'))
        self.assertEqual(r.status_code, 200)
        self.assertEqual([t['value'] for t in r.context['period_tabs']],
                         ['all', str(self.today.year), str(self.today.year - 1), str(self.today.year - 2)])
        self.assertContains(r, 'data-period="all"')

    def test_sin_parcelas_muestra_estado_vacio(self):
        other = User.objects.create_user(username="vacio", email="v@example.com", password="x",
                                         organization=Organization.objects.create(name="Vacía"))
        self.client.force_login(other)
        self.assertContains(self.client.get(reverse('field-costs')), 'Aún no tienes parcelas')

    def total(self, **params):
        r = self.client.get(self.url, params)
        self.assertEqual(r.status_code, 200)
        return r.json()['total_cost']

    def test_todos_no_limita_por_fechas(self):
        # total_price se recalcula al guardar: se compara con lo guardado, no con el valor que se pasó
        self.assertAlmostEqual(self.total(all=1), float(sum(tp.total_price for tp in TreatmentProduct.objects.all())))
        self.assertGreater(self.total(all=1), self.total())

    def test_rango_de_un_ano(self):
        y = self.today.year - 1
        old = TreatmentProduct.objects.get(treatment__name='Antiguo')
        self.assertAlmostEqual(self.total(date_from=f'{y}-01-01', date_to=f'{y}-12-31'), float(old.total_price))

    def test_fechas_invalidas_no_dan_500(self):
        for params in ({'date_from': 'ayer'}, {'date_from': '2026-02-31'}, {'date_to': 'x'}, {'field_ids': 'abc'}):
            self.assertEqual(self.client.get(self.url, params).status_code, 200)

    def test_field_ids_raros_se_ignoran(self):
        for bad in ('١٢٣', '9' * 30, '²', '-1', ' 1'):
            r = self.client.get(self.url, {'all': 1, 'field_ids': bad})
            self.assertEqual(r.status_code, 200, bad)
            self.assertEqual([f['name'] for f in r.json()['fields']], ['Cartuja'], bad)

    def test_requiere_sesion(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_no_incluye_parcelas_ajenas(self):
        Treatment(name="Ajeno", field=self.alien, type='fertigation', date=self.today, organization=self.other_org).save()
        names = [f['name'] for f in self.client.get(self.url, {'all': 1}).json()['fields']]
        self.assertEqual(names, ['Cartuja'])
