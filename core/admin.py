from django.contrib import admin

from .models import FeatureFlag


@admin.register(FeatureFlag)
class FeatureFlagAdmin(admin.ModelAdmin):
    list_display = ('name', 'enabled', 'description', 'updated_at')
    list_editable = ('enabled',)
    list_display_links = ('name',)
    search_fields = ('name', 'description')
    readonly_fields = ('updated_at',)
    ordering = ('name',)

    def get_readonly_fields(self, request, obj=None):
        # No permitir cambiar el nombre una vez creado para no romper referencias en código
        if obj:
            return self.readonly_fields + ('name',)
        return self.readonly_fields

