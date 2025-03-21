from django.contrib import admin

from farm.models import Product, Field, Machine, Task, Harvest, TaskProduct

admin.site.register(Product)
admin.site.register(Field)
admin.site.register(Machine)
admin.site.register(Task)
admin.site.register(Harvest)
admin.site.register(TaskProduct)
