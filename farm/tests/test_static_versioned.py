from django.template import Context, Template
from django.test import TestCase


class StaticVersionedTests(TestCase):
    def render(self, path):
        return Template("{% load static_versioned %}{% static_v '" + path + "' %}").render(Context())

    def test_anade_hash_del_contenido(self):
        url = self.render('js/treatment-form.js')
        self.assertRegex(url, r'^/static/js/treatment-form\.js\?v=[0-9a-f]{10}$')

    def test_mismo_contenido_mismo_hash(self):
        self.assertEqual(self.render('js/treatment-form.js'), self.render('js/treatment-form.js'))

    def test_fichero_inexistente_no_rompe(self):
        self.assertEqual(self.render('js/no-existe.js'), '/static/js/no-existe.js')

    def test_la_pagina_del_formulario_usa_url_versionada(self):
        import re
        from pathlib import Path
        html = (Path(__file__).resolve().parents[2] / 'templates/farm/treatments/treatment_form.html').read_text()
        self.assertEqual(len(re.findall(r"static_v 'js/treatment-", html)), 3)
