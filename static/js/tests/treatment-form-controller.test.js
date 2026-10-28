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
    assert.match(p.q('#tfMissing').textContent, /^Falta: nombre, parcela, un producto, máquina/);
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

// ── A2: dosis y total son dos inputs siempre visibles; lo último que se toca manda ─────────────────

const total = (p, i) => p.qa('.tf-line')[i || 0].querySelector('[data-role="total"]');
const dose = (p, i) => p.qa('.tf-line')[i || 0].querySelector('[data-role="dose"]');

/** Fertirrigación con Abono (solo fertirrigación): parcela A (4,2 ha). Se añade Mojante tras cambiar de tipo no: usamos Abono. */
function fertigation() {
    const p = create();
    p.q('.tf-seg-btn[data-type="fertigation"]').click();
    p.q('#tfFieldBtn').click();
    p.q('#tfFieldsPop [data-field="1"]').click();
    p.q('#tfFieldBtn').click();
    p.type(p.q('#tfAddInput'), 'abono');
    p.key(p.q('#tfAddInput'), 'Enter');
    p.q('#tfAddClose').click();
    p.type(p.q('#tfName'), 'Abonado');
    return p;
}

test('A2 el total es un input siempre visible, junto a la dosis, con su unidad', () => {
    const p = fertigation();                                  // Abono: 10 L/ha × 4,2 ha
    assert.equal(dose(p).value, '10');
    assert.equal(total(p).value, '42');
    assert.equal(total(p).hidden, false);
    assert.equal(total(p).closest('[hidden]'), null);
    assert.equal(total(p).disabled, false);
    assert.equal(total(p).getAttribute('inputmode'), 'decimal');
    assert.match(p.q('.tf-total-unit').textContent, /^L$/);
});

test('A2 teclear en el total recalcula la dosis EN EL INPUT DE DOSIS sin tocar el total ni perder el foco', () => {
    const p = fertigation();
    const t = total(p);
    t.focus();
    p.type(t, '2');
    p.type(t, '25');
    assert.equal(p.d.activeElement, t);                       // el foco sigue en el total
    assert.equal(t.value, '25');                              // lo tecleado no se reescribe
    assert.equal(dose(p).value, '5,952');                    // 25 / 4,2
    assert.equal(p.T.state.lines[0].override, true);
    assert.match(p.q('.tf-line-notes').textContent, /Total ajustado a mano/);
    assert.ok(p.q('[data-act="clear-total"]'));
});

test('A2 teclear en la dosis recalcula el total en su input y quita el «a mano»', () => {
    const p = fertigation();
    p.type(total(p), '25');
    p.type(dose(p), '11');
    assert.equal(p.d.activeElement, dose(p));
    assert.equal(dose(p).value, '11');
    assert.equal(total(p).value, '46,2');                     // 11 × 4,2
    assert.equal(p.T.state.lines[0].override, false);
    assert.equal(p.q('[data-act="clear-total"]'), null);
});

test('A2 vaciar el total vuelve a calcularlo desde la dosis', () => {
    const p = fertigation();
    p.type(total(p), '25');
    p.type(total(p), '');
    assert.equal(p.T.state.lines[0].override, false);
    assert.equal(dose(p).value, '10');
    assert.equal(p.d.activeElement, total(p));
    p.q('#tfName').focus();                                    // al salir, el total vuelve a enseñar el calculado
    p.w.document.activeElement.dispatchEvent(new p.w.FocusEvent('focusout', { bubbles: true }));
    p.type(p.q('#tfName'), 'Abonado');
    assert.equal(total(p).value, '42');
});

test('A2 «Restablecer dosis» quita el total a mano y pone la dosis recomendada (ronda 4)', () => {
    const p = fertigation();
    p.type(total(p), '25');
    assert.equal(dose(p).value, '5,952');                     // derivada del total
    p.q('[data-act="clear-total"]').focus();                   // como al tocar el botón: el total pierde el foco
    p.q('[data-act="clear-total"]').click();
    assert.equal(p.T.state.lines[0].override, false);
    assert.equal(dose(p).value, '10');                         // recomendada del Abono en fertirrigación (antes: 5,9524 → total 25,0026)
    assert.equal(total(p).value, '42');                        // 10 × 4,2
});

test('A2 con varias parcelas el total es la suma, está deshabilitado y lo explica', () => {
    const p = fertigation();
    p.q('#tfFieldBtn').click();
    p.q('#tfFieldsPop [data-field="2"]').click();
    assert.equal(total(p).disabled, true);
    assert.equal(total(p).value, '62');                        // 10 L/ha × 6,2 ha
    assert.equal(p.q('#tfMultiTotalNote').hidden, false);
    assert.match(p.q('#tfMultiTotalNote').textContent, /Con varias parcelas el total se calcula por parcela/);
    p.q('#tfFieldsPop [data-field="2"]').click();             // desmarca B y vuelve a ser editable
    assert.equal(total(p).disabled, false);
    assert.equal(p.q('#tfMultiTotalNote').hidden, true);
});

test('A2 envío con total a mano: total_overridden=true, total exacto 25.00 y la dosis derivada', () => {
    const p = fertigation();
    p.type(total(p), '25');
    const ev = p.submit();
    assert.equal(ev.defaultPrevented, false);
    assert.equal(p.field(0, 'total_overridden').value, 'true');
    assert.equal(p.field(0, 'total_dose').value, '25.00');
    assert.equal(p.field(0, 'dose').value, '5.952');
    assert.equal(p.q('#id_type').value, 'fertigation');
});

test('A2 editar un tratamiento con total a mano: el input de total lo enseña exacto y la línea sigue «a mano»', () => {
    const p = load('treatment_form_edit.html');
    assert.equal(total(p, 0).value, '12,6');
    assert.equal(total(p, 1).value, '2,1');
    assert.equal(p.T.state.lines[1].override, true);
    assert.equal(p.qa('[data-act="clear-total"]').length, 1);
});

// ── B4: sin Bootstrap (CDN caído) los selectores siguen funcionando con el desplegable ─────────────

test('B4 sin Bootstrap en móvil se usa el desplegable en lugar de la hoja inferior', () => {
    const p = create({ desktop: false });                      // móvil y sin window.bootstrap
    assert.ok(p.q('#tfRoot').classList.contains('tf--nosheet'));
    p.q('#tfFieldBtn').click();
    assert.equal(p.q('#tfFieldsPop').hidden, false);
    p.q('#tfFieldsPop [data-field="1"]').click();
    assert.equal(p.q('#tfFieldTitle').textContent, 'Parcela A');
    p.q('#tfFieldBtn').click();                                // se cierra
    assert.equal(p.q('#tfFieldsPop').hidden, true);
    p.type(p.q('#tfAddInput'), 'fung');                        // productos: el buscador en línea también vale en móvil
    assert.equal(p.q('#tfProductsPop').hidden, false);
    p.key(p.q('#tfAddInput'), 'Enter');
    assert.equal(p.T.state.lines.length, 1);
    p.q('#tfAddBtn').click();                                  // el botón también abre el desplegable
    assert.equal(p.q('#tfProductsPop').hidden, false);
});

test('B4 con Bootstrap en móvil se abre la hoja inferior y el desplegable queda cerrado', () => {
    const shown = [];
    const p = create({ desktop: false, bootstrap: () => ({ Offcanvas: { getOrCreateInstance: (n) => ({ show() { shown.push(n.id); }, hide() {} }) } }) });
    assert.equal(p.q('#tfRoot').classList.contains('tf--nosheet'), false);
    p.q('#tfFieldBtn').click();
    assert.deepEqual(shown, ['tfFieldsSheet']);
    assert.equal(p.q('#tfFieldsPop').hidden, true);
});

test('B4 la plantilla avisa con <noscript> de que hace falta JavaScript', () => {
    assert.match(html('treatment_form_create.html'), /<noscript>[\s\S]*JavaScript[\s\S]*<\/noscript>/);
});

// ── B5: flechas y Intro en el buscador de productos de escritorio ──────────────────────────────────

test('B5 ↓/↑ mueven el resaltado entre los productos válidos y Intro añade el resaltado', () => {
    const p = fill(create());                                   // Fungicida ya añadido
    p.q('#tfAddBtn');                                           // (en escritorio se usa el buscador en línea)
    p.type(p.q('#tfAddInput'), 'i');                            // todos contienen «i» (tipo «Fitosanitario»)
    const names = () => p.qa('#tfProductsPop .tf-opt').map((n) => n.querySelector('.tf-opt-name').textContent);
    const active = () => p.qa('#tfProductsPop .tf-opt').filter((n) => n.dataset.active === 'true').map((n) => n.querySelector('.tf-opt-name').textContent);
    assert.deepEqual(names(), ['Fungicida', 'Insecticida', 'Mojante', 'Abono']);   // válidos primero (A-Z), los que no admiten el tipo al final
    const first = active();
    assert.deepEqual(first, ['Insecticida']);                   // el primero válido que no está ya añadido
    p.key(p.q('#tfAddInput'), 'ArrowDown');
    const second = active();
    assert.equal(second.length, 1);
    assert.notDeepEqual(second, first);
    p.key(p.q('#tfAddInput'), 'ArrowUp');
    assert.deepEqual(active(), first);
    p.key(p.q('#tfAddInput'), 'ArrowDown');
    p.key(p.q('#tfAddInput'), 'Enter');
    const added = p.T.state.lines.map((l) => l.productId);
    assert.equal(added.length, 2);
    assert.notDeepEqual(added, [1, 1]);
});

test('B5 Esc cierra el buscador y Intro sin resultados no hace nada', () => {
    const p = create();
    p.type(p.q('#tfAddInput'), 'zzzz');
    p.key(p.q('#tfAddInput'), 'Enter');
    assert.equal(p.T.state.lines.length, 0);
    p.key(p.q('#tfAddInput'), 'Escape');
    assert.equal(p.q('#tfProductsPop').hidden, true);
});

// ── B10: accesibilidad ─────────────────────────────────────────────────────────────────────────────

test('B10 los errores no son role="alert" (no se anuncian en cada tecla) y las listas son listbox', () => {
    const p = create();
    assert.equal(p.qa('.tf-err[role="alert"]').length, 0);
    assert.ok(p.qa('.tf-err').every((n) => n.getAttribute('aria-live') === 'polite'));
    assert.equal(p.q('#tfMissing').getAttribute('role'), null);
    assert.ok(p.qa('[data-list]').every((n) => n.getAttribute('role') === 'listbox'));
    assert.equal(p.qa('[data-list="fields"]').every((n) => n.getAttribute('aria-multiselectable') === 'true'), true);
});

test('B10 el texto de un error solo se reescribe cuando cambia', () => {
    const p = create();
    p.submit();                                                // intento de guardar: aparecen los errores
    const box = p.q('[data-err="products"]');
    const span = box.querySelector('span');
    assert.ok(span);
    p.type(p.q('#tfName'), 'a');                               // teclear en otro campo no repinta ese error
    assert.equal(box.querySelector('span'), span);
});

// ── Faltas respecto al prototipo ───────────────────────────────────────────────────────────────────

test('Lista de productos: etiqueta «Reciente» y precio por unidad', () => {
    const p = load('treatment_form_edit.html');                // los productos del tratamiento guardado son recientes
    p.type(p.q('#tfAddInput'), 'a');
    const fung = p.qa('#tfProductsPop .tf-opt').find((n) => /Fungicida/.test(n.textContent));
    assert.match(fung.textContent, /Reciente/);
    assert.match(fung.textContent, /9,50 €\/kg/);
});

test('Pie de las hojas: «Listo · N parcelas/productos»', () => {
    const p = create();
    const done = (kind) => p.q('#tfFieldsPop [data-done="fields"]') && p.q('[data-done="' + kind + '"]').textContent;
    assert.equal(p.q('#tfFieldsPop [data-done="fields"]').textContent, 'Listo');
    p.q('#tfFieldBtn').click();
    p.q('#tfFieldsPop [data-field="1"]').click();
    assert.equal(p.q('#tfFieldsPop [data-done="fields"]').textContent, 'Listo · 1 parcela');
    p.q('#tfFieldsPop [data-field="2"]').click();
    assert.equal(p.q('#tfFieldsPop [data-done="fields"]').textContent, 'Listo · 2 parcelas');
    p.q('#tfFieldBtn').click();
    p.type(p.q('#tfAddInput'), 'fung');
    p.key(p.q('#tfAddInput'), 'Enter');
    assert.equal(p.q('#tfProductsSheet [data-done="products"]').textContent, 'Listo · 1 producto');
});

test('Un producto ya añadido pero no válido para el tipo actual se puede quitar desde la lista', () => {
    const p = fill(create());
    p.q('.tf-seg-btn[data-type="fertigation"]').click();       // el fungicida ya no tiene dosis
    p.type(p.q('#tfAddInput'), 'fung');
    const opt = p.q('#tfProductsPop [data-product="1"]');
    assert.equal(opt.disabled, false);
    opt.click();
    assert.equal(p.T.state.lines.length, 0);
});

// ── Ronda 4 (28/10) ───────────────────────────────────────────────────────────────────────────────

/** Pulverización mínima: parcela A + Fungicida + primera máquina (el mojado es el de partida) + nombre. */
function sprayDefault() {
    const p = create();
    p.q('#tfFieldBtn').click();
    p.q('#tfFieldsPop [data-field="1"]').click();
    p.q('#tfFieldBtn').click();
    p.type(p.q('#tfAddInput'), 'fung');
    p.key(p.q('#tfAddInput'), 'Enter');
    p.q('#tfAddClose').click();
    p.q('#tfMachineChips [data-machine="1"]').click();
    return p;
}

test('R4 crear en pulverización: el mojado arranca en 1000 y ya no falta', () => {
    const p = create();
    assert.equal(p.q('#tfWater').value, '1000');
    assert.doesNotMatch(p.q('#tfMissing').textContent, /mojado/);
});

test('R4 editar el total sin tocar el mojado: la dosis y «por máquina» salen calculados', () => {
    const p = sprayDefault();
    p.type(total(p), '25');
    assert.equal(dose(p).value, '5,952');                      // Fungicida kg/1000L: 25 × 1000 / 4200
    assert.match(p.q('.tf-line-load').textContent, /^\d/);       // 25 kg en 4200 L de caldo; cuba de 2000 L = 11,904 kg
    assert.equal(sp(p.q('.tf-line-load').textContent), '11,904 kg');
    assert.match(p.q('.tf-line-hint').textContent, /11,904 kg por máquina/);
});

test('R4 borrar el mojado: aviso en cada línea, ni dosis ni por máquina en blanco sin explicación, y no deja guardar', () => {
    const p = sprayDefault();
    p.type(p.q('#tfName'), 'X');
    p.type(total(p), '25');
    p.type(p.q('#tfWater'), '');
    assert.equal(dose(p).value, '');
    assert.match(p.q('.tf-line-notes').textContent, /Pon el mojado para calcular la dosis/);
    assert.match(p.q('#tfMissing').textContent, /mojado/);
    assert.equal(p.submit().defaultPrevented, true);
    p.type(p.q('#tfWater'), '1000');
    assert.doesNotMatch(p.q('.tf-line-notes').textContent, /Pon el mojado/);
});

test('R4 fertirrigación: ni celda, ni título «por máquina», ni «No aplica», ni el texto del hint', () => {
    const p = fertigation();
    assert.equal(p.q('.tf-line-load').hidden, true);
    assert.equal(p.q('#tfLoadHead').hidden, true);
    assert.equal(p.q('#tfLoadHead').textContent, '');
    assert.ok(p.q('#tfRoot').classList.contains('tf--ferti'));   // la rejilla de escritorio quita la columna (sin hueco)
    const all = p.q('#tfLines').textContent + p.q('.tf-lines-head').textContent;
    assert.doesNotMatch(all, /No aplica|máquina|cuba/i);
    p.q('.tf-seg-btn[data-type="spraying"]').click();           // y al volver a pulverización reaparece
    assert.equal(p.q('#tfRoot').classList.contains('tf--ferti'), false);
});

test('R4 pulverización con máquina: «Por máquina» en la cabecera y en el hint móvil', () => {
    const p = sprayDefault();
    assert.equal(p.q('#tfLoadHead').textContent, 'Por máquina');
    assert.equal(p.q('#tfLoadHead').hidden, false);
    assert.equal(p.q('.tf-line-load').hidden, false);
    assert.match(p.q('.tf-line-hint').textContent, /6 kg por máquina/);   // 3 kg/1000L × 2000 L
    assert.doesNotMatch(p.q('#tfSecProducts').textContent, /cuba llena/);
    assert.match(p.q('#tfLoadsHead').textContent, /Cuba 2000/);          // el resumen de cubas no se toca
});

test('R4 «Total ajustado a mano» + «Restablecer dosis»: pone la dosis recomendada y el total desde ella', () => {
    const p = sprayDefault();
    p.type(dose(p), '4');
    p.type(total(p), '25');
    assert.match(p.q('.tf-line-notes').textContent, /Total ajustado a mano/);
    assert.doesNotMatch(p.q('.tf-line-notes').textContent, /Volver a calcularlo|la dosis se calcula a partir/);
    const btn = p.q('[data-act="clear-total"]');
    assert.equal(btn.textContent, 'Restablecer dosis');
    btn.focus();
    btn.click();
    assert.equal(p.T.state.lines[0].override, false);
    assert.equal(dose(p).value, '3');                             // recomendada del Fungicida
    assert.equal(total(p).value, '12,6');                         // 3 × 4,2
    assert.equal(p.q('[data-act="clear-total"]'), null);
});

test('R4 la unidad va siempre junto a la dosis y el total, y la dosis es la del producto', () => {
    const p = sprayDefault();
    assert.equal(p.q('.tf-line-dose .tf-unit').textContent, 'kg/1000L');
    assert.equal(p.q('.tf-total-unit').textContent, 'kg');
    assert.match(p.q('.tf-line-hint').textContent, /Recomendada 3 kg\/1000L/);
    assert.doesNotMatch(p.q('#tfSecProducts').textContent, /dosis de la parcela|dosis por parcela/i);
});

test('R4 el nombre es lo primero de la pantalla, sin enfoque automático, y su error lleva el foco', () => {
    const p = create();
    const main = p.q('.tf-main');
    assert.equal(main.firstElementChild.id, 'tfSecName');
    const pos = (sel) => p.q(sel).compareDocumentPosition(p.q('#tfSecField')) & p.w.Node.DOCUMENT_POSITION_FOLLOWING;
    assert.ok(pos('#tfSecName'), 'el nombre va antes que Tipo/Parcela en el DOM (tabulación y lector de pantalla)');
    assert.notEqual(p.d.activeElement, p.q('#tfName'));
    assert.equal(p.qa('#tfSecName').length, 1);                   // y no queda otra sección Nombre al final
    assert.equal(p.q('#tfName').getAttribute('aria-describedby') || '', '');
    const f = fill(create());
    f.type(f.q('#tfName'), '');
    assert.equal(f.submit().defaultPrevented, true);
    assert.equal(f.d.activeElement, f.q('#tfName'));              // el primer error es el nombre: se enfoca (y se sube a él)
    assert.match(f.q('[data-err="name"]').textContent, /nombre/);
    assert.match(f.q('#tfMissing').textContent, /^Falta: nombre/);
});

test('R4 en edición el nombre guardado se mantiene', () => {
    const p = load('treatment_form_edit.html');
    assert.ok(p.q('#tfName').value.length > 0);
    assert.equal(p.q('#tfName').value, p.q('#id_name').value);
});
