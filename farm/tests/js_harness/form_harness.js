/**
 * Arnés jsdom del formulario de tratamiento para los tests de Python (farm/tests/form_cycle.py).
 *
 * Proceso largo: lee de stdin una petición JSON por línea y responde con una línea JSON.
 *   petición: {html, steps: [...], desktop?: bool}
 *   respuesta: {ok, view, post?, prevented?, error?}
 *
 * Carga el HTML REAL que renderiza Django, ejecuta el JS REAL (treatment-calc.js, treatment-form-state.js,
 * treatment-form.js), simula lo que hace el usuario (steps) y devuelve:
 *   - view: lo que MUESTRAN los inputs y textos visibles (antes de enviar),
 *   - post: lo que enviaría el navegador (todos los campos con nombre del formulario tras el submit, con los
 *           valores que escribe el controlador en los inputs reales), y si el envío quedó bloqueado.
 * No calcula nada por su cuenta: solo teclea, hace clic y lee.
 */
const fs = require('node:fs');
const path = require('node:path');
const readline = require('node:readline');

const ROOT = path.resolve(__dirname, '..', '..', '..');
const { JSDOM } = require(path.join(ROOT, 'node_modules', 'jsdom'));
const SRC = ['treatment-calc.js', 'treatment-form-state.js', 'treatment-form.js']
    .map((f) => fs.readFileSync(path.join(ROOT, 'static', 'js', f), 'utf8'));

function run(req) {
    const dom = new JSDOM(req.html, { runScripts: 'outside-only', pretendToBeVisual: true });
    const w = dom.window;
    w.matchMedia = () => ({ matches: req.desktop !== false, addEventListener() {}, removeEventListener() {} });
    Object.defineProperty(w.HTMLElement.prototype, 'offsetParent', { get() { return this.parentNode; } });
    w.Element.prototype.scrollIntoView = function () {};
    SRC.forEach((code) => w.eval(code));
    const d = w.document;
    const q = (s) => d.querySelector(s);
    const qa = (s) => Array.from(d.querySelectorAll(s));
    const must = (s) => { const n = q(s); if (!n) throw new Error('No existe ' + s); return n; };
    const ev = (el, type, init) => el.dispatchEvent(new w.Event(type, Object.assign({ bubbles: true, cancelable: true }, init)));
    const typeInto = (el, value) => { el.focus(); el.value = value; ev(el, 'input'); };
    const line = (n) => {
        const l = qa('.tf-line')[n - 1];
        if (!l) throw new Error('No existe la línea ' + n);
        return l;
    };
    const T = w.__treatmentForm;

    const pickerOpen = (id) => !must(id).hidden;
    const SEL = {
        name: '#tfName', water: '#tfWater', realWater: '#tfRealWater', area: '#tfArea', zone: '#tfZone',
        finish: '#tfFinish', customDate: '#tfCustomDate',
    };

    let post = null;
    let prevented = null;
    let view = null;

    const ops = {
        type: (s) => typeInto(must(s.sel), s.value),
        click: (s) => must(s.sel).click(),
        key: (s) => must(s.sel).dispatchEvent(new w.KeyboardEvent('keydown', { key: s.key, bubbles: true, cancelable: true })),
        blur: (s) => { const el = must(s.sel); el.blur(); ev(el, 'focusout'); },
        set: (s) => typeInto(must(SEL[s.field]), s.value),
        kind: (s) => must('.tf-seg-btn[data-type="' + s.value + '"]').click(),
        machine: (s) => must('#tfMachineChips [data-machine="' + s.id + '"]').click(),
        date: (s) => { must('#tfDateChips [data-date="custom"]').click(); typeInto(must('#tfCustomDate'), s.value); },
        done: (s) => { if ((must('#tfDone').getAttribute('aria-checked') === 'true') !== !!s.value) must('#tfDone').click(); },
        partial: (s) => {
            if (s.value) { must('#tfPartialOpen').click(); typeInto(must('#tfArea'), s.value); } else must('#tfPartialClose').click();
        },
        // Parcelas: deja marcadas exactamente `ids` (en alta se acumulan; en edición se sustituye)
        fields: (s) => {
            if (!pickerOpen('#tfFieldsPop')) must('#tfFieldBtn').click();
            const now = T.state.fieldIds.slice();
            if (T.state.mode === 'edit') {
                if (now[0] !== s.ids[0]) must('#tfFieldsPop [data-field="' + s.ids[0] + '"]').click();
            } else {
                const toggle = now.filter((i) => s.ids.indexOf(i) < 0).concat(s.ids.filter((i) => now.indexOf(i) < 0));
                toggle.forEach((i) => must('#tfFieldsPop [data-field="' + i + '"]').click());
            }
            if (pickerOpen('#tfFieldsPop')) must('#tfFieldBtn').click();
        },
        product: (s) => {
            typeInto(must('#tfAddInput'), s.query || ' ');
            must('#tfProductsPop [data-product="' + s.id + '"]').click();
            must('#tfAddClose').click();
        },
        removeLine: (s) => must('.tf-line:nth-child(' + s.n + ') [data-act="remove"]').click(),
        dose: (s) => typeInto(line(s.n).querySelector('[data-role="dose"]'), s.value),
        total: (s) => typeInto(line(s.n).querySelector('[data-role="total"]'), s.value),
        clearTotal: (s) => line(s.n).querySelector('[data-act="clear-total"]').click(),
        submit: () => {
            view = snapshot();
            const e = new w.Event('submit', { bubbles: true, cancelable: true });
            must('#treatmentForm').dispatchEvent(e);
            prevented = e.defaultPrevented;
            if (!prevented) post = formData();
        },
    };

    function formData() {
        const pairs = [];
        Array.from(must('#treatmentForm').elements).forEach((el) => {
            if (!el.name || el.disabled) return;
            const t = el.type;
            if (t === 'submit' || t === 'button') return;
            if ((t === 'checkbox' || t === 'radio') && !el.checked) return;
            if (el.tagName === 'SELECT' && el.multiple) {
                Array.from(el.selectedOptions).forEach((o) => pairs.push([el.name, o.value]));
                return;
            }
            pairs.push([el.name, el.value]);
        });
        return pairs;
    }

    function snapshot() {
        const txt = (s) => { const n = q(s); return n ? n.textContent : null; };
        const chip = (s) => qa(s).filter((n) => n.getAttribute('aria-checked') === 'true').map((n) => n.textContent.trim());
        return {
            type: qa('.tf-seg-btn').filter((b) => b.getAttribute('aria-pressed') === 'true').map((b) => b.dataset.type)[0],
            fieldTitle: txt('#tfFieldTitle'), fieldSub: txt('#tfFieldSub'),
            name: must('#tfName').value, water: must('#tfWater').value,
            machine: chip('#tfMachineChips .tf-chip').concat(q('#tfMachineSingle') && !q('#tfMachineSingle').hidden ? [txt('#tfMachineName')] : []),
            date: must('#tfCustomDate').value, dateChip: chip('#tfDateChips .tf-chip'),
            done: must('#tfDone').getAttribute('aria-checked') === 'true',
            finish: must('#tfFinish').value, realWater: must('#tfRealWater').value,
            area: must('#tfArea').value, zone: must('#tfZone').value, partialVisible: !must('#tfPartial').hidden,
            lines: qa('.tf-line').map((l) => ({
                name: l.querySelector('.tf-line-name').textContent,
                dose: l.querySelector('[data-role="dose"]').value,
                total: l.querySelector('[data-role="total"]').value,
                totalDisabled: l.querySelector('[data-role="total"]').disabled,
                unit: l.querySelector('.tf-line-dose .tf-unit').textContent,
                totalUnit: l.querySelector('.tf-total-unit').textContent,
                perLoad: l.querySelector('.tf-line-load').textContent,
                cost: l.querySelector('.tf-line-cost').textContent,
                hint: l.querySelector('.tf-line-hint').textContent,
                notes: l.querySelector('.tf-line-notes').textContent,
                manual: !!l.querySelector('[data-act="clear-total"]'),
                bad: l.classList.contains('tf-line--bad'),
            })),
            loadsHead: txt('#tfLoadsHead'), loadRows: qa('#tfLoadRows .tf-loads-row').map((n) => n.textContent),
            sumMain: txt('#tfSumMain'), sumSub: txt('#tfSumSub'), missing: txt('#tfMissing'), save: txt('#tfSave'),
            errors: qa('[data-err]').map((n) => [n.dataset.err, n.textContent]).filter((p) => p[1]),
            state: JSON.parse(JSON.stringify(T.state)),
        };
    }

    (req.steps || []).forEach((s, i) => {
        if (!ops[s.op]) throw new Error('Paso desconocido: ' + s.op);
        try { ops[s.op](s); } catch (e) { throw new Error('Paso ' + (i + 1) + ' (' + JSON.stringify(s) + '): ' + e.message); }
    });
    if (view === null) view = snapshot();
    const out = { ok: true, view: view, prevented: prevented, post: post };
    dom.window.close();
    return out;
}

const rl = readline.createInterface({ input: process.stdin });
rl.on('line', (line) => {
    let res;
    try { res = run(JSON.parse(line)); } catch (e) { res = { ok: false, error: String(e && e.stack || e) }; }
    process.stdout.write(JSON.stringify(res) + '\n');
});
