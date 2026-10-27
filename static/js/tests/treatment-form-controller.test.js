/**
 * Controlador del formulario (static/js/treatment-form.js) sobre el HTML real de la página de alta
 * (fixtures/treatment_form_create.html: render de Django con 2 parcelas, 2 máquinas y 2 productos).
 * Para regenerar el fixture: renderizar treatment-create con ese juego de datos.
 */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');

const HTML = fs.readFileSync(path.join(__dirname, 'fixtures', 'treatment_form_create.html'), 'utf8');
const JS = ['treatment-calc.js', 'treatment-form-state.js', 'treatment-form.js']
    .map((f) => fs.readFileSync(path.join(__dirname, '..', f), 'utf8'));

function load() {
    const dom = new JSDOM(HTML, { runScripts: 'outside-only', pretendToBeVisual: true });
    const w = dom.window;
    w.matchMedia = () => ({ matches: true, addEventListener() {}, removeEventListener() {} });
    Object.defineProperty(w.HTMLElement.prototype, 'offsetParent', { get() { return this.parentNode; } });
    w.Element.prototype.scrollIntoView = function () {};
    JS.forEach((code) => w.eval(code));
    const d = w.document;
    const q = (s) => d.querySelector(s);
    const type = (input, value) => { input.value = value; input.dispatchEvent(new w.Event('input', { bubbles: true })); };
    const submit = () => { const ev = new w.Event('submit', { bubbles: true, cancelable: true }); q('#treatmentForm').dispatchEvent(ev); return ev; };
    return { w, d, q, type, submit, T: w.__treatmentForm };
}

function fill(p) {
    p.q('#tfFieldBtn').click();
    p.q('#tfFieldsPop [data-field]').click();
    p.q('#tfFieldBtn').click();
    p.type(p.q('#tfAddInput'), 'fung');
    p.q('#tfAddInput').dispatchEvent(new p.w.KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
    p.q('#tfAddClose').click();
    p.q('#tfMachineChips .tf-chip').click();
    p.type(p.q('#tfWater'), '1000');
}

test('arranca vacío y dice qué falta', () => {
    const p = load();
    assert.match(p.q('#tfMissing').textContent, /^Falta: parcela, un producto, máquina, mojado, nombre/);
    assert.equal(p.q('#tfSumMain').textContent, '— €');
    assert.equal(p.q('#tfSave').textContent.replace(/\u00a0/g, ' '), 'Crear tratamiento');
});

test('flujo completo: parcela, producto, máquina y mojado dan coste y escriben los inputs reales al enviar', () => {
    const p = fill_(load());
    assert.equal(p.q('#tfMissing').textContent, '');
    assert.match(p.q('#tfSumMain').textContent, /€/);
    const ev = p.submit();
    assert.equal(ev.defaultPrevented, false);
    assert.equal(p.q('#id_type').value, 'spraying');
    assert.equal(p.q('#id_water_per_ha').value, '1000');
    assert.equal(p.q('#id_name').value, 'Fungicida');
    assert.equal(p.d.getElementById('id_treatmentproduct_set-TOTAL_FORMS').value, '1');
    assert.equal(p.q('[name="treatmentproduct_set-0-dose"]').value, '3.000');
    assert.equal(p.q('[name="treatmentproduct_set-0-position"]').value, '0');
    assert.equal(p.q('[name="treatmentproduct_set-0-total_overridden"]').value, 'false');
});

test('con datos incompletos bloquea el envío, marca las secciones y pone el foco en la primera', () => {
    const p = load();
    const ev = p.submit();
    assert.equal(ev.defaultPrevented, true);
    assert.ok(p.q('#tfSecField').classList.contains('tf-card--err'));
    assert.match(p.q('[data-err="products"]').textContent, /al menos un producto/);
});

test('varias parcelas: botón «Crear N tratamientos», nota y extra_fields', () => {
    const p = fill_(load());
    p.q('#tfFieldBtn').click();
    p.d.querySelectorAll('#tfFieldsPop [data-field]')[1].click();
    assert.equal(p.q('#tfSave').textContent.replace(/\u00a0/g, ' '), 'Crear 2 tratamientos');
    assert.equal(p.q('#tfMultiNote').hidden, false);
    p.submit();
    assert.equal(Array.from(p.q('#id_extra_fields').selectedOptions).length, 1);
});

test('total a mano: recalcula dosis y coste; «Volver a calcularlo» lo quita', () => {
    const p = fill_(load());
    p.q('[data-act="edit-total"]').click();
    p.type(p.q('[data-role="total"]'), '10,5');
    assert.equal(p.T.state.lines[0].override, true);
    assert.match(p.q('.tf-line-cost').textContent, /99,75/);
    p.q('[data-role="total"]').dispatchEvent(new p.w.FocusEvent('focusout', { bubbles: true }));
    p.q('[data-act="clear-total"]').click();
    assert.equal(p.T.state.lines[0].override, false);
});

test('fertirrigación oculta máquina y mojado y avisa del producto sin dosis', () => {
    const p = fill_(load());
    p.q('.tf-seg-btn[data-type="fertigation"]').click();
    assert.equal(p.q('#tfSecApp').hidden, true);
    assert.match(p.q('.tf-line-notes').textContent, /no tiene dosis para fertirrigación/);
});

test('Intro en un campo no envía el formulario', () => {
    const p = load();
    const ev = new p.w.KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true });
    p.q('#tfName').dispatchEvent(ev);
    assert.equal(ev.defaultPrevented, true);
});

function fill_(p) { fill(p); return p; }
