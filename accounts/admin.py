from django.contrib import admin

from accounts.models import User, Organization

admin.site.register(Organization)
admin.site.register(User)
