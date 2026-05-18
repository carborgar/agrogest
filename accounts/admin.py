from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from accounts.models import User, Organization, NotificationPreferences, Notification
from accounts.notification_service import _send_email


# ── Acciones personalizadas ────────────────────────────────────────────────────

@admin.action(description='✉️  Enviar email de prueba a los usuarios seleccionados')
def send_test_email(modeladmin, request, queryset):
    ok, skip = 0, 0
    for user in queryset:
        if not user.email:
            skip += 1
            continue
        _send_email(
            user=user,
            title='📧 Email de prueba – AgroGest',
            body=(
                f'Hola {user.get_full_name() or user.username}, '
                'este es un mensaje de prueba enviado desde el panel de administración. '
                'Si lo recibes correctamente, la configuración de email funciona bien. 🎉'
            ),
            link='',
        )
        ok += 1
    if ok:
        modeladmin.message_user(request, f'Email de prueba enviado a {ok} usuario(s).', messages.SUCCESS)
    if skip:
        modeladmin.message_user(request, f'{skip} usuario(s) omitidos por no tener email.', messages.WARNING)


# ── Modelos registrados ────────────────────────────────────────────────────────

admin.site.register(Organization)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    actions = [send_test_email]


admin.site.register(NotificationPreferences)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'event_type', 'read', 'created_at')
    list_filter = ('event_type', 'read')
    search_fields = ('title', 'user__username')
    ordering = ('-created_at',)

