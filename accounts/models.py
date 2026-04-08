from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class Organization(models.Model):
    """
    Representa una organización o empresa que agrupa usuarios.
    """
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class User(AbstractUser):
    """
    Usuario extendido con campos adicionales para tracking y organización.
    """
    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='members'
    )

    # Campos para tracking
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)
    last_activity = models.DateTimeField(null=True, blank=True)

    def update_last_activity(self):
        self.last_activity = timezone.now()
        self.save(update_fields=['last_activity'])

    def __str__(self):
        return self.username


class NotificationPreferences(models.Model):
    """
    Preferencias de notificación por usuario: canal elegido para cada evento.
    """
    CHANNEL_NONE = 'none'
    CHANNEL_INBOX = 'inbox'
    CHANNEL_EMAIL = 'email'
    CHANNEL_BOTH = 'both'

    CHANNEL_CHOICES = [
        (CHANNEL_NONE, 'Ninguna'),
        (CHANNEL_INBOX, 'Sólo inbox'),
        (CHANNEL_EMAIL, 'Sólo email'),
        (CHANNEL_BOTH, 'Inbox y email'),
    ]

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='notification_preferences'
    )
    treatment_created_channel = models.CharField(
        max_length=10,
        choices=CHANNEL_CHOICES,
        default=CHANNEL_INBOX,
        verbose_name='Nuevo tratamiento',
        help_text='Recibir notificación cuando se cree un nuevo tratamiento',
    )
    treatment_finished_channel = models.CharField(
        max_length=10,
        choices=CHANNEL_CHOICES,
        default=CHANNEL_INBOX,
        verbose_name='Tratamiento finalizado',
        help_text='Recibir notificación cuando se finalice un tratamiento',
    )

    class Meta:
        verbose_name = 'Preferencias de notificación'
        verbose_name_plural = 'Preferencias de notificación'

    def __str__(self):
        return f'Preferencias de {self.user}'


class Notification(models.Model):
    """
    Notificación interna de inbox por usuario.
    """
    EVENT_TREATMENT_CREATED = 'treatment_created'
    EVENT_TREATMENT_FINISHED = 'treatment_finished'

    EVENT_CHOICES = [
        (EVENT_TREATMENT_CREATED, 'Nuevo tratamiento'),
        (EVENT_TREATMENT_FINISHED, 'Tratamiento finalizado'),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='notifications'
    )
    event_type = models.CharField(max_length=50, choices=EVENT_CHOICES)
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    link = models.CharField(max_length=500, blank=True)
    read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Notificación'
        verbose_name_plural = 'Notificaciones'

    def __str__(self):
        return f'{self.title} → {self.user}'


class AuditLog(models.Model):
    """
    Registro de auditoría para cambios en entidades.
    """
    ACTION_CHOICES = [
        ('create', 'Creación'),
        ('update', 'Actualización'),
        ('delete', 'Eliminación'),
    ]

    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=10, choices=ACTION_CHOICES)
    model_name = models.CharField(max_length=100)
    object_id = models.IntegerField()
    object_repr = models.CharField(max_length=200)
    timestamp = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    details = models.JSONField(null=True, blank=True)  # Para almacenar los cambios específicos

    def __str__(self):
        return f"{self.get_action_display()} de {self.model_name} {self.object_id} por {self.user}"
