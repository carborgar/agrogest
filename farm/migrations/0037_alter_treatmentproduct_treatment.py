# Generated by Django 5.1.8 on 2025-05-03 11:45

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('farm', '0036_remove_field_created_by_remove_field_updated_by_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='treatmentproduct',
            name='treatment',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='farm.treatment'),
        ),
    ]
