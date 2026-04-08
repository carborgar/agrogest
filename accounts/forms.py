from django import forms

from accounts.models import NotificationPreferences


class NotificationPreferencesForm(forms.ModelForm):
    class Meta:
        model = NotificationPreferences
        fields = ['notify_treatment_created', 'notify_treatment_finished']

