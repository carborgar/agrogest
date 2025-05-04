from django.contrib import admin

from farm.models import Product, Field, Machine, Treatment, Harvest, TreatmentProduct, ProductType


class TreatmentAdmin(admin.ModelAdmin):
    list_per_page = 20


class TreatmentProductAdmin(admin.ModelAdmin):
    list_per_page = 20
    list_filter = ('treatment', 'product__name')
    ordering = ['-created_at']

    search_fields = ['product__name', 'treatment__name']
    search_help_text = 'Buscar por nombre del producto o del tratamiento'

    list_display = ('treatment', 'product', 'dose', 'dose_type')


admin.site.register(Product)
admin.site.register(Field)
admin.site.register(Machine)
admin.site.register(Treatment, TreatmentAdmin)
admin.site.register(Harvest)
admin.site.register(TreatmentProduct, TreatmentProductAdmin)
admin.site.register(ProductType)
