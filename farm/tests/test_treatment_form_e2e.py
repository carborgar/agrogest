"""
Fase 5: de punta a punta sin navegador (no hay Playwright ni Chromium en este entorno).

Cada caso hace lo que hace el controlador JS al enviar: POST con los valores normalizados de
`TreatmentFormState.toFormValues` (dosis a 3 decimales, total a 4, punto decimal) y después comprueba
en la página de DETALLE los valores que el propio formulario enseña (los del fichero de casos
`treatment_calc_cases.json`, calculados a mano): total, coste, coste/ha, cubas y dosis por cuba.
"""
import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import Organization
from farm.models import Field, Machine, Product, ProductType, Treatment
from farm.tests.form_helpers import formset_data

User = get_user_model()
CASES = {c['id']: c for c in json.loads(
    (Path(__file__).parent / 'fixtures' / 'treatment_calc_cases.json').read_text(encoding='utf-8'))['cases']}


class FormToDetailTests(TestCase):

    def setUp(self):
        self.org = Organization.objects.create(name="Org E2E")
        self.user = User.objects.create_user(username="e2e", email="e2e@example.com", password="pass123",
                                             organization=self.org)
        self.client.force_login(self.user)
        self.ptype = ProductType.objects.create(name="Fito", organization=self.org)
        self.create_url = reverse("treatment-create")

    def _case_objects(self, case_id):
        inp = CASES[case_id]['input']
        field = Field.objects.create(name=f"Parcela {case_id}", area=inp['field_area'], crop="Olivo",
                                     planting_year=2020, organization=self.org)
        machine = Machine.objects.create(name=f"Cuba {case_id}", type="Pulverizador", capacity=inp['capacity'],
                                         organization=self.org)
        product = Product.objects.create(
            name=f"Producto {case_id}", product_type=self.ptype, price=Decimal(inp['price']),
            spraying_dose=Decimal(inp['dose']), spraying_dose_type=inp['dose_type'], organization=self.org)
        return field, machine, product

    def _post_case(self, case_id):
        case = CASES[case_id]
        inp, exp = case['input'], case['expected']
        field, machine, product = self._case_objects(case_id)
        overridden = bool(inp['total_override'])
        # Lo que escribe el controlador: con total a mano la dosis se deriva del total (4 decimales)
        dose = f"{exp['dose']:.4f}" if overridden else f"{float(inp['dose']):.3f}"
        total = f"{exp['total_dose']:.4f}"
        data = {
            "name": f"Caso {case_id}", "type": "spraying",
            "date": (date.today() + timedelta(days=1)).isoformat(),
            "field": str(field.pk), "machine": str(machine.pk),
            "water_per_ha": str(inp['water_per_ha']), "finish_date": "",
        }
        data.update(formset_data([{"product": product.pk, "dose": dose, "total_dose": total,
                                   "total_overridden": "true" if overridden else "false"}]))
        response = self.client.post(self.create_url, data)
        self.assertEqual(response.status_code, 302, getattr(response, "context", None) and response.context["form_errors"])
        return Treatment.objects.get(name=f"Caso {case_id}"), exp

    def _assert_detail_matches(self, treatment, exp):
        response = self.client.get(reverse("treatment-detail", kwargs={"pk": treatment.pk}))
        self.assertEqual(response.status_code, 200)
        tp = response.context["products"][0] if "products" in response.context else treatment.treatmentproduct_set.get()
        self.assertAlmostEqual(float(tp.total_dose), exp['total_dose'], places=3)
        self.assertAlmostEqual(float(tp.dose), exp['dose'], places=3)
        self.assertEqual(tp.total_dose_unit, exp['total_dose_unit'])
        self.assertAlmostEqual(float(tp.total_price), exp['total_price'], places=2)
        self.assertAlmostEqual(float(tp.price_per_ha), exp['price_per_ha'], places=2)
        self.assertAlmostEqual(float(response.context["total_cost"]), exp['total_price'], places=2)
        self.assertEqual(response.context["load_info"], exp['loads'])
        self.assertAlmostEqual(float(tp.get_dose_per_load()), exp['dose_per_load'], places=3)

    def test_case_b_kg_per_1000l(self):
        self._assert_detail_matches(*self._post_case("B"))

    def test_case_d_percentage(self):
        self._assert_detail_matches(*self._post_case("D"))

    def test_case_h_manual_total(self):
        treatment, exp = self._post_case("H")
        self.assertTrue(treatment.treatmentproduct_set.get().total_overridden)
        self._assert_detail_matches(treatment, exp)

    def test_three_fields_create_three_treatments_each_with_its_own_amounts(self):
        inp = CASES["B"]['input']
        fields = [Field.objects.create(name=n, area=a, crop="Olivo", planting_year=2020, organization=self.org)
                  for n, a in (("P1", 4.2), ("P2", 2.8), ("P3", 6.5))]
        machine = Machine.objects.create(name="Cuba", type="Pulverizador", capacity=2000, organization=self.org)
        product = Product.objects.create(name="Fungicida", product_type=self.ptype, price=Decimal("9.50"),
                                         spraying_dose=Decimal("3"), spraying_dose_type="kg_per_1000l",
                                         organization=self.org)
        data = {
            "name": "Tres parcelas", "type": "spraying", "date": date.today().isoformat(),
            "field": str(fields[0].pk), "extra_fields": [str(f.pk) for f in fields[1:]],
            "machine": str(machine.pk), "water_per_ha": str(inp['water_per_ha']), "finish_date": "",
        }
        data.update(formset_data([{"product": product.pk, "dose": "3.000", "total_dose": "",
                                   "total_overridden": "false"}]))
        response = self.client.post(self.create_url, data)
        self.assertEqual(response.status_code, 302)
        created = Treatment.objects.filter(name="Tres parcelas").order_by("field__name")
        self.assertEqual(created.count(), 3)
        expected_total = {"P1": 12.6, "P2": 8.4, "P3": 19.5}      # área × 1000 L/ha × 3 kg / 1000 L
        expected_cost = {"P1": 119.70, "P2": 79.80, "P3": 185.25}
        for t in created:
            tp = t.treatmentproduct_set.get()
            self.assertAlmostEqual(float(tp.total_dose), expected_total[t.field.name], places=3)
            self.assertAlmostEqual(float(tp.total_price), expected_cost[t.field.name], places=2)
            detail = self.client.get(reverse("treatment-detail", kwargs={"pk": t.pk}))
            self.assertAlmostEqual(float(detail.context["total_cost"]), expected_cost[t.field.name], places=2)

    def test_fertigation_total_rounded_to_the_container_shows_exactly_25_l_in_detail(self):
        """A2: la dosis da 23,94 L y el usuario pone 25 L (envase de 25 L): el detalle muestra 25 L, no 23,94."""
        field = Field.objects.create(name="Parcela 4,2", area=4.2, crop="Olivo", planting_year=2020, organization=self.org)
        product = Product.objects.create(name="Ácidos", product_type=self.ptype, price=Decimal("4.00"),
                                         fertigation_dose=Decimal("5.7"), fertigation_dose_type="l_per_ha",
                                         organization=self.org)
        data = {"name": "Ferti 25 L", "type": "fertigation", "date": date.today().isoformat(),
                "field": str(field.pk), "machine": "", "water_per_ha": "0", "finish_date": ""}
        # Lo que escribe el controlador al teclear 25 en el total: dosis derivada (25 / 4,2) y total exacto
        data.update(formset_data([{"product": product.pk, "dose": "5.9524", "total_dose": "25.0000",
                                   "total_overridden": "true"}]))
        self.assertEqual(self.client.post(self.create_url, data).status_code, 302)
        t = Treatment.objects.get(name="Ferti 25 L")
        tp = t.treatmentproduct_set.get()
        self.assertEqual(tp.total_dose, Decimal("25.0000"))
        self.assertTrue(tp.total_overridden)
        self.assertEqual(tp.total_price, Decimal("100.00"))
        detail = self.client.get(reverse("treatment-detail", kwargs={"pk": t.pk}))
        self.assertContains(detail, "25 L")
        self.assertNotContains(detail, "23,94")
