"""
Fase 1 del plan del formulario de tratamiento: errores E1-E7, D1, mojado real,
varias parcelas al crear y datos del formulario sin fetch.
"""
from datetime import date, timedelta
from decimal import Decimal
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse

from accounts.models import Notification, Organization
from farm.models import Field, Machine, ProductType, Product, Treatment, TreatmentProduct
from farm.tests.form_helpers import formset_data

User = get_user_model()


class BackendBase(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Org Backend")
        self.other_org = Organization.objects.create(name="Org Ajena")
        self.user = User.objects.create_user(
            username="back", email="back@example.com", password="pass123", organization=self.org,
        )
        self.client.force_login(self.user)

        self.field = Field.objects.create(name="Parcela A", area=4.2, crop="Olivo", planting_year=2020,
                                          organization=self.org)
        self.field_b = Field.objects.create(name="Parcela B", area=2.8, crop="Almendro", planting_year=2020,
                                            organization=self.org)
        self.field_c = Field.objects.create(name="Parcela C", area=6.5, crop="Olivo", planting_year=2020,
                                            organization=self.org)
        self.machine = Machine.objects.create(name="Cuba 2000", type="Pulverizador", capacity=2000,
                                              organization=self.org)
        self.ptype = ProductType.objects.create(name="Fito", organization=self.org)
        self.kgha = Product.objects.create(
            name="Abono kg/ha", product_type=self.ptype, price=Decimal("10.00"),
            spraying_dose=Decimal("3"), spraying_dose_type="kg_per_ha", organization=self.org)
        self.l1000 = Product.objects.create(
            name="Fungicida L/1000L", product_type=self.ptype, price=Decimal("10.00"),
            spraying_dose=Decimal("1"), spraying_dose_type="l_per_1000l", organization=self.org)
        self.lha = Product.objects.create(
            name="Foliar L/ha", product_type=self.ptype, price=Decimal("5.00"),
            spraying_dose=Decimal("2"), spraying_dose_type="l_per_ha",
            fertigation_dose=Decimal("10"), fertigation_dose_type="l_per_ha", organization=self.org)
        self.spray_only = Product.objects.create(
            name="Solo pulverizar", product_type=self.ptype, price=Decimal("5.00"),
            spraying_dose=Decimal("1"), spraying_dose_type="l_per_1000l", organization=self.org)

        # Datos de otra organización
        self.o_field = Field.objects.create(name="Ajena", area=3.0, crop="Olivo", planting_year=2020,
                                            organization=self.other_org)
        self.o_machine = Machine.objects.create(name="Cuba ajena", type="Pulverizador", capacity=1000,
                                                organization=self.other_org)
        o_type = ProductType.objects.create(name="Fito ajeno", organization=self.other_org)
        self.o_product = Product.objects.create(
            name="Producto ajeno", product_type=o_type, price=Decimal("1.00"),
            spraying_dose=Decimal("1"), spraying_dose_type="l_per_ha", organization=self.other_org)

        self.create_url = reverse("treatment-create")

    def base(self, **overrides):
        data = {
            "name": "Caso backend",
            "type": "spraying",
            "date": (date.today() + timedelta(days=2)).isoformat(),
            "field": str(self.field.pk),
            "machine": str(self.machine.pk),
            "water_per_ha": "1000",
            "finish_date": "",
        }
        data.update(overrides)
        return data

    def post_create(self, lines, **overrides):
        data = self.base(**overrides)
        data.update(formset_data(lines))
        return self.client.post(self.create_url, data)

    def edit_url(self, treatment):
        return reverse("treatment-edit", kwargs={"pk": treatment.pk})


# ── E1 / E2: total a mano ─────────────────────────────────────────────────────

@pytest.mark.django_db
class TotalOverriddenTests(BackendBase):

    def test_create_keeps_manual_total(self):
        """E1 + E2: el total a mano llega por el formulario y se guarda exacto."""
        response = self.post_create([{"product": self.kgha.pk, "dose": "1", "total_dose": "10",
                                      "total_overridden": "true"}])
        self.assertEqual(response.status_code, 302)
        tp = TreatmentProduct.objects.get(treatment__name="Caso backend")
        self.assertTrue(tp.total_overridden)
        self.assertEqual(tp.total_dose, Decimal("10.0000"))
        self.assertEqual(tp.dose, Decimal("2.3810"))
        self.assertEqual(tp.total_price, Decimal("100.00"))

    def test_edit_keeps_manual_total(self):
        self.post_create([{"product": self.l1000.pk, "dose": "1", "total_dose": "5", "total_overridden": "true"}])
        treatment = Treatment.objects.get(name="Caso backend")
        tp = treatment.treatmentproduct_set.get()
        data = self.base(name="Renombrado")
        data.update(formset_data([{"id": tp.pk, "product": self.l1000.pk, "dose": "1.19", "total_dose": "5.00",
                                   "total_overridden": "true"}], initial=1))
        response = self.client.post(self.edit_url(treatment), data)
        self.assertEqual(response.status_code, 302)
        tp.refresh_from_db()
        self.assertTrue(tp.total_overridden)
        self.assertEqual(tp.total_dose, Decimal("5.0000"))

    def test_removing_manual_total_recalculates_from_dose(self):
        self.post_create([{"product": self.kgha.pk, "dose": "1", "total_dose": "10", "total_overridden": "true"}])
        treatment = Treatment.objects.get(name="Caso backend")
        tp = treatment.treatmentproduct_set.get()
        data = self.base()
        data.update(formset_data([{"id": tp.pk, "product": self.kgha.pk, "dose": "3", "total_dose": "10",
                                   "total_overridden": "false"}], initial=1))
        response = self.client.post(self.edit_url(treatment), data)
        self.assertEqual(response.status_code, 302)
        tp.refresh_from_db()
        self.assertFalse(tp.total_overridden)
        self.assertEqual(tp.total_dose, Decimal("12.6000"))

    def test_manual_total_must_be_positive(self):
        for bad in ("", "0"):
            response = self.post_create([{"product": self.kgha.pk, "dose": "1", "total_dose": bad,
                                          "total_overridden": "true"}])
            self.assertEqual(response.status_code, 200, bad)
            self.assertIn("total_dose", response.context["products_formset"].forms[0].errors, bad)
        self.assertFalse(Treatment.objects.filter(name="Caso backend").exists())

    def test_total_is_optional_when_not_overridden(self):
        """El backend es la fuente de verdad: si no hay total a mano, recalcula."""
        response = self.post_create([{"product": self.kgha.pk, "dose": "3", "total_dose": "",
                                      "total_overridden": "false"}])
        self.assertEqual(response.status_code, 302)
        tp = TreatmentProduct.objects.get(treatment__name="Caso backend")
        self.assertEqual(tp.total_dose, Decimal("12.6000"))

    def test_model_new_line_with_manual_total_is_kept(self):
        """E2 a nivel de modelo."""
        treatment = Treatment.objects.create(
            organization=self.org, field=self.field, machine=self.machine, name="M", type="spraying",
            date=date.today(), water_per_ha=1000)
        tp = TreatmentProduct.objects.create(
            organization=self.org, treatment=treatment, product=self.kgha, dose=Decimal("1"),
            total_dose=Decimal("10"), total_overridden=True)
        tp.refresh_from_db()
        self.assertEqual(tp.total_dose, Decimal("10.0000"))
        self.assertEqual(tp.dose, Decimal("2.3810"))


# ── D1: el total a mano gana al mojado real ───────────────────────────────────

@pytest.mark.django_db
class ManualTotalVsRealWaterTests(BackendBase):

    def _treatment_with_manual_total(self):
        treatment = Treatment.objects.create(
            organization=self.org, field=self.field, machine=self.machine, name="D1", type="spraying",
            date=date.today() - timedelta(days=2), water_per_ha=1000)
        tp = TreatmentProduct.objects.create(
            organization=self.org, treatment=treatment, product=self.l1000, dose=Decimal("1"),
            total_dose=Decimal("0"))
        # El usuario pone el total a mano (L/1000L, 4,2 ha, 1000 L/ha: dosis derivada 1,1905)
        tp.total_dose = Decimal("5")
        tp.total_overridden = True
        tp.save()
        tp.refresh_from_db()
        self.assertEqual(tp.total_dose, Decimal("5.0000"))
        return treatment, tp

    def test_manual_total_survives_real_water_different_from_planned(self):
        treatment, tp = self._treatment_with_manual_total()
        treatment.finish_treatment(date.today(), 1100)
        tp.refresh_from_db()
        self.assertEqual(tp.total_dose, Decimal("5.0000"))
        self.assertTrue(tp.total_overridden)
        # La dosis se deriva del total con el mojado real: 5 * 1000 / (4,2 * 1100)
        self.assertEqual(tp.dose, Decimal("1.0823"))
        self.assertEqual(tp.total_price, Decimal("50.00"))

    def test_without_manual_total_real_water_still_recalculates(self):
        treatment = Treatment.objects.create(
            organization=self.org, field=self.field, machine=self.machine, name="D1b", type="spraying",
            date=date.today() - timedelta(days=2), water_per_ha=1000)
        tp = TreatmentProduct.objects.create(
            organization=self.org, treatment=treatment, product=self.l1000, dose=Decimal("1"),
            total_dose=Decimal("0"))
        treatment.finish_treatment(date.today(), 1100)
        tp.refresh_from_db()
        self.assertEqual(tp.total_dose, Decimal("4.6200"))


# ── E6: aislamiento por organización ──────────────────────────────────────────

@pytest.mark.django_db
class OrganizationIsolationTests(BackendBase):

    def test_field_from_other_org_is_rejected(self):
        response = self.post_create([{"product": self.kgha.pk, "dose": "3", "total_dose": "9"}],
                                    field=str(self.o_field.pk))
        self.assertEqual(response.status_code, 200)
        self.assertIn("field", response.context["form"].errors)
        self.assertFalse(Treatment.objects.filter(name="Caso backend").exists())

    def test_machine_from_other_org_is_rejected(self):
        response = self.post_create([{"product": self.kgha.pk, "dose": "3", "total_dose": "9"}],
                                    machine=str(self.o_machine.pk))
        self.assertEqual(response.status_code, 200)
        self.assertIn("machine", response.context["form"].errors)

    def test_product_from_other_org_is_rejected(self):
        response = self.post_create([{"product": self.o_product.pk, "dose": "3", "total_dose": "9"}])
        self.assertEqual(response.status_code, 200)
        self.assertIn("product", response.context["products_formset"].forms[0].errors)
        self.assertFalse(Treatment.objects.filter(name="Caso backend").exists())

    def test_extra_field_from_other_org_is_rejected(self):
        data = self.base()
        data.update(formset_data([{"product": self.kgha.pk, "dose": "3", "total_dose": "9"}]))
        data["extra_fields"] = [str(self.field_b.pk), str(self.o_field.pk)]
        response = self.client.post(self.create_url, data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("extra_fields", response.context["form"].errors)


# ── E7 y mojado real ──────────────────────────────────────────────────────────

@pytest.mark.django_db
class FinishDateAndRealWaterTests(BackendBase):
    LINE = {"product": None, "dose": "3", "total_dose": "12.6"}

    def line(self):
        return [{**self.LINE, "product": self.kgha.pk}]

    def test_future_finish_date_is_rejected(self):
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        response = self.post_create(self.line(), finish_date=tomorrow)
        self.assertEqual(response.status_code, 200)
        self.assertIn("finish_date", response.context["form"].errors)
        self.assertFalse(Treatment.objects.filter(name="Caso backend").exists())

    def test_today_finish_date_is_accepted(self):
        response = self.post_create(self.line(), finish_date=date.today().isoformat(),
                                    date=date.today().isoformat())
        self.assertEqual(response.status_code, 302)

    def test_real_water_is_saved_and_used_for_totals(self):
        response = self.post_create(self.line(), finish_date=date.today().isoformat(),
                                    date=date.today().isoformat(), real_water_per_ha="1100")
        self.assertEqual(response.status_code, 302)
        t = Treatment.objects.get(name="Caso backend")
        self.assertEqual(t.real_water_per_ha, 1100)
        self.assertEqual(t.status, "completed")

    def test_real_water_without_finish_date_is_ignored(self):
        response = self.post_create(self.line(), real_water_per_ha="1100")
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(Treatment.objects.get(name="Caso backend").real_water_per_ha)

    def test_real_water_must_be_positive_when_finished(self):
        response = self.post_create(self.line(), finish_date=date.today().isoformat(),
                                    date=date.today().isoformat(), real_water_per_ha="0")
        self.assertEqual(response.status_code, 200)
        self.assertIn("real_water_per_ha", response.context["form"].errors)

    def test_real_water_is_ignored_in_fertigation(self):
        response = self.post_create(
            [{"product": self.lha.pk, "dose": "10", "total_dose": "42"}], type="fertigation", machine="",
            water_per_ha="", finish_date=date.today().isoformat(), date=date.today().isoformat(),
            real_water_per_ha="900")
        self.assertEqual(response.status_code, 302)
        t = Treatment.objects.get(name="Caso backend")
        self.assertEqual(t.real_water_per_ha, 0)
        self.assertEqual(t.water_per_ha, 0)


# ── E5: ?field= ───────────────────────────────────────────────────────────────

@pytest.mark.django_db
class PresetFieldTests(BackendBase):

    def test_field_param_preselects_field(self):
        response = self.client.get(self.create_url, {"field": self.field_b.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(str(response.context["form"]["field"].value()), str(self.field_b.pk))

    def test_field_param_of_other_org_is_ignored(self):
        response = self.client.get(self.create_url, {"field": self.o_field.pk})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["form"]["field"].value())

    def test_invalid_field_param_is_ignored(self):
        response = self.client.get(self.create_url, {"field": "abc"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["form"]["field"].value())

    def test_field_param_is_ignored_when_editing(self):
        treatment = Treatment.objects.create(
            organization=self.org, field=self.field, machine=self.machine, name="X", type="spraying",
            date=date.today(), water_per_ha=1000)
        TreatmentProduct.objects.create(organization=self.org, treatment=treatment, product=self.kgha,
                                        dose=Decimal("3"), total_dose=Decimal("0"))
        response = self.client.get(self.edit_url(treatment), {"field": self.field_b.pk})
        self.assertEqual(str(response.context["form"]["field"].value()), str(self.field.pk))


# ── Productos sin dosis para el tipo ──────────────────────────────────────────

@pytest.mark.django_db
class ProductSupportsTypeTests(BackendBase):

    def test_product_without_dose_for_type_is_rejected(self):
        response = self.post_create(
            [{"product": self.spray_only.pk, "dose": "1", "total_dose": "4.2"}],
            type="fertigation", machine="", water_per_ha="")
        self.assertEqual(response.status_code, 200)
        self.assertIn("product", response.context["products_formset"].forms[0].errors)
        self.assertFalse(Treatment.objects.filter(name="Caso backend").exists())


# ── Varias parcelas al crear ──────────────────────────────────────────────────

@pytest.mark.django_db
class MultiFieldCreateTests(BackendBase):

    def post_multi(self, lines=None, extra=None, **overrides):
        data = self.base(**overrides)
        data.update(formset_data(lines or [{"product": self.lha.pk, "dose": "2", "total_dose": "8.4"}]))
        data["extra_fields"] = [str(f.pk) for f in (extra if extra is not None else [self.field_b, self.field_c])]
        return self.client.post(self.create_url, data)

    def created_notifications(self):
        return Notification.objects.filter(event_type=Notification.EVENT_TREATMENT_CREATED)

    def test_three_fields_create_three_treatments_with_own_totals(self):
        response = self.post_multi()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("treatment-list"))

        treatments = Treatment.objects.filter(name="Caso backend").order_by("field__name")
        self.assertEqual([t.field_id for t in treatments], [self.field.pk, self.field_b.pk, self.field_c.pk])
        totals = {t.field_id: t.treatmentproduct_set.get().total_dose for t in treatments}
        self.assertEqual(totals[self.field.pk], Decimal("8.4000"))   # 2 L/ha x 4,2 ha
        self.assertEqual(totals[self.field_b.pk], Decimal("5.6000"))  # x 2,8 ha
        self.assertEqual(totals[self.field_c.pk], Decimal("13.0000"))  # x 6,5 ha
        for t in treatments:
            self.assertEqual(t.machine_id, self.machine.pk)
            self.assertEqual(t.water_per_ha, 1000)
            self.assertEqual(t.date, date.today() + timedelta(days=2))
            tp = t.treatmentproduct_set.get()
            self.assertEqual(tp.position, 0)
            self.assertFalse(tp.total_overridden)

    def test_only_one_notification(self):
        self.post_multi()
        notifications = self.created_notifications()
        self.assertEqual(notifications.count(), 1)
        self.assertIn("3 parcelas", notifications.get().title)

    def test_single_field_notification_unchanged(self):
        self.post_create([{"product": self.lha.pk, "dose": "2", "total_dose": "8.4"}])
        notifications = self.created_notifications()
        self.assertEqual(notifications.count(), 1)
        self.assertIn("Nuevo tratamiento: Caso backend", notifications.get().title)

    def test_message_reports_number_of_treatments(self):
        response = self.post_multi()
        texts = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertTrue(any("3 tratamientos creados" in t for t in texts), texts)

    def test_extra_fields_equal_to_main_field_are_ignored(self):
        response = self.post_multi(extra=[self.field, self.field_b])
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Treatment.objects.filter(name="Caso backend").count(), 2)

    def test_one_field_redirects_to_detail(self):
        response = self.post_multi(extra=[])
        t = Treatment.objects.get(name="Caso backend")
        self.assertEqual(response.url, reverse("treatment-detail", kwargs={"pk": t.pk}))

    def test_applied_area_is_forbidden_with_several_fields(self):
        response = self.post_multi(applied_area="1.5")
        self.assertEqual(response.status_code, 200)
        self.assertIn("applied_area", response.context["form"].errors)
        self.assertFalse(Treatment.objects.filter(name="Caso backend").exists())

    def test_zone_notes_is_forbidden_with_several_fields(self):
        response = self.post_multi(zone_notes="sector norte")
        self.assertEqual(response.status_code, 200)
        self.assertIn("zone_notes", response.context["form"].errors)

    def test_manual_total_is_forbidden_with_several_fields(self):
        response = self.post_multi(lines=[{"product": self.lha.pk, "dose": "2", "total_dose": "8",
                                           "total_overridden": "true"}])
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["products_formset"].non_form_errors()
                        or any(f.errors for f in response.context["products_formset"].forms))
        self.assertFalse(Treatment.objects.filter(name="Caso backend").exists())

    def test_all_or_nothing(self):
        original_save = TreatmentProduct.save
        calls = {"n": 0}

        def flaky_save(instance, *args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("fallo simulado en la segunda parcela")
            return original_save(instance, *args, **kwargs)

        with mock.patch.object(TreatmentProduct, "save", autospec=True, side_effect=flaky_save):
            with self.assertRaises(RuntimeError):
                self.post_multi()
        self.assertFalse(Treatment.objects.filter(name="Caso backend").exists())
        self.assertEqual(self.created_notifications().count(), 0)

    def test_extra_fields_are_not_accepted_when_editing(self):
        self.post_create([{"product": self.lha.pk, "dose": "2", "total_dose": "8.4"}])
        treatment = Treatment.objects.get(name="Caso backend")
        tp = treatment.treatmentproduct_set.get()
        data = self.base()
        data.update(formset_data([{"id": tp.pk, "product": self.lha.pk, "dose": "2", "total_dose": "8.4"}], initial=1))
        data["extra_fields"] = [str(self.field_b.pk)]
        response = self.client.post(self.edit_url(treatment), data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Treatment.objects.filter(name="Caso backend").count(), 1)


# ── Datos del formulario sin fetch ────────────────────────────────────────────

@pytest.mark.django_db
class FormDataTests(BackendBase):

    def test_form_data_is_in_context_and_rendered_as_json_script(self):
        response = self.client.get(self.create_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="treatment-form-data"')
        data = response.context["form_data"]
        self.assertEqual({f["id"] for f in data["fields"]}, {self.field.pk, self.field_b.pk, self.field_c.pk})
        self.assertEqual({m["id"] for m in data["machines"]}, {self.machine.pk})
        self.assertNotIn("lines", data)

    def test_fields_carry_area_crop_and_last_treatment_date(self):
        last = date.today() - timedelta(days=12)
        Treatment.objects.create(organization=self.org, field=self.field, machine=self.machine, name="Antiguo",
                                 type="spraying", date=last - timedelta(days=30), water_per_ha=1000)
        Treatment.objects.create(organization=self.org, field=self.field, machine=self.machine, name="Reciente",
                                 type="spraying", date=last, water_per_ha=1000)
        data = self.client.get(self.create_url).context["form_data"]
        by_id = {f["id"]: f for f in data["fields"]}
        self.assertEqual(by_id[self.field.pk]["area"], 4.2)
        self.assertEqual(by_id[self.field.pk]["crop"], "Olivo")
        self.assertEqual(by_id[self.field.pk]["last_treatment_date"], last.isoformat())
        self.assertIsNone(by_id[self.field_b.pk]["last_treatment_date"])

    def test_products_only_active_with_both_doses_and_recent_flag(self):
        inactive = Product.objects.create(
            name="Archivado", product_type=self.ptype, price=Decimal("1"), spraying_dose=Decimal("1"),
            spraying_dose_type="l_per_ha", is_active=False, organization=self.org)
        # lha se ha usado hace 10 días; l1000 hace 200
        t_recent = Treatment.objects.create(organization=self.org, field=self.field, machine=self.machine,
                                            name="R", type="spraying", date=date.today() - timedelta(days=10),
                                            water_per_ha=1000)
        TreatmentProduct.objects.create(organization=self.org, treatment=t_recent, product=self.lha,
                                        dose=Decimal("2"), total_dose=Decimal("0"))
        t_old = Treatment.objects.create(organization=self.org, field=self.field, machine=self.machine,
                                         name="O", type="spraying", date=date.today() - timedelta(days=200),
                                         water_per_ha=1000)
        TreatmentProduct.objects.create(organization=self.org, treatment=t_old, product=self.l1000,
                                        dose=Decimal("1"), total_dose=Decimal("0"))

        data = self.client.get(self.create_url).context["form_data"]
        by_id = {p["id"]: p for p in data["products"]}
        self.assertNotIn(inactive.pk, by_id)
        self.assertNotIn(self.o_product.pk, by_id)
        lha = by_id[self.lha.pk]
        self.assertEqual(lha["spraying"], {"dose": 2.0, "dose_type": "l_per_ha", "label": "L/ha"})
        self.assertEqual(lha["fertigation"], {"dose": 10.0, "dose_type": "l_per_ha", "label": "L/ha"})
        self.assertIsNone(by_id[self.spray_only.pk]["fertigation"])
        self.assertEqual(lha["price"], 5.0)
        self.assertEqual(lha["type_name"], "Fito")
        self.assertTrue(lha["recent"])
        self.assertFalse(by_id[self.l1000.pk]["recent"])

    def test_edit_includes_saved_lines(self):
        self.post_create([
            {"product": self.kgha.pk, "dose": "1", "total_dose": "10", "total_overridden": "true"},
            {"product": self.l1000.pk, "dose": "1", "total_dose": "4.2"},
        ])
        treatment = Treatment.objects.get(name="Caso backend")
        response = self.client.get(self.edit_url(treatment))
        lines = response.context["form_data"]["lines"]
        self.assertEqual([l["product_id"] for l in lines], [self.kgha.pk, self.l1000.pk])
        self.assertEqual([l["position"] for l in lines], [0, 1])
        self.assertTrue(lines[0]["total_overridden"])
        self.assertEqual(lines[0]["total_dose"], 10.0)
        self.assertEqual(lines[0]["dose"], 2.381)
        self.assertEqual(lines[0]["unit_price"], 10.0)

    def test_json_script_is_escaped(self):
        Field.objects.create(name="</script><b>x", area=1.0, crop="Olivo", planting_year=2020,
                             organization=self.org)
        html = self.client.get(self.create_url).content.decode()
        self.assertNotIn("</script><b>x", html)
