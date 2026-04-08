# Plan: Sistema de notificaciones inbox

Notificaciones internas sin librerías externas ni colas de tareas. Un modelo `Notification` por usuario, con hooks en los puntos exactos donde ya se crean/finalizan tratamientos, y un campana en el menú con badge de no leídas.

## Pasos

1. **Modelo `Notification`** en `accounts/models.py` — campos `user`, `event_type`, `title`, `body`, `link`, `read` (bool, default False), `created_at`. Migración correspondiente.

2. **Servicio de notificaciones** nuevo `accounts/notification_service.py` — función `notify_org_users(event_type, title, body, link, organization)` que consulta todos los usuarios de la org, filtra por `NotificationPreferences`, y hace un `bulk_create` de `Notification`.

3. **Conectar los hooks** en los dos puntos exactos del código:
   - `farm/services.py` → `save_treatment_with_products()` llama al servicio tras guardar (evento `treatment_created`)
   - `farm/views/treatment_views.py` → `FinishTreatmentView.post()` llama al servicio tras `finish_treatment()` (evento `treatment_finished`)

4. **Context processor** en `farm/context_processors.py` — inyecta `unread_notifications_count` para el badge del menú (solo si el usuario está autenticado).

5. **Vista inbox** nueva en `accounts/views.py` (`NotificationInboxView`) + URL `/notificaciones/` — `ListView` de las notificaciones del usuario ordenadas por fecha, que marca todas como leídas al entrar. Admin registrado.

6. **Template inbox** `templates/accounts/inbox.html` — lista con diseño de tarjetas similar al de preferencias, distinguiendo leídas/no leídas visualmente.

7. **Bell en el menú** — añadir en `templates/menu.html` un enlace al inbox con badge `{{ unread_notifications_count }}` (se oculta automáticamente si es 0 con `{% if %}`).

## Consideraciones

1. **Marca como leída**: lo más simple es marcar todo al entrar al inbox (un solo `UPDATE`). Si en el futuro quieres marcar individualmente, el modelo ya lo soporta y solo hay que añadir un endpoint AJAX.
2. **Limpieza de notificaciones antiguas**: sin purga automática por ahora — se puede añadir un `management command` más adelante o un filtro de "solo últimos 30 días" en la vista.
3. **Multi-usuario**: el servicio ya está diseñado para notificar a N usuarios de la org, así que cuando se incorporen más usuarios no habrá que tocar nada.

