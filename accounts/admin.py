from django.contrib import admin

from accounts.models import User, Organization, NotificationPreferences

admin.site.register(Organization)
admin.site.register(User)
admin.site.register(NotificationPreferences)
