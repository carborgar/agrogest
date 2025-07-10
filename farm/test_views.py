from django import forms
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from core.forms import SmartSelect
from farm.models import Product, Field, Machine


class TestSmartSelectForm(forms.Form):
    """Test form to demonstrate SmartSelect functionality"""
    
    def __init__(self, user=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # If user is provided, filter by organization
        if user and hasattr(user, 'organization'):
            org = user.organization
            product_qs = Product.objects.filter(organization=org)
            field_qs = Field.objects.filter(organization=org)[:3]  # Limit to 3 for testing
            machine_qs = Machine.objects.filter(organization=org)
        else:
            # For testing, use all objects
            product_qs = Product.objects.all()
            field_qs = Field.objects.all()[:3]
            machine_qs = Machine.objects.all()
    
        # Test with many products (should use searchable)
        self.fields['product'] = forms.ModelChoiceField(
            queryset=product_qs,
            widget=SmartSelect(threshold=5),
            label="Producto (SmartSelect)",
            required=False
        )
        
        # Test with few fields (should use standard select)
        self.fields['field'] = forms.ModelChoiceField(
            queryset=field_qs,
            widget=SmartSelect(threshold=5),
            label="Campo (Standard Select)",
            required=False
        )
        
        # Test with machines (borderline case)
        self.fields['machine'] = forms.ModelChoiceField(
            queryset=machine_qs,
            widget=SmartSelect(threshold=10),
            label="Máquina (SmartSelect if > 10)",
            required=False
        )


@login_required
def test_smart_select(request):
    """Test view for SmartSelect widget"""
    if request.method == 'POST':
        form = TestSmartSelectForm(user=request.user, data=request.POST)
        if form.is_valid():
            # Just show the selected values
            return render(request, 'test_smart_select.html', {
                'form': form,
                'submitted': True,
                'data': form.cleaned_data
            })
    else:
        form = TestSmartSelectForm(user=request.user)
    
    return render(request, 'test_smart_select.html', {'form': form})