import os
import re

from django.conf import settings
from django.test import TestCase
from django.urls import get_resolver, reverse


class UrlNamesInTemplatesTest(TestCase):

    def extract_url_names_from_templates(self):
        url_names = set()
        template_dir = settings.TEMPLATES[0]['DIRS'][0]  # Ajusta esto según tu configuración de plantillas

        # Recorre todos los archivos .html en el directorio de plantillas
        for root, dirs, files in os.walk(template_dir):
            for file in files:
                if file.endswith('.html'):
                    with open(os.path.join(root, file), 'r', encoding='utf-8') as template_file:
                        content = template_file.read()
                        # Busca todas las etiquetas {% url 'name' %}
                        matches = re.findall(r"{%\s*url\s+'([^']+)'\s*%}", content)
                        url_names.update(matches)

        return url_names

    def test_all_urls_in_templates_exist(self):
        url_names = self.extract_url_names_from_templates()
        url_resolver = get_resolver()

        # Comprobar que cada nombre de URL realmente existe en la configuración de URLs
        for name in url_names:
            with self.subTest(name=name):
                try:
                    # Intenta hacer reverse para ver si el nombre de URL está registrado
                    reverse(name)
                except Exception:
                    self.fail(f"La URL con el nombre '{name}' no está definida en 'urls.py'.")
