#!/usr/bin/env python3
"""
Django CRUD Generator for Admin Entities
Generates list, create, and edit templates maintaining app's design consistency
"""

import os
import re
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple


@dataclass
class FieldInfo:
    name: str
    field_type: str
    verbose_name: str
    choices: Optional[List[Tuple[str, str]]] = None
    related_model: Optional[str] = None
    is_required: bool = True
    max_length: Optional[int] = None
    help_text: str = ""


class DjangoCRUDGenerator:
    def __init__(self, models_file_path: str):
        self.models_file_path = models_file_path
        self.models_content = self._read_models_file()

    def _read_models_file(self) -> str:
        with open(self.models_file_path, 'r', encoding='utf-8') as f:
            return f.read()

    def _extract_model_fields(self, model_name: str) -> List[FieldInfo]:
        """Extrae información de los campos de un modelo específico"""
        # Buscar la definición de la clase
        pattern = rf'class {model_name}\([^)]*\):(.*?)(?=class|\Z)'
        match = re.search(pattern, self.models_content, re.DOTALL)

        if not match:
            raise ValueError(f"Modelo {model_name} no encontrado")

        model_content = match.group(1)
        fields = []

        # Patrones para diferentes tipos de campos
        field_patterns = [
            (r'(\w+)\s*=\s*models\.CharField\([^)]*max_length=(\d+)[^)]*\)', 'CharField'),
            (r'(\w+)\s*=\s*models\.TextField\([^)]*\)', 'TextField'),
            (r'(\w+)\s*=\s*models\.IntegerField\([^)]*\)', 'IntegerField'),
            (r'(\w+)\s*=\s*models\.FloatField\([^)]*\)', 'FloatField'),
            (r'(\w+)\s*=\s*models\.DecimalField\([^)]*\)', 'DecimalField'),
            (r'(\w+)\s*=\s*models\.DateField\([^)]*\)', 'DateField'),
            (r'(\w+)\s*=\s*models\.DateTimeField\([^)]*\)', 'DateTimeField'),
            (r'(\w+)\s*=\s*models\.BooleanField\([^)]*\)', 'BooleanField'),
            (r'(\w+)\s*=\s*models\.ForeignKey\([\'"]([^\'\"]+)[\'"][^)]*\)', 'ForeignKey'),
        ]

        for pattern, field_type in field_patterns:
            matches = re.finditer(pattern, model_content)
            for match in matches:
                field_name = match.group(1)

                # Saltar campos heredados comunes
                if field_name in ['organization', 'created_at', 'updated_at', 'id']:
                    continue

                field_info = FieldInfo(
                    name=field_name,
                    field_type=field_type,
                    verbose_name=self._generate_verbose_name(field_name)
                )

                # Extraer información adicional del campo
                full_field_def = self._get_full_field_definition(model_content, field_name)

                if field_type == 'CharField':
                    max_length_match = re.search(r'max_length=(\d+)', full_field_def)
                    if max_length_match:
                        field_info.max_length = int(max_length_match.group(1))

                if field_type == 'ForeignKey':
                    field_info.related_model = match.group(2)

                # Verificar si tiene choices
                choices_match = re.search(r'choices=(\w+)', full_field_def)
                if choices_match:
                    choices_var = choices_match.group(1)
                    field_info.choices = self._extract_choices(model_content, choices_var)

                # Verificar si es opcional
                if 'null=True' in full_field_def or 'blank=True' in full_field_def:
                    field_info.is_required = False

                # Extraer help_text
                help_match = re.search(r'help_text=[\'"]([^\'"]*)[\'"]', full_field_def)
                if help_match:
                    field_info.help_text = help_match.group(1)

                fields.append(field_info)

        return fields

    def _get_full_field_definition(self, model_content: str, field_name: str) -> str:
        """Obtiene la definición completa de un campo"""
        pattern = rf'{field_name}\s*=\s*models\.[^(]+\([^)]*\)'
        match = re.search(pattern, model_content)
        return match.group(0) if match else ""

    def _extract_choices(self, model_content: str, choices_var: str) -> List[Tuple[str, str]]:
        """Extrae las opciones de un campo con choices"""
        pattern = rf'{choices_var}\s*=\s*\[(.*?)\]'
        match = re.search(pattern, model_content, re.DOTALL)

        if not match:
            return []

        choices_content = match.group(1)
        choices = []

        # Buscar tuplas en el formato ('key', 'value')
        tuple_pattern = r'\([\'"]([^\'"]*)[\'"],\s*[\'"]([^\'"]*)[\'"]\)'
        for tuple_match in re.finditer(tuple_pattern, choices_content):
            choices.append((tuple_match.group(1), tuple_match.group(2)))

        return choices

    def _generate_verbose_name(self, field_name: str) -> str:
        """Genera un nombre legible para el campo"""
        verbose_map = {
            'name': 'Nombre',
            'type': 'Tipo',
            'area': 'Área (ha)',
            'crop': 'Cultivo',
            'planting_year': 'Año de plantación',
            'location': 'Ubicación',
            'capacity': 'Capacidad (L)',
            'description': 'Descripción',
            'price': 'Precio',
            'comments': 'Comentarios',
            'product_type': 'Tipo de producto',
            'spraying_dose': 'Dosis pulverización',
            'fertigation_dose': 'Dosis fertirrigación',
            'spraying_dose_type': 'Tipo dosis pulverización',
            'fertigation_dose_type': 'Tipo dosis fertirrigación'
        }

        return verbose_map.get(field_name, field_name.replace('_', ' ').title())

    def _needs_filters(self, model_name: str, fields: List[FieldInfo]) -> bool:
        """Determina si una entidad necesita filtros basado en su complejidad"""
        # Productos tienen muchos campos y relaciones, necesitan filtros
        if model_name.lower() == 'product':
            return True

        # Si tiene más de 4 campos o ForeignKeys, probablemente necesite filtros
        if len(fields) > 4 or any(f.field_type == 'ForeignKey' for f in fields):
            return True

        return False

    def generate_list_template(self, model_name: str, app_name: str = 'farm') -> str:
        """Genera el template de listado"""
        fields = self._extract_model_fields(model_name)
        model_name_lower = model_name.lower()
        model_verbose = self._get_model_verbose_name(model_name)
        model_verbose_plural = f"{model_verbose}s"

        needs_filters = self._needs_filters(model_name, fields)

        template = f'''{{%% extends "base.html" %%}}
{{% load django_bootstrap5 %}}
{{% load static %}}

{{% block extra_head %}}
<link href="{{% static 'css/treatment-styles.css' %}}" rel="stylesheet">
{{% endblock %}}

{{% block header %}}{model_verbose_plural}{{% endblock %}}

{{% block content %}}
<div class="row g-4">'''

        if needs_filters:
            template += self._generate_filters_section(model_name, fields)
            content_col = "col-lg-9"
        else:
            content_col = "col-12"

        template += f'''
    <!-- Results -->
    <div class="{content_col}">
        <div class="results-container card">
            <div class="results-header d-flex justify-content-between align-items-center">
                <div class="d-flex align-items-center">
                    <h5 class="mb-0 fw-bold">{model_verbose_plural}
                        <span class="badge bg-primary rounded-pill ms-2">{{{{ total_count }}}}</span>
                    </h5>
                </div>
                <div class="d-flex gap-3">
                    <div class="view-switcher">
                        <button type="button" class="btn view-btn active" id="cardViewBtn">
                            <i class="fa fa-th"></i> Tarjetas
                        </button>
                        <button type="button" class="btn view-btn" id="listViewBtn">
                            <i class="fa fa-list"></i> Lista
                        </button>
                    </div>
                </div>
            </div>

            <div class="card-body p-4" id="results">
                {{% if not {model_name_lower}s %}}
                <div class="alert alert-info d-flex align-items-center" role="alert">
                    <i class="fa fa-info-circle me-3 fs-4"></i>
                    <div>No se encontraron {model_verbose.lower()}s.</div>
                </div>
                {{% endif %}}

                <div class="row row-cols-1 row-cols-md-2 row-cols-lg-3 g-4" id="cardView">
                    {{% for {model_name_lower} in {model_name_lower}s %}}
                    <div class="col">
                        <div class="card h-100 shadow-sm hover-shadow">
                            <div class="card-body">
                                <div class="d-flex justify-content-between align-items-start mb-2">
                                    <h6 class="card-title mb-1 fw-bold">{{{{ {model_name_lower}.name }}}}</h6>
                                    <div class="dropdown">
                                        <button class="btn btn-sm btn-outline-secondary" data-bs-toggle="dropdown">
                                            <i class="fa fa-ellipsis-v"></i>
                                        </button>
                                        <ul class="dropdown-menu">
                                            <li><a class="dropdown-item" href="{{% url '{model_name_lower}-edit' {model_name_lower}.id %}}">
                                                <i class="fa fa-edit me-2"></i>Editar</a></li>
                                            <li><a class="dropdown-item text-danger" href="#" 
                                                   onclick="confirmDelete('{{{{ {model_name_lower}.id }}}}', '{{{{ {model_name_lower}.name }}}}')">
                                                <i class="fa fa-trash me-2"></i>Eliminar</a></li>
                                        </ul>
                                    </div>
                                </div>'''

        # Agregar campos principales para mostrar en la tarjeta
        main_fields = [f for f in fields if f.name not in ['name', 'description', 'comments']][:3]
        for field in main_fields:
            if field.field_type == 'ForeignKey':
                template += f'''
                                <p class="card-text text-muted mb-1">
                                    <small><strong>{field.verbose_name}:</strong> {{{{ {model_name_lower}.{field.name} }}}}</small>
                                </p>'''
            elif field.choices:
                template += f'''
                                <p class="card-text text-muted mb-1">
                                    <small><strong>{field.verbose_name}:</strong> {{{{ {model_name_lower}.get_{field.name}_display }}}}</small>
                                </p>'''
            else:
                template += f'''
                                <p class="card-text text-muted mb-1">
                                    <small><strong>{field.verbose_name}:</strong> {{{{ {model_name_lower}.{field.name} }}}}</small>
                                </p>'''

        template += f'''
                            </div>
                        </div>
                    </div>
                    {{% endfor %}}
                </div>

                <div id="listView" class="d-none">
                    <div class="table-responsive">
                        <table class="table table-hover">
                            <thead class="table-light">
                                <tr>
                                    <th>Nombre</th>'''

        # Headers para la vista de tabla
        for field in main_fields:
            template += f'''
                                    <th>{field.verbose_name}</th>'''

        template += f'''
                                    <th width="120">Acciones</th>
                                </tr>
                            </thead>
                            <tbody>
                                {{% for {model_name_lower} in {model_name_lower}s %}}
                                <tr>
                                    <td class="fw-semibold">{{{{ {model_name_lower}.name }}}}</td>'''

        # Datos para la vista de tabla
        for field in main_fields:
            if field.field_type == 'ForeignKey':
                template += f'''
                                    <td>{{{{ {model_name_lower}.{field.name} }}}}</td>'''
            elif field.choices:
                template += f'''
                                    <td>{{{{ {model_name_lower}.get_{field.name}_display }}}}</td>'''
            else:
                template += f'''
                                    <td>{{{{ {model_name_lower}.{field.name} }}}}</td>'''

        template += f'''
                                    <td>
                                        <div class="btn-group btn-group-sm">
                                            <a href="{{% url '{model_name_lower}-edit' {model_name_lower}.id %}}" 
                                               class="btn btn-outline-primary btn-sm">
                                                <i class="fa fa-edit"></i>
                                            </a>
                                            <button class="btn btn-outline-danger btn-sm"
                                                    onclick="confirmDelete('{{{{ {model_name_lower}.id }}}}', '{{{{ {model_name_lower}.name }}}}')">
                                                <i class="fa fa-trash"></i>
                                            </button>
                                        </div>
                                    </td>
                                </tr>
                                {{% endfor %}}
                            </tbody>
                        </table>
                    </div>
                </div>'''

        # Paginación si es necesaria
        template += f'''
                {{% if is_paginated %}}
                <div class="d-flex justify-content-center mt-3">
                    {{% bootstrap_pagination page_obj %}}
                </div>
                {{% endif %}}
            </div>
        </div>
    </div>
</div>

<!-- Botón flotante para crear -->
<div class="floating-action">
    <a href="{{% url '{model_name_lower}-create' %}}" class="btn btn-primary btn-lg rounded-circle shadow">
        <i class="fa fa-plus"></i>
    </a>
</div>

<!-- Modal de confirmación de eliminación -->
<div class="modal fade" id="deleteModal" tabindex="-1">
    <div class="modal-dialog">
        <div class="modal-content">
            <div class="modal-header">
                <h5 class="modal-title">Confirmar eliminación</h5>
                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
            </div>
            <div class="modal-body">
                <p>¿Está seguro de que desea eliminar <strong id="deleteItemName"></strong>?</p>
                <p class="text-muted">Esta acción no se puede deshacer.</p>
            </div>
            <div class="modal-footer">
                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancelar</button>
                <form id="deleteForm" method="post" style="display: inline;">
                    {{% csrf_token %}}
                    <button type="submit" class="btn btn-danger">Eliminar</button>
                </form>
            </div>
        </div>
    </div>
</div>
{{% endblock %}}

{{% block extra_js %}}
<script>
    document.addEventListener('DOMContentLoaded', function() {{
        // Toggle between views
        const cardView = document.getElementById('cardView');
        const listView = document.getElementById('listView');
        const cardViewBtn = document.getElementById('cardViewBtn');
        const listViewBtn = document.getElementById('listViewBtn');

        cardViewBtn.addEventListener('click', function() {{
            cardView.classList.remove('d-none');
            listView.classList.add('d-none');
            cardViewBtn.classList.add('active');
            listViewBtn.classList.remove('active');
        }});

        listViewBtn.addEventListener('click', function() {{
            listView.classList.remove('d-none');
            cardView.classList.add('d-none');
            listViewBtn.classList.add('active');
            cardViewBtn.classList.remove('active');
        }});
    }});

    function confirmDelete(id, name) {{
        document.getElementById('deleteItemName').textContent = name;
        document.getElementById('deleteForm').action = `/admin/{model_name_lower}/` + id + `/delete/`;
        new bootstrap.Modal(document.getElementById('deleteModal')).show();
    }}
</script>

<style>
.floating-action {{
    position: fixed;
    bottom: 30px;
    right: 30px;
    z-index: 1000;
}}

.hover-shadow {{
    transition: box-shadow 0.3s ease;
}}

.hover-shadow:hover {{
    box-shadow: 0 8px 25px rgba(0,0,0,0.15) !important;
}}
</style>
{{% endblock %}}'''

        return template

    def _generate_filters_section(self, model_name: str, fields: List[FieldInfo]) -> str:
        """Genera la sección de filtros lateral"""
        model_name_lower = model_name.lower()

        filters_html = '''
    <!-- Panel de filtros -->
    <div class="col-lg-3">
        <form method="GET">'''

        # Generar filtros por ForeignKey
        fk_fields = [f for f in fields if f.field_type == 'ForeignKey']
        for field in fk_fields:
            filters_html += f'''
            <!-- Filtro por {field.verbose_name.lower()} -->
            <div class="filter-panel">
                <div class="filter-header">
                    <button class="btn filter-btn collapsed" type="button" 
                            data-bs-toggle="collapse" data-bs-target="#{field.name}Filter">
                        <div class="d-flex align-items-center">
                            <span class="filter-icon">
                                <i class="fa fa-tag"></i>
                            </span>
                            <span>{field.verbose_name}</span>
                        </div>
                        <i class="fa fa-chevron-down toggle-icon"></i>
                    </button>
                </div>
                <div class="collapse" id="{field.name}Filter">
                    <div class="filter-body">
                        {{% for item in {field.name}s %}}
                        <div class="form-check mb-2">
                            <input class="form-check-input" type="checkbox" value="{{{{ item.id }}}}" 
                                   name="{field.name}" id="{field.name}-{{{{ item.id }}}}">
                            <label class="form-check-label" for="{field.name}-{{{{ item.id }}}}">
                                {{{{ item.name }}}}
                            </label>
                        </div>
                        {{% endfor %}}
                    </div>
                </div>
            </div>'''

        # Generar filtros por campos con choices
        choice_fields = [f for f in fields if f.choices]
        for field in choice_fields:
            filters_html += f'''
            <!-- Filtro por {field.verbose_name.lower()} -->
            <div class="filter-panel">
                <div class="filter-header">
                    <button class="btn filter-btn collapsed" type="button" 
                            data-bs-toggle="collapse" data-bs-target="#{field.name}Filter">
                        <div class="d-flex align-items-center">
                            <span class="filter-icon">
                                <i class="fa fa-filter"></i>
                            </span>
                            <span>{field.verbose_name}</span>
                        </div>
                        <i class="fa fa-chevron-down toggle-icon"></i>
                    </button>
                </div>
                <div class="collapse" id="{field.name}Filter">
                    <div class="filter-body">'''

            for choice_key, choice_value in field.choices:
                filters_html += f'''
                        <div class="form-check mb-2">
                            <input class="form-check-input" type="checkbox" value="{choice_key}" 
                                   name="{field.name}" id="{field.name}-{choice_key}">
                            <label class="form-check-label" for="{field.name}-{choice_key}">
                                {choice_value}
                            </label>
                        </div>'''

            filters_html += '''
                    </div>
                </div>
            </div>'''

        filters_html += f'''
            <div class="filter-actions">
                <button class="btn btn-primary apply-btn" type="submit">
                    <i class="fa fa-filter"></i>Filtrar
                </button>
                <a class="clear-filters" href="{{% url '{model_name_lower}-list' %}}">
                    <i class="fa fa-times-circle"></i>Limpiar
                </a>
            </div>
        </form>
    </div>'''

        return filters_html

    def generate_form_template(self, model_name: str) -> str:
        """Genera el template del formulario (crear/editar)"""
        fields = self._extract_model_fields(model_name)
        model_name_lower = model_name.lower()
        model_verbose = self._get_model_verbose_name(model_name)

        template = f'''{{%% extends "base.html" %%}}
{{% load django_bootstrap5 %}}

{{% block header %}}{{{{ form_title|default:"" }}}} {model_verbose}{{% endblock %}}

{{% block content %}}
<div class="row justify-content-center">
    <div class="col-lg-8">
        <div class="card shadow-sm">
            <div class="card-header bg-primary text-white">
                <h5 class="mb-0">
                    <i class="fa fa-{{{{ form_icon|default:"plus" }}}}"></i>
                    {{{{ form_title|default:"Gestionar" }}}} {model_verbose}
                </h5>
            </div>
            <div class="card-body">
                <form method="post">
                    {{% csrf_token %}}

                    <div class="row">'''

        # Generar campos del formulario
        for i, field in enumerate(fields):
            col_class = "col-md-6" if len(fields) > 4 and field.field_type not in ['TextField'] else "col-12"

            template += f'''
                        <div class="{col_class} mb-3">
                            <label for="id_{field.name}" class="form-label">
                                {field.verbose_name}
                                {"" if field.is_required else " (opcional)"}
                            </label>'''

            if field.field_type == 'TextField':
                template += f'''
                            <textarea class="form-control" name="{field.name}" id="id_{field.name}" 
                                      rows="3" placeholder="{field.help_text or f'Ingrese {field.verbose_name.lower()}'}"
                                      {"required" if field.is_required else ""}>{{{{ form.{field.name}.value|default:"" }}}}</textarea>'''
            elif field.field_type == 'ForeignKey':
                template += f'''
                            <select class="form-select" name="{field.name}" id="id_{field.name}"
                                    {"required" if field.is_required else ""}>
                                <option value="">Seleccione {field.verbose_name.lower()}</option>
                                {{% for option in form.{field.name}.field.queryset %}}
                                <option value="{{{{ option.pk }}}}" 
                                        {{% if form.{field.name}.value == option.pk %}}selected{{% endif %}}>
                                    {{{{ option }}}}
                                </option>
                                {{% endfor %}}
                            </select>'''
            elif field.choices:
                template += f'''
                            <select class="form-select" name="{field.name}" id="id_{field.name}"
                                    {"required" if field.is_required else ""}>
                                <option value="">Seleccione {field.verbose_name.lower()}</option>
                                {{% for key, value in form.{field.name}.field.choices %}}
                                <option value="{{{{ key }}}}" 
                                        {{% if form.{field.name}.value == key %}}selected{{% endif %}}>
                                    {{{{ value }}}}
                                </option>
                                {{% endfor %}}
                            </select>'''
            elif field.field_type in ['DateField', 'DateTimeField']:
                input_type = "datetime-local" if field.field_type == 'DateTimeField' else "date"
                template += f'''
                            <input type="{input_type}" class="form-control" name="{field.name}" 
                                   id="id_{field.name}" value="{{{{ form.{field.name}.value|default:"" }}}}"
                                   {"required" if field.is_required else ""}>'''
            elif field.field_type == 'BooleanField':
                template += f'''
                            <div class="form-check">
                                <input class="form-check-input" type="checkbox" name="{field.name}" 
                                       id="id_{field.name}" value="1"
                                       {{% if form.{field.name}.value %}}checked{{% endif %}}>
                                <label class="form-check-label" for="id_{field.name}">
                                    {field.verbose_name}
                                </label>
                            </div>'''
            else:
                input_type = "number" if field.field_type in ['IntegerField', 'FloatField', 'DecimalField'] else "text"
                step_attr = 'step="0.01"' if field.field_type in ['FloatField', 'DecimalField'] else ''
                max_length_attr = f'maxlength="{field.max_length}"' if field.max_length else ''

                template += f'''
                            <input type="{input_type}" class="form-control" name="{field.name}" 
                                   id="id_{field.name}" value="{{{{ form.{field.name}.value|default:"" }}}}"
                                   placeholder="{field.help_text or f'Ingrese {field.verbose_name.lower()}'}"
                                   {step_attr} {max_length_attr} {"required" if field.is_required else ""}>'''

            if field.help_text:
                template += f'''
                            <div class="form-text">{field.help_text}</div>'''

            template += '''
                        </div>'''

        template += f'''
                    </div>

                    <div class="d-flex justify-content-between mt-4">
                        <a href="{{% url '{model_name_lower}-list' %}}" class="btn btn-secondary">
                            <i class="fa fa-arrow-left"></i> Volver
                        </a>
                        <button type="submit" class="btn btn-primary">
                            <i class="fa fa-save"></i> {{{{ submit_text|default:"Guardar" }}}}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    </div>
</div>
{{% endblock %}}'''

        return template

    def generate_views(self, model_name: str, app_name: str = 'farm') -> str:
        """Genera las vistas para el CRUD"""
        model_name_lower = model_name.lower()

        views_code = f'''from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from .models import {model_name}
from .forms import {model_name}Form


class {model_name}ListView(LoginRequiredMixin, ListView):
    model = {model_name}
    template_name = '{app_name}/{model_name_lower}_list.html'
    context_object_name = '{model_name_lower}s'
    paginate_by = 20

    def get_queryset(self):
        return {model_name}.ownership_objects.filter_by_organization(self.request.user.organization)


class {model_name}CreateView(LoginRequiredMixin, CreateView):
    model = {model_name}
    form_class = {model_name}Form
    template_name = '{app_name}/{model_name_lower}_form.html'
    success_url = reverse_lazy('{model_name_lower}-list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({{
            'form_title': 'Crear',
            'form_icon': 'plus',
            'submit_text': 'Crear'
        }})
        return context

    def form_valid(self, form):
        form.instance.organization = self.request.user.organization
        messages.success(self.request, f'<<ENTIDAD>> creado exitosamente.')
        return super().form_valid(form)

class {model_name}UpdateView(LoginRequiredMixin, UpdateView):
    model = {model_name}
    form_class = {model_name}Form
    template_name = '{app_name}/{model_name_lower}_form.html'
    success_url = reverse_lazy('{model_name_lower}-list')

    def get_queryset(self):
        return {model_name}.ownership_objects.filter_by_organization(self.request.user.organization)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({{
            'form_title': 'Editar',
            'form_icon': 'edit',
            'submit_text': 'Guardar cambios'
        }})
        return context

    def form_valid(self, form):
        messages.success(self.request, f'<<ENTIDAD>> actualizado exitosamente.')
        return super().form_valid(form)

class {model_name}DeleteView(LoginRequiredMixin, DeleteView):
    model = {model_name}
    success_url = reverse_lazy('{model_name_lower}-list')

    def get_queryset(self):
        return {model_name}.ownership_objects.filter_by_organization(self.request.user.organization)

    def delete(self, request, *args, **kwargs):
        messages.success(request, f'<<ENTIDAD>> eliminado exitosamente.')
        return super().delete(request, *args, **kwargs)
'''

        return views_code

    def generate_forms(self, model_name: str) -> str:
        """Genera el formulario para el modelo"""
        fields = self._extract_model_fields(model_name)
        model_name_lower = model_name.lower()

        # Campos que se excluyen del formulario
        excluded_fields = ['organization', 'created_at', 'updated_at']
        form_fields = [f.name for f in fields if f.name not in excluded_fields]

        forms_code = f'''from django import forms
from .models import {model_name}


class {model_name}Form(forms.ModelForm):
    class Meta:
        model = {model_name}
        fields = {form_fields}
        widgets = {{'''

        # Generar widgets específicos para algunos tipos de campo
        for field in fields:
            if field.name in excluded_fields:
                continue

            if field.field_type == 'TextField':
                forms_code += f'''
            '{field.name}': forms.Textarea(attrs={{'rows': 3, 'class': 'form-control'}}),'''
            elif field.field_type == 'DateField':
                forms_code += f'''
            '{field.name}': forms.DateInput(attrs={{'type': 'date', 'class': 'form-control'}}),'''
            elif field.field_type == 'DateTimeField':
                forms_code += f'''
            '{field.name}': forms.DateTimeInput(attrs={{'type': 'datetime-local', 'class': 'form-control'}}),'''

        forms_code += '''
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-control'})
'''

        return forms_code

    def generate_urls(self, model_name: str, app_name: str = 'farm') -> str:
        """Genera las URLs para el CRUD"""
        model_name_lower = model_name.lower()

        urls_code = f'''from django.urls import path
from .views import (
    {model_name}ListView,
    {model_name}CreateView, 
    {model_name}UpdateView,
    {model_name}DeleteView
)

# URLs para {model_name}
urlpatterns = [
    path('admin/{model_name_lower}/', {model_name}ListView.as_view(), name='{model_name_lower}-list'),
    path('admin/{model_name_lower}/create/', {model_name}CreateView.as_view(), name='{model_name_lower}-create'),
    path('admin/{model_name_lower}/<int:pk>/edit/', {model_name}UpdateView.as_view(), name='{model_name_lower}-edit'),
    path('admin/{model_name_lower}/<int:pk>/delete/', {model_name}DeleteView.as_view(), name='{model_name_lower}-delete'),
]
'''

        return urls_code

    def generate_crud_files(self, model_name: str, output_dir: str = "generated_templates",
                            generate_py_files: bool = True):
        """Genera todos los archivos del CRUD"""
        os.makedirs(output_dir, exist_ok=True)

        model_name_lower = model_name.lower()

        # Generar templates
        list_template = self.generate_list_template(model_name)
        with open(f"{output_dir}/{model_name_lower}_list.html", 'w', encoding='utf-8') as f:
            f.write(list_template)

        form_template = self.generate_form_template(model_name)
        with open(f"{output_dir}/{model_name_lower}_form.html", 'w', encoding='utf-8') as f:
            f.write(form_template)

        print(f"✅ Templates generados para {model_name}:")
        print(f"   - {model_name_lower}_list.html")
        print(f"   - {model_name_lower}_form.html")

        # Generar archivos Python si se solicita
        if generate_py_files:
            views_code = self.generate_views(model_name)
            with open(f"{output_dir}/{model_name_lower}_views.py", 'w', encoding='utf-8') as f:
                f.write(views_code)

            forms_code = self.generate_forms(model_name)
            with open(f"{output_dir}/{model_name_lower}_forms.py", 'w', encoding='utf-8') as f:
                f.write(forms_code)

            urls_code = self.generate_urls(model_name)
            with open(f"{output_dir}/{model_name_lower}_urls.py", 'w', encoding='utf-8') as f:
                f.write(urls_code)

            print(f"   - {model_name_lower}_views.py")
            print(f"   - {model_name_lower}_forms.py")
            print(f"   - {model_name_lower}_urls.py")

        print(f"   📁 Guardados en: {output_dir}/")

    def _get_model_verbose_name(self, model_name: str) -> str:
        """Obtiene el nombre legible del modelo"""
        verbose_names = {
            'Field': 'Parcela',
            'Machine': 'Máquina',
            'Product': 'Producto',
            'ProductType': 'Tipo de Producto',
        }
        return verbose_names.get(model_name, model_name)


def main():
    """Función principal para usar el generador"""
    import argparse

    parser = argparse.ArgumentParser(description='Django CRUD Generator')
    parser.add_argument('models_file', help='Ruta al archivo models.py')
    parser.add_argument('model_name', help='Nombre del modelo para generar CRUD')
    parser.add_argument('--output', '-o', default='generated_templates',
                        help='Directorio de salida (default: generated_templates)')
    parser.add_argument('--templates-only', action='store_true',
                        help='Solo generar templates, no archivos Python')

    args = parser.parse_args()

    try:
        generator = DjangoCRUDGenerator(args.models_file)
        generate_py = not args.templates_only
        generator.generate_crud_files(args.model_name, args.output, generate_py)

        if generate_py:
            print(f"\n📝 Para integrar en tu proyecto:")
            print(f"1. Copia las clases de {args.model_name.lower()}_views.py a tus views.py")
            print(f"2. Copia {args.model_name}Form de {args.model_name.lower()}_forms.py a tus forms.py")
            print(f"3. Agrega las URLs de {args.model_name.lower()}_urls.py a tu urlpatterns")

    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    main()

# Ejemplo de uso como módulo:
"""
from django_crud_generator import DjangoCRUDGenerator

generator = DjangoCRUDGenerator('path/to/models.py')

# Solo templates
generator.generate_crud_files('Product', generate_py_files=False)

# CRUD completo (templates + vistas + forms + urls)
generator.generate_crud_files('Product', generate_py_files=True)
"""
