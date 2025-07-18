# Generated by Django 5.1.8 on 2025-07-10 10:19

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('farm', '0043_alter_product_spraying_dose_type'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='field',
            options={'ordering': ['name']},
        ),
        migrations.AlterModelOptions(
            name='machine',
            options={'ordering': ['name']},
        ),
        migrations.AlterModelOptions(
            name='product',
            options={'ordering': ['name']},
        ),
        migrations.AlterModelOptions(
            name='producttype',
            options={'ordering': ['name']},
        ),
        migrations.AlterField(
            model_name='treatment',
            name='type',
            field=models.CharField(choices=[('fertigation', 'Fertirrigación'), ('spraying', 'Pulverización')], max_length=20),
        ),
    ]
