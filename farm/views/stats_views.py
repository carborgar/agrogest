from datetime import date

from django.db.models import Count, Sum, Min
from django.db.models.functions import TruncMonth
from django.views.generic import TemplateView

from farm.mixins import OwnershipRequiredMixin
from farm.models import Treatment, TreatmentProduct, Field, Harvest, Expense


# Tope de PK admitido en el filtro de parcela (evita desbordar el entero de la BD)
MAX_PK = 2**31 - 1


class YearlyStatsView(OwnershipRequiredMixin, TemplateView):
    template_name = "farm/stats/yearly_stats.html"

    def _year_url(self, year):
        query = self.request.GET.copy()
        query["year"] = str(year)
        return "?" + query.urlencode()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        # ── Año seleccionado ──────────────────────────────────────────────
        current_year = date.today().year
        try:
            selected_year = int(self.request.GET.get("year", current_year))
        except (ValueError, TypeError):
            selected_year = current_year
        if not 2000 <= selected_year <= current_year + 1:
            selected_year = current_year

        # Rango de años disponibles (desde el primer tratamiento hasta hoy)
        year_range_qs = Treatment.objects.filter(
            field__organization=user.organization
        ).aggregate(min_year=Min("date"))
        min_year = year_range_qs["min_year"].year if year_range_qs["min_year"] else current_year
        available_years = set(range(max(min_year, current_year - 10), current_year + 1))
        available_years.add(selected_year)
        available_years = sorted(available_years)

        context["selected_year"] = selected_year
        context["available_years"] = available_years
        context["current_year"] = current_year

        # ── Filtros por tipo y parcelas ───────────────────────────────────
        org = user.organization
        fields_qs = Field.objects.filter(organization=org)
        
        # Obtener tipos de tratamiento y parcelas disponibles
        context["type_choices"] = Treatment.TYPE_CHOICES
        context["fields"] = fields_qs
        
        # Procesar filtros seleccionados
        valid_types = {key for key, _label in Treatment.TYPE_CHOICES}
        selected_types = [t for t in self.request.GET.getlist("type") if t in valid_types]
        selected_fields = [f for f in self.request.GET.getlist("field")
                           if f.isascii() and f.isdigit() and int(f) <= MAX_PK]
        context["selected_types"] = selected_types
        context["selected_fields"] = selected_fields

        context["panel_filter_count"] = len(selected_types) + len(selected_fields)

        # Pestañas de año: el actual y los dos anteriores (+ el elegido si es más antiguo).
        # Cada una conserva los filtros de parcela y tipo.
        tab_years = [current_year - i for i in range(3)]
        if selected_year not in tab_years:
            tab_years.append(selected_year)
        context["year_tabs"] = [
            {"label": str(y), "active": y == selected_year, "url": self._year_url(y)}
            for y in tab_years
        ]
        context["older_years"] = [y for y in available_years if y not in tab_years]
        context["clear_url"] = f"?year={selected_year}"

        # ── Base querysets ────────────────────────────────────────────────
        treatments_qs = Treatment.objects.filter(
            organization=org,
            finish_date__year=selected_year,
            status=Treatment.STATUS_COMPLETED,
        ).select_related("field", "machine")
        
        # Aplicar filtros
        if selected_types:
            treatments_qs = treatments_qs.filter(type__in=selected_types)
        if selected_fields:
            treatments_qs = treatments_qs.filter(field_id__in=selected_fields)

        treatment_products_qs = TreatmentProduct.objects.filter(
            treatment__organization=org,
            treatment__finish_date__year=selected_year,
            treatment__status=Treatment.STATUS_COMPLETED,
        ).select_related("product", "product__product_type", "treatment__field")
        
        # Aplicar filtros a treatment_products_qs
        if selected_types:
            treatment_products_qs = treatment_products_qs.filter(treatment__type__in=selected_types)
        if selected_fields:
            treatment_products_qs = treatment_products_qs.filter(treatment__field_id__in=selected_fields)

        # ── KPIs principales ──────────────────────────────────────────────
        total_treatments = treatments_qs.count()
        total_spraying = treatments_qs.filter(type="spraying").count()
        total_fertigation = treatments_qs.filter(type="fertigation").count()

        # Suma de coste de productos en tratamientos completados
        total_products_cost = treatment_products_qs.aggregate(
            total=Sum("total_price")
        )["total"] or 0

        # Área total tratada (suma de áreas de parcelas con tratamientos completados)
        treated_fields_ids = treatments_qs.values_list("field_id", flat=True).distinct()
        total_ha_treated = fields_qs.filter(pk__in=treated_fields_ids).aggregate(
            total=Sum("area")
        )["total"] or 0

        # Distintos productos usados
        distinct_products_count = treatment_products_qs.values("product_id").distinct().count()

        context["total_treatments"] = total_treatments
        context["total_spraying"] = total_spraying
        context["total_fertigation"] = total_fertigation
        context["total_products_cost"] = total_products_cost
        context["total_ha_treated"] = round(total_ha_treated, 2)
        context["distinct_products_count"] = distinct_products_count

        # ── Tratamientos por mes ──────────────────────────────────────────
        treatments_by_month_qs = (
            treatments_qs
            .annotate(month=TruncMonth("finish_date"))
            .values("month")
            .annotate(count=Count("id"))
            .order_by("month")
        )
        month_labels = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
                        "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
        monthly_data = [0] * 12
        for row in treatments_by_month_qs:
            if row["month"]:
                monthly_data[row["month"].month - 1] = row["count"]

        context["month_labels"] = month_labels
        context["monthly_data"] = monthly_data
        max_month = max(monthly_data)
        context["monthly_bars"] = [
            {"label": label, "count": count,
             # Se resalta solo si un único mes destaca; con empates no hay «el» mes más activo
             "is_max": bool(max_month) and count == max_month and monthly_data.count(max_month) == 1}
            for label, count in zip(month_labels, monthly_data)
        ]

        busiest_month_idx = monthly_data.index(max(monthly_data)) if any(monthly_data) else None
        context["busiest_month"] = month_labels[busiest_month_idx] if busiest_month_idx is not None and max(monthly_data) > 0 else None
        context["busiest_month_count"] = max(monthly_data) if any(monthly_data) else 0

        # ── Top productos más usados ──────────────────────────────────────
        top_products = (
            treatment_products_qs
            .values("product__name", "product__product_type__name")
            .annotate(
                times_used=Count("id"),
                total_cost=Sum("total_price"),
            )
            .order_by("-times_used")[:8]
        )
        context["top_products"] = list(top_products)

        # ── Uso por tipo de producto ──────────────────────────────────────
        by_product_type = (
            treatment_products_qs
            .values("product__product_type__name")
            .annotate(
                times_used=Count("id"),
                total_cost=Sum("total_price"),
            )
            .order_by("-times_used")
        )
        context["by_product_type"] = list(by_product_type)

        # ── Parcelas más activas ──────────────────────────────────────────
        most_active_fields = (
            treatments_qs
            .values("field__name")
            .annotate(
                treatments_count=Count("id"),
                total_cost=Sum("treatmentproduct__total_price"),
            )
            .order_by("-treatments_count")[:6]
        )
        context["most_active_fields"] = list(most_active_fields)

        # ── Cosechas del año ──────────────────────────────────────────────
        harvests_qs = Harvest.objects.filter(
            organization=org,
            date__year=selected_year,
        ).select_related("field")
        if selected_fields:
            harvests_qs = harvests_qs.filter(field_id__in=selected_fields)

        harvest_totals = harvests_qs.aggregate(total_kg=Sum("amount"))
        total_harvest_kg = harvest_totals["total_kg"] or 0

        # Calcular ingresos correctamente
        total_harvest_income = sum(
            h.income() for h in harvests_qs if h.income() is not None
        )

        harvests_by_field = (
            harvests_qs
            .values("field__name")
            .annotate(total_kg=Sum("amount"))
            .order_by("-total_kg")[:5]
        )

        context["total_harvest_kg"] = total_harvest_kg
        context["total_harvest_income"] = total_harvest_income
        context["harvests_by_field"] = list(harvests_by_field)
        context["harvests_without_price"] = harvests_qs.filter(sale_price_per_kg__isnull=True).count()

        # ── Gastos del año ────────────────────────────────────────────────
        expenses_qs = Expense.objects.filter(
            organization=org,
            payment_date__year=selected_year,
        )
        if selected_fields:
            expenses_qs = expenses_qs.filter(field_id__in=selected_fields)
        total_expenses = expenses_qs.aggregate(total=Sum("amount"))["total"] or 0

        expenses_by_type = (
            expenses_qs
            .values("expense_type__name")
            .annotate(total=Sum("amount"))
            .order_by("-total")[:5]
        )
        context["total_expenses"] = total_expenses
        context["expenses_by_type"] = list(expenses_by_type)

        # ── Coste total (productos + gastos) ─────────────────────────────
        total_cost_all = float(total_products_cost) + float(total_expenses)
        context["total_cost_all"] = total_cost_all

        # ── Resultado y coste por hectárea ────────────────────────────────
        # Los gastos (agua, mano de obra…) se reparten por toda la superficie, no solo por la tratada
        scope_fields = fields_qs.filter(pk__in=selected_fields) if selected_fields else fields_qs
        total_ha_farm = scope_fields.aggregate(total=Sum("area"))["total"] or 0
        context["total_ha_farm"] = round(total_ha_farm, 2)
        context["cost_per_ha"] = round(total_cost_all / total_ha_farm, 2) if total_ha_farm else None
        # Con filtro de tipo, el coste de productos va filtrado y gastos/ingresos no:
        # el resultado mezclaría ambos criterios, así que no se calcula.
        context["result"] = None if selected_types else float(total_harvest_income) - total_cost_all

        # ── Rachas / curiosidades ─────────────────────────────────────────
        # Mes sin ningún tratamiento
        months_with_activity = {row["month"].month for row in treatments_by_month_qs if row["month"]}
        quiet_months = [month_labels[i] for i in range(12) if (i + 1) not in months_with_activity]
        context["quiet_months"] = quiet_months

        # ── Coste medio por tratamiento ───────────────────────────────────
        avg_cost_per_treatment = (
            float(total_products_cost) / total_treatments
            if total_treatments > 0 else 0
        )
        context["avg_cost_per_treatment"] = round(avg_cost_per_treatment, 2)

        # ── Datos para las gráficas (Chart.js los lee con json_script) ─────
        # Solo tipos nativos (int/str): json_script serializaría los Decimal como texto.
        context["stats_charts"] = {
            "months": {
                "labels": month_labels,
                "counts": monthly_data,
                "peak": next((i for i, b in enumerate(context["monthly_bars"]) if b["is_max"]), None),
            },
            "productTypes": {
                "labels": [r["product__product_type__name"] or "Sin tipo" for r in context["by_product_type"]],
                "data": [r["times_used"] for r in context["by_product_type"]],
            },
        }

        # ── Marca nav activo ──────────────────────────────────────────────
        context["nav_stats"] = True

        return context


