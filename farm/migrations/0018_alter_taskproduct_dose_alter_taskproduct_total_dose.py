# Generated by Django 5.0.11 on 2025-04-03 10:08

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('farm', '0017_alter_task_water_per_ha'),
    ]

    operations = [
        migrations.AlterField(
            model_name='taskproduct',
            name='dose',
            field=models.DecimalField(decimal_places=2, max_digits=10),
        ),
        migrations.AlterField(
            model_name='taskproduct',
            name='total_dose',
            field=models.DecimalField(decimal_places=2, max_digits=10),
        ),
    ]
