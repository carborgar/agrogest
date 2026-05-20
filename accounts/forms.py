from django import forms
from django.contrib.auth.forms import AuthenticationForm

from accounts.models import NotificationPreferences


class EmailOrUsernameAuthenticationForm(AuthenticationForm):
    username = forms.CharField(
        label='Usuario o email',
        widget=forms.TextInput(attrs={
            'autofocus': True,
            'class': 'form-control',
            'placeholder': 'Ingrese su usuario o email',
        }),
    )


class NotificationPreferencesForm(forms.ModelForm):
    class Meta:
        model = NotificationPreferences
        fields = ['treatment_created_channel', 'treatment_finished_channel']
