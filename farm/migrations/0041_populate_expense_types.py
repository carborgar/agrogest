# Data migration to create ExpenseType objects and migrate existing data

from django.db import migrations


def create_expense_types_and_migrate_data(apps, schema_editor):
    """Create expense types and migrate existing expense data"""
    ExpenseType = apps.get_model('farm', 'ExpenseType')
    Expense = apps.get_model('farm', 'Expense')
    Organization = apps.get_model('accounts', 'Organization')
    
    # Default expense types mapping
    type_mapping = {
        'labor': ('Mano de obra', 'Gastos relacionados con trabajo manual y contratación de personal'),
        'water': ('Recibo de agua', 'Facturas y pagos por consumo de agua'),
        'irrigation_fee': ('Cuota comunidad de regantes', 'Cuotas y tasas de la comunidad de regantes'),
        'machinery': ('Maquinaria', 'Compra, alquiler y gastos de maquinaria agrícola'),
        'fuel': ('Combustible', 'Gastos en combustible para maquinaria y vehículos'),
        'maintenance': ('Mantenimiento', 'Reparaciones y mantenimiento de equipos e instalaciones'),
        'fertilizer': ('Abonos no registrados', 'Fertilizantes y abonos no incluidos en los tratamientos'),
        'seeds': ('Semillas', 'Compra de semillas y material de siembra'),
        'other': ('Otros', 'Otros gastos diversos no categorizados'),
    }
    
    # Create expense types for each organization
    for organization in Organization.objects.all():
        created_types = {}
        for key, (name, description) in type_mapping.items():
            expense_type = ExpenseType.objects.create(
                name=name,
                description=description,
                organization=organization
            )
            created_types[key] = expense_type
        
        # Migrate existing expenses for this organization
        expenses = Expense.objects.filter(organization=organization)
        for expense in expenses:
            if expense.expense_type in created_types:
                expense.expense_type_new = created_types[expense.expense_type]
                expense.save()


def reverse_migration(apps, schema_editor):
    """Reverse the migration"""
    ExpenseType = apps.get_model('farm', 'ExpenseType')
    ExpenseType.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('farm', '0040_add_expense_type_model'),
    ]

    operations = [
        migrations.RunPython(create_expense_types_and_migrate_data, reverse_migration),
    ]