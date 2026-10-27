/**
 * Controlador del formulario (static/js/treatment-form.js) ejecutado de verdad con jsdom sobre HTML real
 * de la plantilla (static/js/tests/fixtures/*.html, generados por farm/tests/test_form_page_fixtures.py,
 * que falla si quedan desactualizados).
 *
 * Datos del fixture: parcelas A (id 1, 4,2 ha) y B (id 2, 2 ha); máquinas Cuba 2000 (id 1) y Cuba 1000 (id 2);
 * productos Fungicida (1, 3 kg/1000L, 9,50 €), Insecticida (2, 0,5 L/1000L, 10 €), Abono (3, solo fertirrigación),
 * Mojante (4, 1,5 L/ha, 6 €). «Hoy» es 2030-06-15.
 */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');

const read = (f) => fs.readFileSync(path.join(__dirname, f), 'utf8');
const JS = ['../treatment-calc.js', '../treatment-form-state.js', '../treatment-form.js'].map(read);
const PAGES = {};
const html = (name) => (PAGES[name] = PAGES[name] || read('fixtures/' + name));

/** Carga una página y ejecuta el JS real. opts.bootstrap: false para simular que no cargó Bootstrap (CDN caído). */
function load(name, opts) {
    opts = opts || {};
    const dom = new JSDOM(html(name), { runScripts: 'outside-only', pretendToBeVisual: true });
    const w = dom.window;
    w.matchMedia = () => ({ matches: opts.desktop !== false, addEventListener() {}, removeEventListener() {} });
    Object.defineProperty(w.HTMLElement.prototype, 'offsetParent', { get() { return this.parentNode; } });
    w.Element.prototype.scrollIntoView = function () {};
    if (opts.bootstrap) w.bootstrap = opts.bootstrap(w);
    JS.forEach((code) => w.eval(code));
    const d = w.document;
    const q = (s) => d.querySelector(s);
    const qa = (s) => Array.from(d.querySelectorAll(s));
    const type = (input, value) => { input.focus(); input.value = value; input.dispatchEvent(new w.Event('input', { bubbles: true })); };
    const key = (target, k) => { const ev = new w.KeyboardEvent('keydown', { key: k, bubbles: true, cancelable: true }); target.dispatchEvent(ev); return ev; };
    const submit = () => { const ev = new w.Event('submit', { bubbles: true, cancelable: true }); q('#treatmentForm').dispatchEvent(ev); return ev; };
    const row = (i) => q('#tfRows').querySelectorAll('[data-row]')[i];
    const field = (i, name) => row(i).querySelector('[name$="-' + name + '"]');
    return { w, d, q, qa, type, key, submit, row, field, T: w.__treatmentForm };
}

const create = (opts) => load('treatment_form_create.html', opts);
const sp = (s) => s.replace(/ /g, ' ');

/** Parcela A + Fungicida + primera máquina + mojado 1000 + nombre: lo mínimo para poder guardar. */
function fill(p) {
    p.q('#tfFieldBtn').click();
    p.q('#tfFieldsPop [data-field="1"]').click();
    p.q('#tfFieldBtn').click();
    p.type(p.q('#tfAddInput'), 'fung');
    p.key(p.q('#tfAddInput'), 'Enter');
    p.q('#tfAddClose').click();
    p.q('#tfMachineChips [data-machine="1"]').click();
    p.type(p.q('#tfWater'), '1000');
    p.type(p.q('#tfName'), 'Mi tratamiento');
    return p;
}

test('arranca vacío, con el nombre sin rellenar, y dice qué falta', () => {
    const p = create();
    assert.equal(p.q('#tfName').value, '');
    assert.match(p.q('#tfMissing').textContent, /^Falta: parcela, un producto, máquina, mojado, nombre/);
    assert.equal(p.q('#tfSumMain').textContent, '— €');
    assert.equal(sp(p.q('#tfSave').textContent), 'Crear tratamiento');
});

test('flujo completo: da coste y escribe en los inputs reales del formset lo que luego recibe el servidor', () => {
    const p = fill(create());
    assert.equal(p.q('#tfMissing').textContent, '');
    assert.match(p.q('#tfSumMain').textContent, /119,70/);
    const ev = p.submit();
    assert.equal(ev.defaultPrevented, false);
    assert.equal(p.q('#id_type').value, 'spraying');
    assert.equal(p.q('#id_field').value, '1');
    assert.equal(p.q('#id_machine').value, '1');
    assert.equal(p.q('#id_water_per_ha').value, '1000');
    assert.equal(p.q('#id_name').value, 'Mi tratamiento');
    assert.equal(p.d.getElementById('id_treatmentproduct_set-TOTAL_FORMS').value, '1');
    assert.equal(p.field(0, 'product').value, '1');
    assert.equal(p.field(0, 'dose').value, '3.000');
    assert.equal(p.field(0, 'total_dose').value, '12.6000');
    assert.equal(p.field(0, 'position').value, '0');
    assert.equal(p.field(0, 'total_overridden').value, 'false');
    assert.equal(p.field(0, 'DELETE').checked, false);
});

test('con datos incompletos bloquea el envío, marca las secciones y explica qué falta', () => {
    const p = create();
    const ev = p.submit();
    assert.equal(ev.defaultPrevented, true);
    assert.ok(p.q('#tfSecField').classList.contains('tf-card--err'));
    assert.ok(p.q('#tfSecName').classList.contains('tf-card--err'));
    assert.match(p.q('[data-err="products"]').textContent, /al menos un producto/);
    assert.match(p.q('[data-err="name"]').textContent, /nombre/);
});

test('varias parcelas: botón «Crear N tratamientos», nota y extra_fields', () => {
    const p = fill(create());
    p.q('#tfFieldBtn').click();
    p.q('#tfFieldsPop [data-field="2"]').click();
    assert.equal(sp(p.q('#tfSave').textContent), 'Crear 2 tratamientos');
    assert.equal(p.q('#tfMultiNote').hidden, false);
    p.submit();
    assert.deepEqual(Array.from(p.q('#id_extra_fields').selectedOptions).map((o) => o.value), ['2']);
    assert.equal(p.field(0, 'total_dose').value, '');           // con varias parcelas el servidor calcula cada una
});

test('fertirrigación oculta máquina y mojado y avisa del producto sin dosis', () => {
    const p = fill(create());
    p.q('.tf-seg-btn[data-type="fertigation"]').click();
    assert.equal(p.q('#tfSecApp').hidden, true);
    assert.match(p.q('.tf-line-notes').textContent, /no tiene dosis para fertirrigación/);
});

test('Intro en un campo no envía el formulario', () => {
    const p = create();
    assert.equal(p.key(p.q('#tfName'), 'Enter').defaultPrevented, true);
});

// ── B1: valores del servidor con punto decimal («1.500» es uno y medio, no mil quinientos) ─────────────

test('B1 tras un envío fallido, una dosis «1.500» del servidor sigue siendo válida y se puede guardar', () => {
    const p = load('treatment_form_bound.html');
    const mojante = p.q('.tf-line[data-key="2"]');
    assert.equal(mojante.querySelector('[data-role="dose"]').value, '1,5');               // se enseña con coma
    assert.equal(mojante.classList.contains('tf-line--bad'), false);
    assert.doesNotMatch(p.q('[data-err="products"]').textContent, /dosis/);
    assert.match(p.q('[data-err="name"]').textContent, /obligatorio|nombre/i);            // el error que sí hay
    p.type(p.q('#tfName'), 'Ya con nombre');
    assert.equal(p.q('#tfMissing').textContent, '');
    const ev = p.submit();
    assert.equal(ev.defaultPrevented, false);
    assert.equal(p.field(1, 'dose').value, '1.500');
    assert.equal(p.field(1, 'total_dose').value, '6.3000');
});

test('B1 editar: dosis guardada de 3 decimales ≥ 1 y total a mano exacto cargados sin perder valor', () => {
    const p = load('treatment_form_edit.html');
    const doses = p.qa('[data-role="dose"]').map((i) => i.value);
    assert.deepEqual(doses, ['3', '0,5', '1,5']);
    assert.equal(p.qa('.tf-line--bad').length, 0);
    assert.equal(p.T.state.lines[1].override, true);
    assert.equal(p.q('#tfMissing').textContent, '');
});

test('B1 lo que teclea el usuario sigue sin aceptar «1.500»: pide la coma', () => {
    const p = fill(create());
    p.type(p.q('[data-role="dose"]'), '1.500');
    assert.equal(p.submit().defaultPrevented, true);
    assert.match(p.q('[data-err="products"]').textContent, /coma/);
});
