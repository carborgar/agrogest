from django.contrib.messages.views import SuccessMessageMixin
from django.db import transaction
from django.urls import reverse
from django.views.generic import ListView, DetailView
from django.views.generic.edit import CreateView, UpdateView

from .forms import TaskForm, TaskProductFormSet
from .models import Field
from .models import Product
from .models import Task


class FieldListView(ListView):
    model = Field
    template_name = "fields/field_list.html"
    context_object_name = "fields"

    def get_queryset(self):
        return Field.objects.all()


class TaskListView(ListView):
    model = Task
    template_name = 'tasks/task_list.html'
    context_object_name = 'tasks'

    def get_queryset(self):
        queryset = super().get_queryset()

        field_ids = self.request.GET.getlist('field')
        type_filters = self.request.GET.getlist('type')
        status_filters = self.request.GET.getlist('status')
        product_ids = self.request.GET.getlist('products')
        date_from = self.request.GET.get('date_from')
        date_to = self.request.GET.get('date_to')

        if field_ids:
            queryset = queryset.filter(field__id__in=field_ids)
        if type_filters:
            queryset = queryset.filter(type__in=type_filters)
        if product_ids:
            queryset = queryset.filter(products__id__in=product_ids)
        if date_from:
            queryset = queryset.filter(date__gte=date_from)  # Filtra por fecha desde
        if date_to:
            queryset = queryset.filter(date__lte=date_to)

        # Filtrado por múltiples estados
        if status_filters:
            queryset = [task for task in queryset if task.status() in status_filters]

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['fields'] = Field.objects.all()
        context['products'] = Product.objects.all()
        context['type_choices'] = Task.TYPE_CHOICES
        context['status_choices'] = Task.STATUS_CHOICES
        context['selected_fields'] = self.request.GET.getlist('field')
        context['selected_types'] = self.request.GET.getlist('type')
        context['selected_statuses'] = self.request.GET.getlist('status')
        context['selected_products'] = self.request.GET.getlist('products')
        context['date_from'] = self.request.GET.get('date_from')
        context['date_to'] = self.request.GET.get('date_to')
        return context


class TaskDetailView(DetailView):
    model = Task
    template_name = 'tasks/task_detail.html'
    context_object_name = 'task'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['status_choices'] = Task.STATUS_CHOICES
        context['products'] = self.object.taskproduct_set.all()

        return context


class TaskFormView(SuccessMessageMixin, CreateView, UpdateView):
    model = Task
    form_class = TaskForm
    template_name = 'tasks/task_form.html'

    def get_success_url(self):
        return reverse('task_detail', kwargs={'pk': self.object.id})

    def get_success_message(self, cleaned_data):
        if self.object.pk is None or not hasattr(self, 'object') or self.object is None:
            return f"Tarea '{cleaned_data['name']}' creada exitosamente"
        else:
            return f"Tarea '{cleaned_data['name']}' actualizada exitosamente"

    def get_object(self, queryset=None):
        if 'pk' in self.kwargs:
            return super().get_object(queryset)
        return None

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        if self.request.POST:
            if self.object:  # Update operation
                context['products_formset'] = TaskProductFormSet(
                    self.request.POST, instance=self.object
                )
            else:  # Create operation
                context['products_formset'] = TaskProductFormSet(self.request.POST)
        else:
            if self.object:  # Update operation
                context['products_formset'] = TaskProductFormSet(instance=self.object)
            else:  # Create operation
                context['products_formset'] = TaskProductFormSet()

        return context

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.get_form()
        task_product_formset = TaskProductFormSet(request.POST, instance=self.object)

        if form.is_valid() and task_product_formset.is_valid():
            self.object = form.save()
            task_product_formset.instance = self.object
            task_product_formset.save()
            return self.form_valid(form)
        else:
            return self.form_invalid(form)
