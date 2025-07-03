# Final migration to replace old expense_type field with the new one

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('farm', '0041_populate_expense_types'),
    ]

    operations = [
        # First, make sure all expenses have expense_type_new set
        migrations.RunSQL(
            "UPDATE farm_expense SET expense_type_new_id = (SELECT id FROM farm_expensetype WHERE organization_id = farm_expense.organization_id AND name = CASE "
            "WHEN expense_type = 'labor' THEN 'Mano de obra' "
            "WHEN expense_type = 'water' THEN 'Recibo de agua' "
            "WHEN expense_type = 'irrigation_fee' THEN 'Cuota comunidad de regantes' "
            "WHEN expense_type = 'machinery' THEN 'Maquinaria' "
            "WHEN expense_type = 'fuel' THEN 'Combustible' "
            "WHEN expense_type = 'maintenance' THEN 'Mantenimiento' "
            "WHEN expense_type = 'fertilizer' THEN 'Abonos no registrados' "
            "WHEN expense_type = 'seeds' THEN 'Semillas' "
            "WHEN expense_type = 'other' THEN 'Otros' "
            "END) WHERE expense_type_new_id IS NULL;",
            reverse_sql="-- No reverse SQL needed"
        ),
        
        # Remove the old expense_type field
        migrations.RemoveField(
            model_name='expense',
            name='expense_type',
        ),
        
        # Rename expense_type_new to expense_type
        migrations.RenameField(
            model_name='expense',
            old_name='expense_type_new',
            new_name='expense_type',
        ),
        
        # Make the field non-nullable
        migrations.AlterField(
            model_name='expense',
            name='expense_type',
            field=models.ForeignKey(on_delete=django.db.models.deletion.RESTRICT, to='farm.expensetype', verbose_name='Tipo de gasto'),
        ),
    ]