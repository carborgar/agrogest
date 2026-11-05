from django.contrib import admin

from assistant.models import AssistantUsage


@admin.register(AssistantUsage)
class AssistantUsageAdmin(admin.ModelAdmin):
    list_display = ('date', 'organization', 'questions', 'calls', 'input_tokens', 'output_tokens')
    list_filter = ('organization',)
    date_hierarchy = 'date'
