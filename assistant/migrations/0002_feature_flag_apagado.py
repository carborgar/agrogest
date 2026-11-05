from django.db import migrations

DESCRIPTION = 'Asistente IA. Necesita ASSISTANT_API_KEY; consume la cuota gratuita del proveedor.'


def create_flag(apps, schema_editor):
    """El flag nace apagado: `is_enabled` da True a un flag que no existe."""
    FeatureFlag = apps.get_model('core', 'FeatureFlag')
    FeatureFlag.objects.get_or_create(name='ASSISTANT', defaults={'enabled': False, 'description': DESCRIPTION})


class Migration(migrations.Migration):

    dependencies = [
        ('assistant', '0001_initial'),
        ('core', '0002_cache_table'),
    ]

    operations = [
        migrations.RunPython(create_flag, migrations.RunPython.noop),
    ]
