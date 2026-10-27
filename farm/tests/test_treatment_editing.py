from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import Organization
from farm.models import Field, Machine, ProductType, Product, Treatment, TreatmentProduct

User = get_user_model()


@pytest.mark.django_db
class TreatmentEditViewTest(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="Org Edit Test")
        self.user = User.objects.create_user(
            username="editor",
            email="editor@example.com",
            password="pass123",
            organization=self.organization,
        )
        self.client.force_login(self.user)

        self.field = Field.objects.create(
            name="Parcela A",
            area=10.0,
            crop="Olivo",
            planting_year=2020,
            organization=self.organization,
        )
        self.machine = Machine.objects.create(
            name="Pulverizador 1000",
            type="Pulverizador",
            capacity=1000,
            organization=self.organization,
        )
        self.product_type = ProductType.objects.create(
            name="Fitosanitario",
            organization=self.organization,
        )

        self.product_1 = Product.objects.create(
            name="Producto 1",
            product_type=self.product_type,
            spraying_dose=Decimal("1.00"),
            spraying_dose_type="l_per_ha",
            price=Decimal("20.00"),
            organization=self.organization,
        )
        self.product_2 = Product.objects.create(
            name="Producto 2",
            product_type=self.product_type,
            spraying_dose=Decimal("1.00"),
            spraying_dose_type="l_per_ha",
            price=Decimal("30.00"),
            organization=self.organization,
        )
        self.product_3 = Product.objects.create(
            name="Producto 3",
            product_type=self.product_type,
            spraying_dose=Decimal("1.00"),
            spraying_dose_type="l_per_ha",
            price=Decimal("15.00"),
            organization=self.organization,
        )

        self.treatment = Treatment.objects.create(
            name="Tratamiento base",
            type="spraying",
            date=date.today() + timedelta(days=1),
            field=self.field,
            machine=self.machine,
            water_per_ha=1000,
            organization=self.organization,
        )

        self.tp_1 = TreatmentProduct.objects.create(
            treatment=self.treatment,
            product=self.product_1,
            dose=Decimal("2.00"),
            total_dose=Decimal("20.00"),
            dose_type="l_per_ha",
            total_dose_unit="L",
            unit_price=Decimal("20.00"),
            organization=self.organization,
        )
        self.tp_2 = TreatmentProduct.objects.create(
            treatment=self.treatment,
            product=self.product_2,
            dose=Decimal("1.00"),
            total_dose=Decimal("10.00"),
            dose_type="l_per_ha",
            total_dose_unit="L",
            unit_price=Decimal("30.00"),
            organization=self.organization,
        )

    def test_edit_page_is_available(self):
        response = self.client.get(reverse("treatment-edit", kwargs={"pk": self.treatment.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Editar tratamiento")
        self.assertContains(response, "Producto 1")
        self.assertContains(response, f'value="{self.treatment.date.isoformat()}"', html=False)
        self.assertContains(response, 'value="20.00"', html=False)
        self.assertContains(response, 'value="10.00"', html=False)

    def test_edit_treatment_updates_name_and_products(self):
        response = self.client.post(
            reverse("treatment-edit", kwargs={"pk": self.treatment.pk}),
            {
                "name": "Tratamiento editado",
                "type": "spraying",
                "date": self.treatment.date.isoformat(),
                "field": str(self.field.pk),
                "machine": str(self.machine.pk),
                "water_per_ha": "1000",
                "finish_date": "",
                "treatmentproduct_set-TOTAL_FORMS": "3",
                "treatmentproduct_set-INITIAL_FORMS": "2",
                "treatmentproduct_set-MIN_NUM_FORMS": "1",
                "treatmentproduct_set-MAX_NUM_FORMS": "1000",
                "treatmentproduct_set-0-id": str(self.tp_1.pk),
                "treatmentproduct_set-0-product": str(self.product_1.pk),
                "treatmentproduct_set-0-dose": "3.00",
                "treatmentproduct_set-0-total_dose": "30.00",
                "treatmentproduct_set-0-DELETE": "",
                "treatmentproduct_set-1-id": str(self.tp_2.pk),
                "treatmentproduct_set-1-product": str(self.product_2.pk),
                "treatmentproduct_set-1-dose": "1.00",
                "treatmentproduct_set-1-total_dose": "10.00",
                "treatmentproduct_set-1-DELETE": "on",
                "treatmentproduct_set-2-id": "",
                "treatmentproduct_set-2-product": str(self.product_3.pk),
                "treatmentproduct_set-2-dose": "0.50",
                "treatmentproduct_set-2-total_dose": "5.00",
                "treatmentproduct_set-2-DELETE": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("treatment-detail", kwargs={"pk": self.treatment.pk}))

        self.treatment.refresh_from_db()
        self.assertEqual(self.treatment.name, "Tratamiento editado")

        current_products = set(
            TreatmentProduct.objects.filter(treatment=self.treatment).values_list("product_id", flat=True)
        )
        self.assertEqual(current_products, {self.product_1.pk, self.product_3.pk})

        updated_tp_1 = TreatmentProduct.objects.get(treatment=self.treatment, product=self.product_1)
        self.assertEqual(updated_tp_1.dose, Decimal("3.00"))



def _formset_data(lines, initial=0):
    """
    Construye el bloque del formset de productos.
    lines: lista de dicts {product, dose, total_dose, id?, delete?, total_overridden?}
    """
    data = {
        "treatmentproduct_set-TOTAL_FORMS": str(len(lines)),
        "treatmentproduct_set-INITIAL_FORMS": str(initial),
        "treatmentproduct_set-MIN_NUM_FORMS": "1",
        "treatmentproduct_set-MAX_NUM_FORMS": "1000",
    }
    for i, line in enumerate(lines):
        prefix = f"treatmentproduct_set-{i}-"
        data[prefix + "id"] = str(line.get("id", ""))
        data[prefix + "product"] = str(line["product"])
        data[prefix + "dose"] = line["dose"]
        data[prefix + "total_dose"] = line.get("total_dose", "")
        data[prefix + "DELETE"] = "on" if line.get("delete") else ""
        if "total_overridden" in line:
            data[prefix + "total_overridden"] = line["total_overridden"]
    return data


@pytest.mark.django_db
class TreatmentFormCharacterizationTest(TestCase):
    """
    Caracterización del formulario de crear/editar: POST que tienen que seguir
    funcionando pase lo que pase con la interfaz (plan, sección 2.2).
    """

    def setUp(self):
        self.organization = Organization.objects.create(name="Org Caracterización")
        self.user = User.objects.create_user(
            username="carac", email="carac@example.com", password="pass123",
            organization=self.organization,
        )
        self.client.force_login(self.user)
        self.field = Field.objects.create(
            name="Parcela 4,2", area=4.2, crop="Olivo", planting_year=2020, organization=self.organization,
        )
        self.machine = Machine.objects.create(
            name="Cuba 2000", type="Pulverizador", capacity=2000, organization=self.organization,
        )
        ptype = ProductType.objects.create(name="Fitosanitario", organization=self.organization)
        self.spray_product = Product.objects.create(
            name="Fungicida", product_type=ptype, price=Decimal("9.50"),
            spraying_dose=Decimal("3"), spraying_dose_type="kg_per_1000l",
            organization=self.organization,
        )
        self.other_spray_product = Product.objects.create(
            name="Insecticida", product_type=ptype, price=Decimal("10.00"),
            spraying_dose=Decimal("0.5"), spraying_dose_type="l_per_1000l",
            organization=self.organization,
        )
        self.ferti_product = Product.objects.create(
            name="Abono", product_type=ptype, price=Decimal("10.00"),
            fertigation_dose=Decimal("10"), fertigation_dose_type="l_per_ha",
            organization=self.organization,
        )
        self.create_url = reverse("treatment-create")

    def _base(self, **overrides):
        data = {
            "name": "Tratamiento caso",
            "type": "spraying",
            "date": (date.today() + timedelta(days=2)).isoformat(),
            "field": str(self.field.pk),
            "machine": str(self.machine.pk),
            "water_per_ha": "1000",
            "finish_date": "",
        }
        data.update(overrides)
        return data

    def test_create_spraying_complete(self):
        data = self._base()
        data.update(_formset_data([{"product": self.spray_product.pk, "dose": "3", "total_dose": "12.60"}]))
        response = self.client.post(self.create_url, data)

        self.assertEqual(response.status_code, 302)
        treatment = Treatment.objects.get(name="Tratamiento caso")
        self.assertEqual(response.url, reverse("treatment-detail", kwargs={"pk": treatment.pk}))
        tp = treatment.treatmentproduct_set.get()
        self.assertEqual(tp.total_dose, Decimal("12.6000"))
        self.assertEqual(tp.total_dose_unit, "kg")
        self.assertEqual(tp.total_price, Decimal("119.70"))
        self.assertEqual(tp.price_per_ha, Decimal("28.50"))
        self.assertEqual(tp.unit_price, Decimal("9.50"))
        self.assertEqual(tp.position, 0)

    def test_create_fertigation_forces_no_machine_and_zero_water(self):
        data = self._base(type="fertigation", machine="", water_per_ha="")
        data.update(_formset_data([{"product": self.ferti_product.pk, "dose": "10", "total_dose": "42.00"}]))
        response = self.client.post(self.create_url, data)

        self.assertEqual(response.status_code, 302)
        treatment = Treatment.objects.get(name="Tratamiento caso")
        self.assertIsNone(treatment.machine)
        self.assertEqual(treatment.water_per_ha, 0)
        tp = treatment.treatmentproduct_set.get()
        self.assertEqual(tp.total_dose, Decimal("42.0000"))
        self.assertEqual(tp.total_dose_unit, "L")

    def test_applied_area_larger_than_field_is_rejected(self):
        data = self._base(applied_area="9")
        data.update(_formset_data([{"product": self.spray_product.pk, "dose": "3", "total_dose": "12.60"}]))
        response = self.client.post(self.create_url, data)

        self.assertEqual(response.status_code, 200)
        self.assertIn("applied_area", response.context["form"].errors)
        self.assertFalse(Treatment.objects.filter(name="Tratamiento caso").exists())

    def test_duplicated_product_is_rejected(self):
        data = self._base()
        data.update(_formset_data([
            {"product": self.spray_product.pk, "dose": "3", "total_dose": "12.60"},
            {"product": self.spray_product.pk, "dose": "2", "total_dose": "8.40"},
        ]))
        response = self.client.post(self.create_url, data)

        self.assertEqual(response.status_code, 200)
        errors = response.context["products_formset"].non_form_errors()
        self.assertTrue(any("duplicado" in e for e in errors))
        self.assertFalse(Treatment.objects.filter(name="Tratamiento caso").exists())

    def test_no_products_is_rejected(self):
        data = self._base()
        data.update(_formset_data([]))
        response = self.client.post(self.create_url, data)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["products_formset"].non_form_errors())
        self.assertFalse(Treatment.objects.filter(name="Tratamiento caso").exists())

    def _create_saved(self):
        data = self._base()
        data.update(_formset_data([{"product": self.spray_product.pk, "dose": "3", "total_dose": "12.60"}]))
        self.client.post(self.create_url, data)
        return Treatment.objects.get(name="Tratamiento caso")

    def test_edit_changing_water_recalculates_totals(self):
        treatment = self._create_saved()
        tp = treatment.treatmentproduct_set.get()
        data = self._base(water_per_ha="500")
        data.update(_formset_data(
            [{"id": tp.pk, "product": self.spray_product.pk, "dose": "3", "total_dose": "12.60"}], initial=1,
        ))
        response = self.client.post(reverse("treatment-edit", kwargs={"pk": treatment.pk}), data)

        self.assertEqual(response.status_code, 302)
        tp.refresh_from_db()
        # 4,2 ha x 500 L/ha = 2100 L de caldo; 3 kg/1000L -> 6,3 kg
        self.assertEqual(tp.total_dose, Decimal("6.3000"))
        self.assertEqual(tp.total_price, Decimal("59.85"))

    def test_edit_completed_keeps_frozen_unit_price(self):
        treatment = self._create_saved()
        treatment.finish_date = date.today()
        treatment.save()
        tp = treatment.treatmentproduct_set.get()
        self.assertEqual(tp.unit_price, Decimal("9.50"))

        # El producto sube de precio: no debe afectar a un tratamiento completado
        self.spray_product.price = Decimal("20.00")
        self.spray_product.save()

        data = self._base(name="Renombrado", finish_date=date.today().isoformat())
        data.update(_formset_data(
            [{"id": tp.pk, "product": self.spray_product.pk, "dose": "3", "total_dose": "12.60"}], initial=1,
        ))
        response = self.client.post(reverse("treatment-edit", kwargs={"pk": treatment.pk}), data)

        self.assertEqual(response.status_code, 302)
        tp.refresh_from_db()
        self.assertEqual(tp.unit_price, Decimal("9.50"))
        self.assertEqual(tp.total_price, Decimal("119.70"))
