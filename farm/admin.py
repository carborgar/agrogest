from django.contrib import admin

from farm.models import Product, Field, Machine, Task, Harvest, TaskProduct, ProductType


class TaskAdmin(admin.ModelAdmin):
    list_per_page = 20


class TaskProductAdmin(admin.ModelAdmin):
    list_per_page = 20


admin.site.register(Product)
admin.site.register(Field)
admin.site.register(Machine)
admin.site.register(Task, TaskAdmin)
admin.site.register(Harvest)
admin.site.register(TaskProduct, TaskProductAdmin)
admin.site.register(ProductType)
