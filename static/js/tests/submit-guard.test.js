// Ejecutar con: npm run test:js
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM, VirtualConsole } = require('jsdom');

const SCRIPT = fs.readFileSync(path.join(__dirname, '..', 'submit-guard.js'), 'utf8');

function setup(html) {
    const vc = new VirtualConsole(); // silencia "not implemented: navigation"
    const dom = new JSDOM(`<!DOCTYPE html><body>${html}</body>`, {
        runScripts: 'outside-only', virtualConsole: vc, pretendToBeVisual: true,
    });
    const { window } = dom;
    // Contador de envíos reales: sustituye al submit nativo ANTES de cargar el guard.
    window.__sent = 0;
    window.HTMLFormElement.prototype.submit = function () { window.__sent++; };
    window.eval(SCRIPT);
    // Se registra DESPUÉS del guard (mismo nodo, orden de registro): cuenta los
    // envíos que el guard no ha cancelado y evita la navegación de jsdom.
    window.document.addEventListener('submit', (e) => {
        if (!e.defaultPrevented) window.__sent++;
        e.preventDefault();
    });
    return window;
}

const tick = () => new Promise((r) => setTimeout(r, 5));

test('clic repetido en un form POST solo envía una vez y bloquea el botón', async () => {
    const w = setup('<form method="post" id="f"><button type="submit" id="b">Guardar</button></form>');
    const b = w.document.getElementById('b');
    b.click(); await tick();
    b.click(); b.click(); await tick();
    assert.equal(w.__sent, 1);
    assert.equal(b.disabled, true);
    assert.ok(b.innerHTML.includes('spinner-border'));
});

test('form.submit() programático duplicado solo envía una vez', () => {
    const w = setup('<form method="post" id="f"><button type="submit">x</button></form>');
    const f = w.document.getElementById('f');
    f.submit(); f.submit(); f.submit();
    assert.equal(w.__sent, 1);
});

test('si una validación hace preventDefault, el form NO queda bloqueado', async () => {
    const w = setup('<form method="post" id="f"><button type="submit" id="b">Guardar</button></form>');
    const f = w.document.getElementById('f');
    let valid = false;
    f.addEventListener('submit', (e) => { if (!valid) e.preventDefault(); });
    const b = w.document.getElementById('b');
    b.click(); await tick();
    assert.equal(w.__sent, 0);
    assert.equal(b.disabled, false);
    assert.equal(f.dataset.submitting, undefined);
    valid = true;
    b.click(); await tick();
    assert.equal(w.__sent, 1);
});

test('los formularios GET no se protegen', async () => {
    const w = setup('<form method="get" id="f"><button type="submit" id="b">Filtrar</button></form>');
    const b = w.document.getElementById('b');
    b.click(); await tick();
    b.click(); await tick();
    assert.equal(w.__sent, 2);
    assert.equal(b.disabled, false);
});

test('data-no-guard desactiva la protección', () => {
    const w = setup('<form method="post" data-no-guard id="f"></form>');
    const f = w.document.getElementById('f');
    f.submit(); f.submit();
    assert.equal(w.__sent, 2);
});

test('pageshow persistido (botón atrás) restaura el formulario', async () => {
    const w = setup('<form method="post" id="f"><button type="submit" id="b">Guardar</button></form>');
    const b = w.document.getElementById('b');
    b.click(); await tick();
    assert.equal(b.disabled, true);
    const ev = new w.Event('pageshow'); ev.persisted = true;
    w.dispatchEvent(ev);
    assert.equal(b.disabled, false);
    assert.equal(b.innerHTML, 'Guardar');
});
