from django import forms

from accounts.models import NotificationPreferences


class NotificationPreferencesForm(forms.ModelForm):
    class Meta:
        model = NotificationPreferences
        fields = ['treatment_created_channel', 'treatment_finished_channel']
