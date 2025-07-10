from django import forms
from django.forms.widgets import Select
from django.forms.utils import flatatt
from django.utils.html import format_html
from django.utils.safestring import mark_safe
import json


class SmartSelect(Select):
    """
    A select widget that automatically switches between standard dropdown 
    and searchable selector with pills based on the number of options.
    """
    
    def __init__(self, attrs=None, choices=(), threshold=10):
        super().__init__(attrs, choices)
        self.threshold = threshold
        
    def render(self, name, value, attrs=None, renderer=None):
        if attrs is None:
            attrs = {}
        
        # Count the number of choices
        choice_count = len(list(self.choices))
        
        # If below threshold, use standard select
        if choice_count <= self.threshold:
            attrs.update({'class': attrs.get('class', '') + ' form-select'})
            return super().render(name, value, attrs, renderer)
        
        # Otherwise, render as searchable selector
        return self.render_searchable(name, value, attrs)
    
    def render_searchable(self, name, value, attrs):
        """Render as searchable selector with pills"""
        if attrs is None:
            attrs = {}
            
        attrs.update({
            'class': attrs.get('class', '') + ' smart-select-searchable',
            'data-threshold': str(self.threshold)
        })
        
        # Build the data for JavaScript
        choices_data = []
        selected_choices = []
        
        for option_value, option_label in self.choices:
            choice_item = {
                'value': str(option_value),
                'label': str(option_label)
            }
            choices_data.append(choice_item)
            
            # Handle both single and multiple values
            if value is not None:
                if isinstance(value, (list, tuple)):
                    if str(option_value) in [str(v) for v in value]:
                        selected_choices.append(choice_item)
                else:
                    if str(option_value) == str(value):
                        selected_choices.append(choice_item)
        
        widget_id = attrs.get('id', f'id_{name}')
        
        # Create the HTML structure
        html = format_html('''
        <div class="smart-select-container" data-name="{name}" data-widget-id="{widget_id}">
            <input type="hidden" name="{name}" id="{widget_id}" value="{value}" {attrs} />
            <div class="smart-select-display">
                <div class="smart-select-pills" id="{widget_id}_pills"></div>
                <div class="smart-select-input-wrapper">
                    <input type="text" 
                           class="form-control smart-select-search" 
                           id="{widget_id}_search"
                           placeholder="Buscar y seleccionar..."
                           autocomplete="off" />
                    <div class="smart-select-dropdown" id="{widget_id}_dropdown">
                        <div class="smart-select-options" id="{widget_id}_options"></div>
                    </div>
                </div>
            </div>
        </div>
        <script type="application/json" class="smart-select-data" data-for="{widget_id}">
            {{"choices": {choices_json}, "selected": {selected_json}}}
        </script>
        ''', 
            name=name,
            widget_id=widget_id,
            value=value or '',
            attrs=flatatt(attrs),
            choices_json=json.dumps(choices_data),
            selected_json=json.dumps(selected_choices)
        )
        
        return html

    class Media:
        css = {
            'all': ('css/smart-select.css',)
        }
        js = ('js/smart-select.js',)


class NoPlaceholderModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Forzar widgets con placeholder vacío
        for field in self.fields.values():
            field.widget.attrs['placeholder'] = ''
