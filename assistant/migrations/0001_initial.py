import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('accounts', '0006_notification_preferences_channels'),
    ]

    operations = [
        migrations.CreateModel(
            name='AssistantUsage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField()),
                ('questions', models.PositiveIntegerField(default=0)),
                ('calls', models.PositiveIntegerField(default=0)),
                ('input_tokens', models.PositiveIntegerField(default=0)),
                ('output_tokens', models.PositiveIntegerField(default=0)),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                                   related_name='assistant_usage', to='accounts.organization')),
            ],
            options={
                'verbose_name': 'Uso del asistente',
                'verbose_name_plural': 'Uso del asistente',
                'ordering': ['-date'],
                'constraints': [models.UniqueConstraint(fields=('organization', 'date'),
                                                        name='unique_assistant_usage_per_day')],
            },
        ),
    ]
