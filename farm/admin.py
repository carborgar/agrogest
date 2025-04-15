from django.contrib import admin

from farm.models import Product, Field, Machine, Treatment, Harvest, TreatmentProduct, ProductType


class TreatmentAdmin(admin.ModelAdmin):
    list_per_page = 20


class TreatmentProductAdmin(admin.ModelAdmin):
    list_per_page = 20


admin.site.register(Product)
admin.site.register(Field)
admin.site.register(Machine)
admin.site.register(Treatment, TreatmentAdmin)
admin.site.register(Harvest)
admin.site.register(TreatmentProduct, TreatmentProductAdmin)
admin.site.register(ProductType)
