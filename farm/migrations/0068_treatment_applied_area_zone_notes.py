from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('farm', '0067_storagepoint_field_storage_point_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='treatment',
            name='applied_area',
            field=models.FloatField(
                blank=True,
                null=True,
                help_text='Hectáreas realmente tratadas. Dejar vacío si se trató la parcela completa.'
            ),
        ),
        migrations.AddField(
            model_name='treatment',
            name='zone_notes',
            field=models.CharField(
                blank=True,
                max_length=200,
                help_text='Zona o sector tratado (ej: zona norte, sector 3). Opcional.'
            ),
        ),
    ]
