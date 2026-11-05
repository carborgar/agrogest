from django.db import models


class AssistantUsage(models.Model):
    """
    Uso del asistente por organización y día.

    `questions` es lo que ve el usuario (su cupo); `calls` son las llamadas al modelo
    (hasta 3 por pregunta), que es lo que cuenta el proveedor. Ver assistant/quota.py.
    """
    organization = models.ForeignKey('accounts.Organization', on_delete=models.CASCADE,
                                     related_name='assistant_usage')
    date = models.DateField()
    questions = models.PositiveIntegerField(default=0)
    calls = models.PositiveIntegerField(default=0)
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = 'Uso del asistente'
        verbose_name_plural = 'Uso del asistente'
        ordering = ['-date']
        constraints = [
            models.UniqueConstraint(fields=['organization', 'date'], name='unique_assistant_usage_per_day'),
        ]

    def __str__(self):
        return f'{self.organization} · {self.date}: {self.questions} preguntas, {self.calls} llamadas'
