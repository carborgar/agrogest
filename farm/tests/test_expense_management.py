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
        self.assertContains(response, "Gestión de gastos")
        self.assertContains(response, "Nuevo gasto")

    def test_expense_create_view(self):
        """Test the expense creation view"""
        response = self.client.get(reverse('expense-create'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Añadir gasto")

    def test_expense_create_post(self):
        """Test creating an expense via POST"""
        data = {
            'field': self.field.id,
            'expense_type': self.expense_type.id,
            'description': 'Test expense description',
            'payment_date': '2024-01-15',
            'amount': '100.00'
        }
        response = self.client.post(reverse('expense-create'), data)
        self.assertEqual(response.status_code, 302)  # Redirect after successful creation
        
        # Check that expense was created
        self.assertTrue(Expense.objects.filter(description='Test expense description').exists())

    def test_expense_list_with_expenses(self):
        """Test the expense list view with existing expenses"""
        expense = Expense.objects.create(
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
        self.assertContains(response, "75.25€")

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
        self.assertContains(response, "Añadir tipo de gasto")

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