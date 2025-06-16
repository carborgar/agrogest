from django.urls import path
from farm.views.field_views import (
    FieldListView,
    FieldCreateView, 
    FieldUpdateView,
    FieldDeleteView
)

# URLs para Field
urlpatterns = [
    path('admin/field/', FieldListView.as_view(), name='field-list'),
    path('admin/field/create/', FieldCreateView.as_view(), name='field-create'),
    path('admin/field/<int:pk>/edit/', FieldUpdateView.as_view(), name='field-edit'),
    path('admin/field/<int:pk>/delete/', FieldDeleteView.as_view(), name='field-delete'),
]
