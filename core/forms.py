from django import forms


class NoPlaceholderModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Forzar widgets con placeholder vacío
        for field in self.fields.values():
            field.widget.attrs['placeholder'] = ''
