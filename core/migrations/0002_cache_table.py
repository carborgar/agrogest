from django.core.management import call_command
from django.db import migrations


def create_cache_table(apps, schema_editor):
    # Tabla de la caché en BD (CACHES en settings). Si ya existe, no hace nada.
    call_command("createcachetable", database=schema_editor.connection.alias)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_cache_table, migrations.RunPython.noop),
    ]
