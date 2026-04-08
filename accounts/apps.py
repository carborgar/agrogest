from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'accounts'

    def ready(self):
        from django.db.models.signals import post_save
        from django.dispatch import receiver

        from accounts.models import User, NotificationPreferences

        @receiver(post_save, sender=User)
        def create_notification_preferences(sender, instance, created, **kwargs):
            if created:
                NotificationPreferences.objects.get_or_create(user=instance)

