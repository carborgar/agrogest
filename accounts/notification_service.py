"""
Servicio de notificaciones inbox + email.

Uso:
    from accounts.notification_service import notify_org_users
    from accounts.models import Notification

    notify_org_users(
        event_type=Notification.EVENT_TREATMENT_CREATED,
        title='Nuevo tratamiento: Poda',
        body='Se ha creado el tratamiento "Poda" en la parcela Norte.',
        link='/tratamientos/42',
        organization=treatment.organization,
    )
"""
import logging

from django.conf import settings
from django.contrib.auth import get_user_model

from accounts.models import Notification, NotificationPreferences

logger = logging.getLogger(__name__)
User = get_user_model()

# Qué campo de NotificationPreferences controla cada evento
_PREF_FIELD = {
    Notification.EVENT_TREATMENT_CREATED: 'treatment_created_channel',
    Notification.EVENT_TREATMENT_FINISHED: 'treatment_finished_channel',
}


def notify_org_users(event_type, title, body='', link='', organization=None):
    """
    Para cada usuario de la organización, comprueba su preferencia de canal
    y crea notificación inbox y/o envía email según corresponda.
    """
    if organization is None:
        return

    pref_field = _PREF_FIELD.get(event_type)
    if not pref_field:
        return

    users = User.objects.filter(organization=organization)
    inbox_to_create = []

    for user in users:
        prefs, _ = NotificationPreferences.objects.get_or_create(user=user)
        channel = getattr(prefs, pref_field)

        if channel in (NotificationPreferences.CHANNEL_INBOX, NotificationPreferences.CHANNEL_BOTH):
            inbox_to_create.append(Notification(
                user=user,
                event_type=event_type,
                title=title,
                body=body,
                link=link,
            ))

        if channel in (NotificationPreferences.CHANNEL_EMAIL, NotificationPreferences.CHANNEL_BOTH):
            _send_email(user=user, title=title, body=body, link=link)

    if inbox_to_create:
        Notification.objects.bulk_create(inbox_to_create)


# ── Email ─────────────────────────────────────────────────────────────────────

def _send_email(user, title, body, link=''):
    """Envía el email de notificación via Resend (o el backend Django si no hay key)."""
    if not user.email:
        return

    site_url = getattr(settings, 'SITE_URL', 'http://localhost:8000').rstrip('/')
    absolute_link = (site_url + link) if link else ''
    html = _build_email_html(title=title, body=body, link=absolute_link)

    resend_key = getattr(settings, 'RESEND_API_KEY', '')

    if resend_key:
        try:
            import resend
            resend.api_key = resend_key
            resend.Emails.send({
                'from': settings.DEFAULT_FROM_EMAIL,
                'to': [user.email],
                'subject': title,
                'html': html,
            })
        except Exception:
            logger.exception('Error enviando email via Resend a %s', user.email)
    else:
        # Fallback: backend de Django (console en desarrollo)
        from django.core.mail import send_mail
        import re
        plain_text = re.sub(r'<[^>]+>', '', html)
        try:
            send_mail(
                subject=title,
                message=plain_text,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                html_message=html,
                fail_silently=True,
            )
        except Exception:
            logger.exception('Error enviando email a %s', user.email)


def _build_email_html(title, body, link=''):
    link_block = ''
    if link:
        link_block = (
            f'<p style="margin:24px 0 0;">'
            f'<a href="{link}" style="display:inline-block;padding:10px 20px;'
            f'background:#1a2332;color:white;text-decoration:none;border-radius:6px;'
            f'font-size:.875rem;font-weight:600;">Ver detalle →</a></p>'
        )

    return f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#1a2332;">
  <div style="max-width:560px;margin:40px auto;background:white;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.08);">
    <div style="background:#1a2332;padding:20px 32px;">
      <span style="color:white;font-size:1.05rem;font-weight:700;">🌿 AgroGest</span>
    </div>
    <div style="padding:32px;">
      <h2 style="margin:0 0 12px;font-size:1.05rem;font-weight:700;">{title}</h2>
      <p style="margin:0;color:#475569;line-height:1.65;font-size:.9rem;">{body}</p>
      {link_block}
    </div>
    <div style="padding:16px 32px;background:#f8faff;border-top:1px solid #e2e8f0;font-size:.75rem;color:#94a3b8;">
      Puedes cambiar tus preferencias de notificación en los ajustes de tu cuenta.
    </div>
  </div>
</body>
</html>"""
