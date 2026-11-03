from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import Organization
from farm.models import Field, Expense, ExpenseType

User = get_user_model()


@pytest.mark.django_db
class ExpenseModelTest(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(
            name="Test Organization"
        )
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123",
            organization=self.organization
        )
        self.field = Field.objects.create(
            name="Test Field",
            area=10.5,
            crop="Tomato",
            planting_year=2024,
            organization=self.organization
        )
        # Create an expense type for testing
        self.expense_type = ExpenseType.objects.create(
            name="Mano de obra",
            description="Labor expenses",
            organization=self.organization
        )

    def test_expense_creation(self):
        """Test creating an expense"""
        expense = Expense.objects.create(
            field=self.field,
            expense_type=self.expense_type,
            description="Manual labor for pruning",
            payment_date="2024-01-15",
            amount=Decimal("150.50"),
            organization=self.organization
        )
        
        self.assertEqual(expense.field, self.field)
        self.assertEqual(expense.expense_type, self.expense_type)
        self.assertEqual(expense.description, "Manual labor for pruning")
        self.assertEqual(expense.amount, Decimal("150.50"))
        self.assertEqual(str(expense), "Mano de obra - Test Field - 150.50€")

    def test_expense_type_creation(self):
        """Test creating an expense type"""
        expense_type = ExpenseType.objects.create(
            name="Combustible",
            description="Fuel costs",
            organization=self.organization
        )
        
        self.assertEqual(expense_type.name, "Combustible")
        self.assertEqual(expense_type.description, "Fuel costs")
        self.assertEqual(expense_type.organization, self.organization)
        self.assertEqual(str(expense_type), "Combustible")


@pytest.mark.django_db
class ExpenseViewTest(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(
            name="Test Organization"
        )
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123",
            organization=self.organization
        )
        self.field = Field.objects.create(
            name="Test Field",
            area=10.5,
            crop="Tomato",
            planting_year=2024,
            organization=self.organization
        )
        # Create an expense type for testing
        self.expense_type = ExpenseType.objects.create(
            name="Recibo de agua",
            description="Water bills",
            organization=self.organization
        )
        self.client.force_login(self.user)

    def test_expense_list_view(self):
        """Test the expense list view"""
        response = self.client.get(reverse('expense-list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Gastos")
        self.assertContains(response, "Nuevo gasto")
        self.assertContains(response, "Todavía no hay gastos")

    def test_expense_create_view(self):
        """Test the expense creation view"""
        response = self.client.get(reverse('expense-create'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Nuevo gasto")
        self.assertContains(response, 'id="expense-field-areas"')

    def test_expense_create_post(self):
        """Test creating an expense via POST"""
        data = {
            'field': self.field.id,
            'expense_type': self.expense_type.id,
            'description': 'Test expense description',
            'payment_date': '2024-01-15',
            'calculation_mode': 'total',
            'amount': '100.00'
        }
        response = self.client.post(reverse('expense-create'), data)
        self.assertEqual(response.status_code, 302)  # Redirect after successful creation
        
        # Check that expense was created
        self.assertTrue(Expense.objects.filter(description='Test expense description').exists())

    def test_expense_list_with_expenses(self):
        """Test the expense list view with existing expenses"""
        Expense.objects.create(
            field=self.field,
            expense_type=self.expense_type,
            description="Water bill payment",
            payment_date="2024-01-15",
            amount=Decimal("75.25"),
            organization=self.organization
        )
        
        response = self.client.get(reverse('expense-list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Water bill payment")
        self.assertContains(response, "75,25 €")
        self.assertContains(response, "Importe directo")

    def test_expense_type_list_view(self):
        """Test the expense type list view"""
        response = self.client.get(reverse('expense-type-list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Tipos de gasto")
        self.assertContains(response, self.expense_type.name)

    def test_expense_type_create_view(self):
        """Test the expense type creation view"""
        response = self.client.get(reverse('expense-type-create'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Nuevo tipo de gasto")

    def test_expense_type_create_post(self):
        """Test creating an expense type via POST"""
        data = {
            'name': 'Semillas',
            'description': 'Gastos en semillas'
        }
        response = self.client.post(reverse('expense-type-create'), data)
        self.assertEqual(response.status_code, 302)  # Redirect after successful creation
        
        # Check that expense type was created
        self.assertTrue(ExpenseType.objects.filter(name='Semillas').exists())

@pytest.mark.django_db
class ExpenseListRedesignTest(TestCase):
    """Listado de gastos: búsqueda, pestañas de año, grupos por mes y totales de toda la consulta."""

    def setUp(self):
        self.organization = Organization.objects.create(name="Org")
        self.user = User.objects.create_user(username="u", password="p", organization=self.organization)
        self.client.login(username="u", password="p")
        self.field = Field.objects.create(name="Cartuja", area=2.5, crop="Olivo", planting_year=2010,
                                          organization=self.organization)
        self.labor = ExpenseType.objects.create(name="Mano de obra", organization=self.organization)
        self.water = ExpenseType.objects.create(name="Agua", organization=self.organization)

    def _expense(self, day, amount, etype=None, description="Gasto"):
        return Expense.objects.create(field=self.field, expense_type=etype or self.labor, description=description,
                                      payment_date=day, amount=Decimal(amount), organization=self.organization)

    def test_search_matches_description_field_and_type(self):
        self._expense("2026-03-01", "10", description="Poda de marzo")
        self._expense("2026-03-02", "20", etype=self.water, description="Recibo")
        url = reverse('expense-list')
        self.assertEqual(len(self.client.get(url, {'q': 'poda'}).context['expenses']), 1)
        self.assertEqual(len(self.client.get(url, {'q': 'agua'}).context['expenses']), 1)
        self.assertEqual(len(self.client.get(url, {'q': 'cartuja'}).context['expenses']), 2)

    def test_totals_cover_whole_query_not_only_the_page(self):
        for i in range(55):
            self._expense("2026-01-10", "2")
        response = self.client.get(reverse('expense-list'))
        self.assertEqual(len(response.context['expenses']), 50)
        self.assertEqual(response.context['expense_count'], 55)
        self.assertEqual(response.context['total_amount'], Decimal("110"))
        self.assertEqual(response.context['month_totals']['2026-01']['total'], Decimal("110"))

    def test_month_groups_show_month_total(self):
        self._expense("2026-02-03", "30")
        self._expense("2026-02-20", "12.5")
        self._expense("2026-01-05", "7")
        response = self.client.get(reverse('expense-list'))
        self.assertEqual(response.content.decode().count('ex-month'), 2)
        self.assertContains(response, "42,50 €")

    def test_year_tabs_and_active_state(self):
        from datetime import date
        year = date.today().year
        response = self.client.get(reverse('expense-list'), {'date_from': f'{year}-01-01', 'date_to': f'{year}-12-31'})
        tabs = response.context['year_tabs']
        self.assertEqual([t['label'] for t in tabs], ['Todos', str(year), str(year - 1), str(year - 2)])
        self.assertTrue(tabs[1]['active'])
        self.assertFalse(response.context['custom_dates'])
        self.assertEqual(response.context['panel_filter_count'], 0)

    def test_year_tab_keeps_other_filters(self):
        response = self.client.get(reverse('expense-list'), {'type': self.water.pk, 'q': 'x', 'page': '1'})
        url = response.context['year_tabs'][1]['url']
        self.assertIn(f'type={self.water.pk}', url)
        self.assertIn('q=x', url)
        self.assertNotIn('page=', url)

    def test_custom_dates_count_as_panel_filter(self):
        response = self.client.get(reverse('expense-list'), {'date_from': '2025-03-01'})
        self.assertTrue(response.context['custom_dates'])
        self.assertEqual(response.context['panel_filter_count'], 1)

    def test_invalid_date_is_ignored(self):
        self._expense("2026-03-01", "10")
        response = self.client.get(reverse('expense-list'), {'date_from': '2026-02-30'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['expenses']), 1)

    def test_price_per_ha_mode_computes_amount(self):
        response = self.client.post(reverse('expense-create'), {
            'field': self.field.pk, 'expense_type': self.labor.pk, 'description': 'Laboreo',
            'payment_date': '2026-03-01', 'calculation_mode': 'price_per_ha', 'price_per_ha': '100',
        })
        self.assertEqual(response.status_code, 302)
        expense = Expense.objects.get(description='Laboreo')
        self.assertEqual(expense.amount, Decimal("250.00"))
        self.assertEqual(expense.field_area_snapshot, Decimal("2.50"))

    def test_form_errors_are_shown(self):
        response = self.client.post(reverse('expense-create'), {
            'field': self.field.pk, 'expense_type': self.labor.pk, 'description': 'Sin importe',
            'payment_date': '2026-03-01', 'calculation_mode': 'quantity_price',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'La cantidad es obligatoria')

    def test_type_list_only_offers_delete_without_expenses(self):
        self._expense("2026-03-01", "10")
        content = self.client.get(reverse('expense-type-list')).content.decode()
        self.assertNotIn(reverse('expense-type-delete', args=[self.labor.pk]), content)
        self.assertIn(reverse('expense-type-delete', args=[self.water.pk]), content)

    def test_invalid_value_in_other_mode_is_ignored(self):
        response = self.client.post(reverse('expense-create'), {
            'field': self.field.pk, 'expense_type': self.labor.pk, 'description': 'Otro modo',
            'payment_date': '2026-03-01', 'calculation_mode': 'total', 'amount': '50', 'quantity': '0',
        })
        self.assertEqual(response.status_code, 302)
        expense = Expense.objects.get(description='Otro modo')
        self.assertEqual(expense.amount, Decimal("50"))
        self.assertIsNone(expense.quantity)

    def test_edit_quantity_price_to_total_clears_units(self):
        expense = Expense.objects.create(field=self.field, expense_type=self.labor, description='Jornales',
                                         payment_date='2026-03-01', calculation_mode='quantity_price',
                                         quantity=Decimal('3'), unit_price=Decimal('80'), amount=Decimal('240'),
                                         organization=self.organization)
        response = self.client.post(reverse('expense-edit', args=[expense.pk]), {
            'field': self.field.pk, 'expense_type': self.labor.pk, 'description': 'Jornales',
            'payment_date': '2026-03-01', 'calculation_mode': 'total', 'amount': '200',
        })
        self.assertEqual(response.status_code, 302)
        expense.refresh_from_db()
        self.assertEqual((expense.amount, expense.quantity, expense.unit_price), (Decimal("200"), None, None))

    def test_second_page_marks_continued_month_with_full_total(self):
        for i in range(52):
            self._expense("2026-01-10", "1")
        response = self.client.get(reverse('expense-list'), {'page': 2})
        self.assertContains(response, "(cont.)")
        self.assertContains(response, "52,00 €")

    def test_invalid_date_does_not_count_as_filter(self):
        response = self.client.get(reverse('expense-list'), {'date_from': '2026-02-30'})
        self.assertFalse(response.context['has_filters'])
