import os
import re
import pytest
from django.conf import settings
from django.urls import get_resolver


# TODO: borrar cuando estén los tests de las vistas. Serían redundantes, porque si la vista renderiza bien, todo está OK

def get_class_from_callback(callback):
    # Si es un método de clase as_view()
    view_class = getattr(callback, 'view_class', None)
    if view_class:
        return view_class
    # Si es función, no hay clase
    return None


@pytest.mark.django_db
def test_templates_exist():
    template_dir = settings.TEMPLATES[0]['DIRS'][0]
    resolver = get_resolver()

    def check_patterns(patterns):
        for pattern in patterns:
            callback = getattr(pattern, 'callback', None)
            if not callback:
                # Puede ser un include (URLResolver), se revisan sus patrones recursivamente
                if hasattr(pattern, 'url_patterns'):
                    check_patterns(pattern.url_patterns)
                continue

            view_class = get_class_from_callback(callback)
            if not view_class:
                continue  # No clase, salta

            template_name = getattr(view_class, 'template_name', None)
            if not template_name and hasattr(view_class, 'get_template_names'):
                try:
                    instance = view_class()
                    template_names = instance.get_template_names()
                    template_name = template_names[0] if template_names else None
                except Exception:
                    template_name = None

            if template_name:
                template_path = os.path.join(template_dir, template_name)
                assert os.path.isfile(
                    template_path), f"Template '{template_name}' no encontrado para la vista '{view_class.__name__}'"

    check_patterns(resolver.url_patterns)


@pytest.mark.django_db
def test_included_templates_exist():
    template_dir = settings.TEMPLATES[0]['DIRS'][0]
    include_pattern = re.compile(r"{%\s*include\s+'([^']+)'\s*%}")
    missing_templates = []

    for root, _, files in os.walk(template_dir):
        for file in files:
            if not file.endswith('.html'):
                continue
            path = os.path.join(root, file)
            with open(path, encoding='utf-8') as f:
                content = f.read()
            includes = include_pattern.findall(content)
            for tpl in includes:
                included_path = os.path.join(template_dir, tpl)
                if not os.path.isfile(included_path):
                    missing_templates.append((file, tpl))

    assert not missing_templates, f"Faltan templates incluidos: {missing_templates}"
