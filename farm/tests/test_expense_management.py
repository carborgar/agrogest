from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import Organization
from farm.models import Field, Expense

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

    def test_expense_creation(self):
        """Test creating an expense"""
        expense = Expense.objects.create(
            field=self.field,
            expense_type="labor",
            description="Manual labor for pruning",
            payment_date="2024-01-15",
            amount=Decimal("150.50"),
            organization=self.organization
        )
        
        self.assertEqual(expense.field, self.field)
        self.assertEqual(expense.expense_type, "labor")
        self.assertEqual(expense.description, "Manual labor for pruning")
        self.assertEqual(expense.amount, Decimal("150.50"))
        self.assertEqual(str(expense), "Mano de obra - Test Field - 150.50€")

    def test_expense_type_choices(self):
        """Test that expense type choices are correctly defined"""
        expected_types = [
            'labor', 'water', 'irrigation_fee', 'machinery', 
            'fuel', 'maintenance', 'fertilizer', 'seeds', 'other'
        ]
        actual_types = [choice[0] for choice in Expense.EXPENSE_TYPES]
        
        for expense_type in expected_types:
            self.assertIn(expense_type, actual_types)


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
            'expense_type': 'labor',
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
            expense_type="water",
            description="Water bill payment",
            payment_date="2024-01-15",
            amount=Decimal("75.25"),
            organization=self.organization
        )
        
        response = self.client.get(reverse('expense-list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Water bill payment")
        self.assertContains(response, "75.25€")