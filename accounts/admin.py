from django.contrib import admin

from accounts.models import User, Organization, NotificationPreferences, Notification

admin.site.register(Organization)
admin.site.register(User)
admin.site.register(NotificationPreferences)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'event_type', 'read', 'created_at')
    list_filter = ('event_type', 'read')
    search_fields = ('title', 'user__username')
    ordering = ('-created_at',)

