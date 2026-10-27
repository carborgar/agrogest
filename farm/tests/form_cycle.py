"""
Ciclo completo del formulario de tratamiento en los tests: teclear → guardar → reabrir → guardar sin tocar.

Un test que solo mira la base de datos no detecta los fallos que ve el usuario (el total que se recalcula solo, 50 L
que al volver a entrar salen como 49,99). Por eso estos tests:

  1. cargan el HTML REAL de la vista (GET con el cliente de Django) en jsdom, ejecutan el JS REAL y simulan lo que
     teclea el usuario; lo que el controlador escribe en los inputs del formulario es lo que se envía con un POST real;
  2. comprueban lo guardado en la base de datos contra valores calculados A MANO en el propio test;
  3. reabren la pantalla de edición y leen lo que MUESTRAN los inputs visibles (texto exacto, coma decimal es-ES);
  4. guardan sin tocar nada (POST con lo que escribe el controlador al reabrir) y exigen que la base de datos quede
     idéntica, tres veces seguidas, para detectar deriva.

Cómo se ejecuta: con `pytest` como siempre. El arnés es un proceso Node (farm/tests/js_harness/form_harness.js, usa
jsdom de node_modules) que arranca una vez y atiende todas las sesiones por stdin/stdout. Si no hay Node o no están
instaladas las dependencias (`npm install`), los tests se SALTAN con el motivo (skip explícito, nunca un pass silencioso).
"""
import atexit
import json
import os
import shutil
import subprocess
import unittest
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import Organization
from farm.models import Field, Machine, Product, ProductType, Treatment, TreatmentProduct

ROOT = Path(__file__).resolve().parents[2]
HARNESS = Path(__file__).parent / 'js_harness' / 'form_harness.js'
User = get_user_model()


def node_unavailable_reason():
    if not shutil.which('node'):
        return 'No hay Node en el PATH: los tests del ciclo del formulario necesitan Node + jsdom'
    if not (ROOT / 'node_modules' / 'jsdom').exists():
        return 'Falta jsdom en node_modules: ejecuta `npm install`'
    return None


class _Harness:
    """Proceso Node único (se arranca al primer uso y se cierra al terminar)."""
    proc = None

    @classmethod
    def request(cls, payload):
        if cls.proc is None or cls.proc.poll() is not None:
            cls.proc = subprocess.Popen(['node', str(HARNESS)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        text=True, encoding='utf-8', cwd=str(ROOT))
            atexit.register(cls.close)
        cls.proc.stdin.write(json.dumps(payload) + '\n')
        cls.proc.stdin.flush()
        line = cls.proc.stdout.readline()
        if not line:
            raise AssertionError('El arnés de Node se ha cerrado sin responder')
        return json.loads(line)

    @classmethod
    def close(cls):
        if cls.proc is not None and cls.proc.poll() is None:
            cls.proc.stdin.close()
            cls.proc.wait(timeout=10)
        cls.proc = None


# ── Formato como lo ve el usuario (es-ES) ─────────────────────────────────────

def es(value, max_decimals=4):
    """Número → texto como lo enseña el formulario: coma decimal, sin miles, sin ceros finales (máx. 4 decimales)."""
    d = Decimal(str(value))
    d = d.quantize(Decimal(1).scaleb(-max_decimals), rounding=ROUND_HALF_EVEN)
    text = format(d, 'f')
    if '.' in text:
        text = text.rstrip('0').rstrip('.')
    return text.replace('.', ',')


def eur(value):
    """Importe → «1234,50 €» (es-ES: sin separador de miles por debajo de 10.000; espacio duro antes del €)."""
    d = Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_EVEN)
    whole, frac = format(abs(d), 'f').split('.')
    if len(whole) >= 5:
        whole = '{:,}'.format(int(whole)).replace(',', '.')
    return ('-' if d < 0 else '') + whole + ',' + frac + ' €'


# ── Pasos de teclado (los interpreta el arnés) ────────────────────────────────

def S_type(value):
    return {'op': 'kind', 'value': value}


def S_fields(*ids):
    return {'op': 'fields', 'ids': list(ids)}


def S_product(pid):
    return {'op': 'product', 'id': pid}


def S_set(field, value):
    return {'op': 'set', 'field': field, 'value': str(value)}


def S_dose(n, value):
    return {'op': 'dose', 'n': n, 'value': str(value)}


def S_total(n, value):
    return {'op': 'total', 'n': n, 'value': str(value)}


def S_machine(mid):
    return {'op': 'machine', 'id': mid}


def S_date(value):
    return {'op': 'date', 'value': value}


def S_done(value=True):
    return {'op': 'done', 'value': value}


def S_partial(value):
    return {'op': 'partial', 'value': str(value) if value else False}


def S_clear_total(n):
    return {'op': 'clearTotal', 'n': n}


def S_remove(n):
    return {'op': 'removeLine', 'n': n}


SUBMIT = {'op': 'submit'}


class FormCycleTestCase(TestCase):
    """Escenario base: organización, parcelas de 4,2 / 2,8 / 6,5 / 1,1 ha, dos máquinas y un producto de cada tipo de dosis."""

    @classmethod
    def setUpClass(cls):
        reason = node_unavailable_reason()
        if reason:
            raise unittest.SkipTest(reason)
        super().setUpClass()

    def setUp(self):
        self.org = Organization.objects.create(name='Org ciclo')
        self.user = User.objects.create_user(username='ciclo', email='ciclo@example.com', password='x', organization=self.org)
        self.client.force_login(self.user)
        mk_field = lambda name, area: Field.objects.create(name=name, area=area, crop='Olivo', planting_year=2020, organization=self.org)
        self.fA, self.fB, self.fC, self.fD = (mk_field('A 4,2', 4.2), mk_field('B 2,8', 2.8), mk_field('C 6,5', 6.5), mk_field('D 1,1', 1.1))
        self.m2000 = Machine.objects.create(name='Cuba 2000', type='Pulverizador', capacity=2000, organization=self.org)
        self.m1000 = Machine.objects.create(name='Cuba 1000', type='Pulverizador', capacity=1000, organization=self.org)
        ptype = ProductType.objects.create(name='Fito', organization=self.org)

        def prod(name, price, **kw):
            return Product.objects.create(name=name, product_type=ptype, price=Decimal(price), organization=self.org, **kw)
        self.pPct = prod('Aceite %', '8.95', spraying_dose=Decimal('0.5'), spraying_dose_type='pct')
        self.pL1000 = prod('Insecticida L/1000L', '10.00', spraying_dose=Decimal('0.5'), spraying_dose_type='l_per_1000l')
        self.pKg1000 = prod('Cobre kg/1000L', '9.50', spraying_dose=Decimal('3'), spraying_dose_type='kg_per_1000l')
        self.pKgHa = prod('Abono foliar kg/ha', '1.80', spraying_dose=Decimal('3'), spraying_dose_type='kg_per_ha')
        self.pLHa = prod('Foliar L/ha', '5.00', spraying_dose=Decimal('2'), spraying_dose_type='l_per_ha',
                         fertigation_dose=Decimal('10'), fertigation_dose_type='l_per_ha')
        self.pFerti = prod('Nitrato kg/ha', '1.20', fertigation_dose=Decimal('40'), fertigation_dose_type='kg_per_ha')
        self.create_url = reverse('treatment-create')

    # ── Navegador simulado ────────────────────────────────────────────────────

    def edit_url(self, t):
        return reverse('treatment-edit', kwargs={'pk': t.pk})

    def play(self, html, steps, desktop=True):
        """Ejecuta el JS real sobre `html` con estos pasos de teclado. Devuelve (vista, POST o None, bloqueado)."""
        res = _Harness.request({'html': html, 'steps': steps, 'desktop': desktop})
        if not res['ok']:
            raise AssertionError('Fallo en el arnés jsdom:\n' + res['error'])
        post = None
        if res.get('post') is not None:
            post = {}
            for name, value in res['post']:
                if name in post:
                    post[name] = (post[name] if isinstance(post[name], list) else [post[name]]) + [value]
                else:
                    post[name] = value
        return res['view'], post, res['prevented']

    def open_create(self):
        response = self.client.get(self.create_url)
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def open_edit(self, t):
        response = self.client.get(self.edit_url(t))
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def type_and_save_new(self, steps, desktop=True):
        """Teclear en el formulario de alta y enviar con el POST real. Devuelve (tratamiento, vista)."""
        view, post, prevented = self.play(self.open_create(), list(steps) + [SUBMIT], desktop)
        self.assertFalse(prevented, f'El formulario no dejó guardar. Errores: {view["errors"]}. Falta: {view["missing"]}')
        before = set(Treatment.objects.values_list('pk', flat=True))
        response = self.client.post(self.create_url, post)
        self.assertEqual(response.status_code, 302, self._form_errors(response))
        new = Treatment.objects.exclude(pk__in=before)
        return new.order_by('pk').first(), view

    def type_and_save_edit(self, t, steps, desktop=True):
        view, post, prevented = self.play(self.open_edit(t), list(steps) + [SUBMIT], desktop)
        self.assertFalse(prevented, f'El formulario no dejó guardar. Errores: {view["errors"]}. Falta: {view["missing"]}')
        response = self.client.post(self.edit_url(t), post)
        self.assertEqual(response.status_code, 302, self._form_errors(response))
        t.refresh_from_db()
        return t, view

    @staticmethod
    def _form_errors(response):
        ctx = getattr(response, 'context', None)
        return ctx and ctx.get('form_errors')

    # ── Base de datos ─────────────────────────────────────────────────────────

    TREATMENT_FIELDS = ('name', 'type', 'date', 'finish_date', 'status', 'field_id', 'machine_id', 'water_per_ha',
                        'real_water_per_ha', 'applied_area', 'zone_notes')
    LINE_FIELDS = ('id', 'product_id', 'dose', 'dose_type', 'total_dose', 'total_dose_unit', 'unit_price',
                   'total_price', 'price_per_ha', 'total_overridden', 'position')

    def db_snapshot(self, t):
        """Todo lo guardado (salvo marcas de tiempo): dos snapshots iguales = la base de datos quedó idéntica."""
        t = Treatment.objects.get(pk=t.pk)
        return {
            'treatment': {f: getattr(t, f) for f in self.TREATMENT_FIELDS},
            'lines': [{f: getattr(tp, f) for f in self.LINE_FIELDS} for tp in t.treatmentproduct_set.order_by('position')],
        }

    def assert_db(self, t, n=1, *, dose, total, override, unit_price, total_price, per_ha, context=''):
        """Valores guardados de la línea n frente a los calculados A MANO en el test (Decimal exactos)."""
        tp = self.line(t, n)
        got = (tp.dose, tp.total_dose, tp.total_overridden, tp.unit_price, tp.total_price, tp.price_per_ha)
        want = (Decimal(dose), Decimal(total), override, Decimal(unit_price), Decimal(total_price), Decimal(per_ha))
        self.assertEqual(got, want, f'{context} línea {n}: guardado (dosis, total, a mano, precio, coste, €/ha)={got}, esperado={want}')

    def line(self, t, n=1):
        return Treatment.objects.get(pk=t.pk).treatmentproduct_set.order_by('position')[n - 1]

    # ── Lo que la pantalla tiene que mostrar al reabrir ───────────────────────

    def assert_screen_shows_saved(self, t, view, typed=None, context=''):
        """Lo que muestran los inputs visibles al reabrir es EXACTAMENTE lo guardado (texto exacto)."""
        t = Treatment.objects.get(pk=t.pk)
        lines = list(t.treatmentproduct_set.order_by('position'))
        self.assertEqual(len(view['lines']), len(lines), f'{context}: líneas en pantalla distintas de las guardadas')
        for n, (tp, shown) in enumerate(zip(lines, view['lines']), start=1):
            tag = f'{context} línea {n} ({shown["name"]})' + (f' tecleado={typed}' if typed is not None else '')
            self.assertEqual(shown['dose'], es(tp.dose), f'{tag}: dosis guardada={tp.dose}, mostrada={shown["dose"]}')
            self.assertEqual(shown['total'], es(tp.total_dose), f'{tag}: total guardado={tp.total_dose}, mostrado={shown["total"]}')
            self.assertEqual(shown['cost'], eur(tp.total_price), f'{tag}: coste guardado={tp.total_price}, mostrado={shown["cost"]}')
            self.assertEqual(shown['manual'], tp.total_overridden, f'{tag}: «a mano» guardado={tp.total_overridden}, mostrado={shown["manual"]}')
            if t.type == 'spraying':
                per_load = tp.get_dose_per_load()
                want = '—' if per_load is None else es(per_load) + ' ' + tp.total_dose_unit
                self.assertEqual(shown['perLoad'].replace(' ', ' '), want.replace(' ', ' '),
                                 f'{tag}: por cuba guardado={per_load}, mostrado={shown["perLoad"]}')
        total_cost = sum(tp.total_price for tp in lines)
        self.assertEqual(view['sumMain'], eur(total_cost), f'{context}: coste total guardado={total_cost}, mostrado={view["sumMain"]}')

    def assert_cycle_is_idempotent(self, t, cycles=3, typed=None, context=''):
        """Abrir → comprobar pantalla → guardar sin tocar → la base de datos queda idéntica (y así `cycles` veces)."""
        before = self.db_snapshot(t)
        for i in range(1, cycles + 1):
            view, post, prevented = self.play(self.open_edit(t), [SUBMIT])
            self.assertFalse(prevented, f'{context} ciclo {i}: no dejó guardar sin tocar nada. Errores: {view["errors"]}')
            self.assert_screen_shows_saved(t, view, typed, f'{context} ciclo {i}')
            response = self.client.post(self.edit_url(t), post)
            self.assertEqual(response.status_code, 302, f'{context} ciclo {i}: {self._form_errors(response)}')
            after = self.db_snapshot(t)
            self.assertEqual(after, before, f'{context} ciclo {i}: guardar sin tocar nada cambió la base de datos (deriva)')

    def assert_detail_matches(self, t):
        """El detalle tras guardar enseña los mismos totales y costes que el formulario."""
        t = Treatment.objects.get(pk=t.pk)
        response = self.client.get(reverse('treatment-detail', kwargs={'pk': t.pk}))
        self.assertEqual(response.status_code, 200)
        lines = list(t.treatmentproduct_set.order_by('position'))
        self.assertEqual([p.pk for p in response.context['products']], [tp.pk for tp in lines])
        self.assertEqual(response.context['total_cost'], sum(tp.total_price for tp in lines))
        view, _, _ = self.play(self.open_edit(t), [])
        self.assertEqual(view['sumMain'], eur(response.context['total_cost']),
                         f'Detalle={response.context["total_cost"]}, formulario={view["sumMain"]}')
        # El detalle enseña cada línea con su total a 2 decimales, el coste y los €/ha: los mismos valores guardados
        import re
        text = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', response.content.decode())).replace('\u00a0', ' ')
        for tp in lines:
            total2 = {es(Decimal(tp.total_dose).quantize(Decimal('0.01'), rounding=r), 2) for r in (ROUND_HALF_EVEN, ROUND_HALF_UP)}
            total2 = {(x if ',' in x else x + ',00') if len(x.split(',')[-1:][0]) == 2 or ',' not in x else x + '0' for x in total2}
            self.assertTrue(any(f'{x} {tp.total_dose_unit}' in text for x in total2),
                            f'El detalle no enseña el total {tp.total_dose} {tp.total_dose_unit} (esperado como {sorted(total2)})')
            for label, value in (('coste', tp.total_price), ('€/ha', tp.price_per_ha)):
                self.assertIn(eur(value).replace('\u00a0', ' '), text, f'El detalle no enseña el {label} {value}')
