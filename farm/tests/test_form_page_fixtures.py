"""
Fixtures HTML del formulario de tratamiento para los tests JS (jsdom).

Las páginas se renderizan con la plantilla REAL y unos datos fijos (ids explícitos, la fecha de hoy
sustituida por una fija), se guardan en static/js/tests/fixtures/ y este test falla si la plantilla o los
datos cambian y el fichero ya no coincide.

Para regenerarlos:   AGRO_REGEN_FIXTURES=1 DATABASE_URL=sqlite:////tmp/x.sqlite3 python3 -m pytest farm/tests/test_form_page_fixtures.py
"""
import os
import re
from datetime import date
from decimal import Decimal
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import Organization
from farm.models import Field, Machine, Product, ProductType, Treatment, TreatmentProduct
from farm.tests.form_helpers import formset_data

User = get_user_model()
FIXTURES = Path(__file__).resolve().parents[2] / 'static' / 'js' / 'tests' / 'fixtures'
FIXED_TODAY = '2030-06-15'


def _normalize(html):
    html = html.replace(date.today().isoformat(), FIXED_TODAY)
    html = re.sub(r'(name="csrfmiddlewaretoken" value=")[^"]+', r'\1TOKEN', html)
    return re.sub(r'(csrfToken: ")[^"]+', r'\1TOKEN', html)


class FormPageFixtures(TestCase):
    maxDiff = None

    def setUp(self):
        self.org = Organization.objects.create(name="Org Fixtures")
        self.user = User.objects.create_user(username="fix", email="fix@example.com", password="pass123",
                                             organization=self.org)
        self.client.force_login(self.user)
        self.field_a = Field.objects.create(id=1, name="Parcela A", area=4.2, crop="Olivo", planting_year=2020, organization=self.org)
        Field.objects.create(id=2, name="Parcela B", area=2, crop="Vid", planting_year=2020, organization=self.org)
        Machine.objects.create(id=1, name="Cuba 2000", type="Pulverizador", capacity=2000, organization=self.org)
        Machine.objects.create(id=2, name="Cuba 1000", type="Pulverizador", capacity=1000, organization=self.org)
        ptype = ProductType.objects.create(id=1, name="Fitosanitario", organization=self.org)

        def product(pk, name, price, **kw):
            return Product.objects.create(id=pk, name=name, product_type=ptype, price=Decimal(price), organization=self.org, **kw)
        self.fung = product(1, "Fungicida", "9.50", spraying_dose=Decimal("3"), spraying_dose_type="kg_per_1000l")
        self.insec = product(2, "Insecticida", "10.00", spraying_dose=Decimal("0.5"), spraying_dose_type="l_per_1000l")
        self.abono = product(3, "Abono", "10.00", fertigation_dose=Decimal("10"), fertigation_dose_type="l_per_ha")
        self.moj = product(4, "Mojante", "6.00", spraying_dose=Decimal("1.5"), spraying_dose_type="l_per_ha")

    def _pages(self):
        pages = {'treatment_form_create.html': self.client.get(reverse('treatment-create')).content.decode()}

        t = Treatment.objects.create(organization=self.org, field=self.field_a, machine=Machine.objects.get(pk=1),
                                     name="Guardado", type="spraying", date=date.today(), water_per_ha=1000)
        for pos, (prod, dose, total, ovr) in enumerate([
                (self.fung, "3", "12.6", False), (self.insec, "0.5", "2.1", True), (self.moj, "1.5", "6.3", False)]):
            TreatmentProduct.objects.create(treatment=t, product=prod, dose=Decimal(dose),
                                            total_dose=Decimal(total), total_overridden=ovr, position=pos)
        edit = self.client.get(reverse('treatment-edit', kwargs={'pk': t.pk})).content.decode()
        # Los ids de tratamiento y líneas dependen de la base de datos: se fijan para que el fichero sea estable
        edit = edit.replace(f'/tratamientos/{t.pk}/', '/tratamientos/1/').replace(f'/tratamientos/{t.pk}"', '/tratamientos/1"')
        ids = {str(tp.pk): str(n) for n, tp in enumerate(t.treatmentproduct_set.order_by('position'), start=1)}
        edit = re.sub(r'(name="treatmentproduct_set-\d+-id" value=")(\d+)"', lambda m: f'{m.group(1)}{ids[m.group(2)]}"', edit)
        edit = re.sub(r'(name="treatmentproduct_set-\d+-treatment" value=")\d+"', r'\g<1>1"', edit)
        pages['treatment_form_edit.html'] = edit

        # Envío fallido: sin nombre y con una dosis de 3 decimales ≥ 1 («1.500», que no es «mil quinientos»)
        data = {'name': '', 'type': 'spraying', 'date': date.today().isoformat(), 'field': '1', 'machine': '1',
                'water_per_ha': '1000', 'finish_date': ''}
        data.update(formset_data([{'product': self.fung.pk, 'dose': '3.000', 'total_dose': '12.6000', 'total_overridden': 'false'},
                                  {'product': self.moj.pk, 'dose': '1.500', 'total_dose': '6.3000', 'total_overridden': 'false'}]))
        response = self.client.post(reverse('treatment-create'), data)
        self.assertEqual(response.status_code, 200)
        pages['treatment_form_bound.html'] = response.content.decode()
        return {name: _normalize(html) for name, html in pages.items()}

    def test_fixtures_are_up_to_date(self):
        pages = self._pages()
        regen = os.environ.get('AGRO_REGEN_FIXTURES') == '1'
        for name, html in pages.items():
            path = FIXTURES / name
            if regen:
                FIXTURES.mkdir(parents=True, exist_ok=True)
                path.write_text(html, encoding='utf-8')
                continue
            self.assertTrue(path.exists(), f'Falta {name}: regenera con AGRO_REGEN_FIXTURES=1')
            self.assertEqual(path.read_text(encoding='utf-8'), html,
                             f'{name} está desactualizado: regenera con AGRO_REGEN_FIXTURES=1 pytest farm/tests/test_form_page_fixtures.py')
