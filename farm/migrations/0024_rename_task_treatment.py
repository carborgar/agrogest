# Generated by Django 5.0.11 on 2025-04-15 10:41

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('farm', '0023_rename_taskproduct_treatmentproduct'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='Task',
            new_name='Treatment',
        ),
    ]
