/**
 * Controlador del formulario de tratamiento (crear/editar).
 *
 * - Lee los datos del servidor (json_script) y los valores iniciales de los inputs reales de Django.
 * - Mantiene el estado con TreatmentFormState (puro, probado) y lo pinta con render().
 * - Justo antes de enviar escribe los valores normalizados (punto decimal) en los inputs reales:
 *   el servidor sigue recibiendo un POST de formulario normal y es la fuente de verdad de los cálculos.
 * - Sin alert(): los errores salen de derive() (cliente) y del servidor (por sección o línea).
 */
(function () {
    'use strict';

    const S = window.TreatmentFormState;
    const C = window.TreatmentCalc;
    const root = document.getElementById('tfRoot');
    if (!root || !S || !C) return;

    // ── Utilidades ────────────────────────────────────────────────────────────

    const $ = (id) => document.getElementById(id);
    const readJson = (id) => { const el = $(id); return el ? JSON.parse(el.textContent) : null; };
    const nf = (n, d) => n.toLocaleString('es-ES', { minimumFractionDigits: 0, maximumFractionDigits: d === undefined ? 2 : d });
    const eur = (n) => n.toLocaleString('es-ES', { style: 'currency', currency: 'EUR' });
    const numText = (n, d) => (n === null || n === undefined || !Number.isFinite(n) ? '' :
        n.toLocaleString('es-ES', { useGrouping: false, minimumFractionDigits: 0, maximumFractionDigits: d }));
    const cap1 = (s) => s.charAt(0).toUpperCase() + s.slice(1);
    const plural = (n, one, many) => (n === 1 ? one : many);
    const norm = (s) => String(s).normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
    const isDesktop = () => window.matchMedia('(min-width: 992px)').matches;
    // Hojas inferiores = offcanvas de Bootstrap. Si no cargó (CDN caído, mala cobertura), el desplegable vale también en móvil
    const hasSheets = () => !!(window.bootstrap && window.bootstrap.Offcanvas);
    const usePop = () => isDesktop() || !hasSheets();
    const visible = (el) => !!el && !el.hidden && el.offsetParent !== null;

    function setText(el, text) { if (el.textContent !== text) el.textContent = text; }
    function setVal(input, text) { if (document.activeElement !== input && input.value !== text) input.value = text; }
    function setHidden(el, hidden) { if (el.hidden !== !!hidden) el.hidden = !!hidden; }
    function el(tag, attrs, text) {
        const node = document.createElement(tag);
        Object.keys(attrs || {}).forEach((k) => node.setAttribute(k, attrs[k]));
        if (text !== undefined) node.textContent = text;
        return node;
    }

    // Fechas ISO (YYYY-MM-DD) sin problemas de zona horaria
    const fromIso = (s) => { const p = s.split('-'); return new Date(+p[0], +p[1] - 1, +p[2], 12); };
    const toIso = (d) => d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
    const addDays = (iso, n) => { const d = fromIso(iso); d.setDate(d.getDate() + n); return toIso(d); };
    const daysBetween = (a, b) => Math.round((fromIso(b) - fromIso(a)) / 86400000);
    const longDate = (iso) => cap1(new Intl.DateTimeFormat('es-ES', { weekday: 'long', day: 'numeric', month: 'long' }).format(fromIso(iso)));
    const shortDate = (iso) => new Intl.DateTimeFormat('es-ES', { day: 'numeric', month: 'short' }).format(fromIso(iso));
    const weekdayShort = (iso) => cap1(new Intl.DateTimeFormat('es-ES', { weekday: 'short', day: 'numeric' }).format(fromIso(iso)).replace(',', '').replace('.', ''));

    // ── Datos y elementos ─────────────────────────────────────────────────────

    const data = readJson('treatment-form-data');
    const serverErrors = readJson('treatment-form-errors');
    const isEdit = root.dataset.edit === '1';
    const form = $('treatmentForm');
    const PREFIX = 'treatmentproduct_set';

    const real = {
        name: $('id_name'), type: $('id_type'), date: $('id_date'), field: $('id_field'), machine: $('id_machine'),
        water: $('id_water_per_ha'), finish: $('id_finish_date'), realWater: $('id_real_water_per_ha'),
        area: $('id_applied_area'), zone: $('id_zone_notes'), extra: $('id_extra_fields'),
        total: form.elements[PREFIX + '-TOTAL_FORMS'], initialForms: form.elements[PREFIX + '-INITIAL_FORMS'],
    };
    const ui_ = {
        status: $('tfStatus'), banner: $('tfBanner'),
        segBtns: Array.from(root.querySelectorAll('.tf-seg-btn')),
        fieldBtn: $('tfFieldBtn'), fieldTitle: $('tfFieldTitle'), fieldSub: $('tfFieldSub'), fieldLbl: $('tfFieldLbl'),
        multiNote: $('tfMultiNote'), partialOpen: $('tfPartialOpen'), partial: $('tfPartial'), area: $('tfArea'), zone: $('tfZone'),
        lines: $('tfLines'), multiTotalNote: $('tfMultiTotalNote'), orderHint: $('tfOrderHint'), totalHead: $('tfTotalHead'), loadHead: $('tfLoadHead'),
        addBtn: $('tfAddBtn'), addLabel: $('tfAddLabel'), addInput: $('tfAddInput'), addClose: $('tfAddClose'),
        secApp: $('tfSecApp'), machineChips: $('tfMachineChips'), machineSingle: $('tfMachineSingle'),
        machineName: $('tfMachineName'), machineCap: $('tfMachineCap'), water: $('tfWater'),
        loads: $('tfLoads'), loadsHead: $('tfLoadsHead'), loadRows: $('tfLoadRows'),
        dateTitle: $('tfDateTitle'), dateChips: $('tfDateChips'), customDate: $('tfCustomDate'), dateLong: $('tfDateLong'),
        done: $('tfDone'), doneFields: $('tfDoneFields'), finish: $('tfFinish'), realWrap: $('tfRealWrap'), realWater: $('tfRealWater'),
        name: $('tfName'),
        summary: $('tfSummary'), sumMain: $('tfSumMain'), sumSub: $('tfSumSub'), kv: $('tfKv'), missing: $('tfMissing'), save: $('tfSave'),
    };
    const SECTIONS = ['name', 'field', 'products', 'application', 'date'];    // orden de la pantalla
    const sectionEl = { field: $('tfSecField'), products: $('tfSecProducts'), application: $('tfSecApp'), date: $('tfSecDate'), name: $('tfSecName') };
    const errEl = {};
    SECTIONS.forEach((s) => { errEl[s] = sectionEl[s].querySelector('[data-err="' + s + '"]'); });

    // ── Estado inicial: valores de los inputs reales (valores guardados o POST fallido) ──

    const TRUE_RE = /^(true|on|1)$/i;
    let rowsInfo = [];     // filas iniciales del formset: {row, id, productId}
    let rowToKey = {};     // índice de fila → key de línea (para los errores del servidor)

    function readInitial() {
        const type = real.type.value === 'fertigation' ? 'fertigation' : 'spraying';
        const fieldIds = real.field.value ? [Number(real.field.value)] : [];
        if (real.extra) {
            Array.from(real.extra.selectedOptions).forEach((o) => { if (o.value && Number(o.value) !== fieldIds[0]) fieldIds.push(Number(o.value)); });
        }
        // Los valores del servidor llevan SIEMPRE punto decimal («1.500» = uno y medio): parser estricto y texto con
        // coma para el estado. Lo que teclea el usuario se interpreta con otras reglas (parseNumber).
        const fromServer = (v) => {
            const x = C.parseServerNumber(v);
            return x === null ? (v === undefined || v === null ? '' : String(v)) : C.numberToText(x, 4);
        };
        const n = (v) => { const x = C.parseServerNumber(v); return x && x > 0 ? String(Math.round(x)) : ''; };
        const savedLines = data.lines || [];

        const lines = [];
        const rows = Array.from($('tfRows').querySelectorAll('[data-row]'));
        const initialCount = Number(real.initialForms.value) || 0;
        rowsInfo = [];
        rows.forEach((row, i) => {
            const q = (suffix) => row.querySelector('[name$="-' + suffix + '"]');
            const productId = Number(q('product').value) || null;
            const id = q('id').value;
            if (i < initialCount) rowsInfo.push({ row: row, id: id, productId: productId });
            else row.remove();                       // las filas nuevas del POST fallido se reconstruyen desde el estado
            if (!productId || q('DELETE').checked) return;
            const saved = id ? savedLines.find((l) => l.product_id === productId) : null;
            const override = TRUE_RE.test(q('total_overridden').value);
            // Con total a mano guardado se usa el valor exacto (el input solo enseña 2 decimales)
            const total = override && saved && !data.bound ? saved.total_dose : q('total_dose').value;   // exacto (el input solo enseña 2 decimales)
            rowToKey[i] = lines.length + 1;
            lines.push({ productId: productId, dose: fromServer(q('dose').value), override: override, total: fromServer(total), unitPrice: saved ? saved.unit_price : null });
        });
        real.total.value = String(rowsInfo.length);

        return {
            isEdit: isEdit, type: type, fieldIds: fieldIds, machineId: real.machine.value || null,
            water: n(real.water.value), date: real.date.value || data.today, finishDate: real.finish.value || '',
            realWater: n(real.realWater.value), appliedArea: fromServer(real.area.value), zone: real.zone.value,
            name: real.name.value, lines: lines,
        };
    }

    let state = S.initialState(data, readInitial());

    // ── Errores del servidor ──────────────────────────────────────────────────

    const SECTION_OF = {
        type: 'field', field: 'field', extra_fields: 'field', applied_area: 'field', zone_notes: 'field',
        machine: 'application', water_per_ha: 'application',
        date: 'date', finish_date: 'date', real_water_per_ha: 'date', name: 'name',
    };
    const srv = { sections: {}, lines: {}, general: [] };
    if (serverErrors) {
        Object.keys(serverErrors.form).forEach((f) => {
            const sec = SECTION_OF[f] || 'field';
            (srv.sections[sec] = srv.sections[sec] || []).push.apply(srv.sections[sec], serverErrors.form[f]);
        });
        srv.general = serverErrors.non_field.slice();
        if (serverErrors.formset.non_form.length) srv.sections.products = serverErrors.formset.non_form.slice();
        Object.keys(serverErrors.formset.lines).forEach((i) => {
            const key = rowToKey[i];
            const msgs = [];
            Object.keys(serverErrors.formset.lines[i]).forEach((f) => { if (f !== 'DELETE') msgs.push.apply(msgs, serverErrors.formset.lines[i][f]); });
            if (key) srv.lines[key] = msgs;
            else if (msgs.length) (srv.sections.products = srv.sections.products || []).push.apply(srv.sections.products, msgs);
        });
        state = S.actions.markTried(state);
    }

    // ── Estado de la interfaz (no es del formulario) ─────────────────────────

    const uiState = { picker: null, fieldsQuery: '', productsQuery: '', hi: -1, customDate: false };

    function dispatch(type, payload) {
        // Directo a la acción: el payload de setType usa la clave `type` y chocaría con la del reduce
        const next = S.actions[type](state, payload || {}, data);
        if (next !== state) { state = next; render(); }
    }

    const lineEls = new Map();

    window.__treatmentForm = { get state() { return state; }, get ui() { return uiState; }, dispatch: dispatch };   // para pruebas

    // ── Pintado ───────────────────────────────────────────────────────────────

    const LINE_HTML =
        '<span class="tf-line-num" aria-hidden="true"></span>' +
        '<div class="tf-line-prod"><div class="tf-line-name"></div><div class="tf-line-sub"><span class="tf-type"></span><span class="tf-rec"></span></div></div>' +
        '<button type="button" class="tf-icon-btn tf-line-remove" data-act="remove"><i class="bi bi-x-lg" aria-hidden="true"></i></button>' +
        '<div class="tf-line-dose"><span class="tf-cap">Dosis</span><span class="tf-inline"><input type="text" class="tf-inp tf-num" inputmode="decimal" autocomplete="off" data-role="dose"><span class="tf-unit"></span></span>' +
        '<div class="tf-line-hint"></div></div>' +
        '<div class="tf-line-load"></div>' +
        '<div class="tf-line-tot"><div class="tf-line-totalcell"><span class="tf-cap tf-cap-total"></span>' +
        '<span class="tf-inline"><input type="text" class="tf-inp tf-num" inputmode="decimal" autocomplete="off" data-role="total"><span class="tf-unit tf-total-unit"></span></span></div>' +
        '<div class="tf-line-cost"></div></div>' +
        '<div class="tf-line-notes"></div>';

    function createLine(key) {
        const node = el('div', { 'class': 'tf-line', 'data-key': String(key) });
        node.innerHTML = LINE_HTML;
        const q = (s) => node.querySelector(s);
        return {
            node: node, num: q('.tf-line-num'), name: q('.tf-line-name'), type: q('.tf-type'), rec: q('.tf-rec'),
            remove: q('[data-act="remove"]'), dose: q('[data-role="dose"]'), unit: q('.tf-line-dose .tf-unit'),
            load: q('.tf-line-load'), capTotal: q('.tf-cap-total'), total: q('[data-role="total"]'), totalUnit: q('.tf-total-unit'),
            cost: q('.tf-line-cost'), hint: q('.tf-line-hint'), notes: q('.tf-line-notes'), notesSig: null,
        };
    }

    function costText(l) {
        switch (l.costState) {
            case 'pick-field': return 'Elige parcela';
            case 'missing-water': return 'Falta el mojado';
            case 'invalid-dose': return '—';
            case 'no-price': return 'Sin precio';
            default: return eur(l.cost);
        }
    }

    function paintLine(refs, l, d, serverMsgs) {
        const tried = state.tried;
        const bad = !l.supported || (tried && !l.valid);
        refs.node.classList.toggle('tf-line--bad', bad);
        refs.node.classList.toggle('tf-line--err', !!(serverMsgs && serverMsgs.length));
        setText(refs.num, String(l.number));
        setText(refs.name, l.name);
        setText(refs.type, l.typeName);
        refs.remove.setAttribute('aria-label', 'Quitar ' + l.name);

        // Avisos de la línea: solo se reconstruyen si cambian (para no perder el clic en «Restablecer dosis»)
        const notes = [];
        const supported = l.supported;
        refs.dose.closest('.tf-line-dose').hidden = !supported;
        refs.total.closest('.tf-line-tot').hidden = !supported;
        refs.load.hidden = !supported || !d.isSpray;          // «por máquina»: solo pulverización
        if (!supported) {
            setText(refs.rec, '');
            setText(refs.hint, '');
            notes.push(['tf-note-warn', l.unsupportedMessage]);
        } else {
            const own = state.lines.find((x) => x.key === l.key);
            // Lo que se está tecleando no se reescribe (setVal respeta el foco); el otro campo se rederiva
            setVal(refs.dose, l.override ? S.doseToText(l.dose) : own.dose);
            refs.dose.setAttribute('aria-label', 'Dosis de ' + l.name);
            refs.dose.setAttribute('aria-invalid', String(!!(tried && !l.valid)));
            refs.dose.classList.toggle('tf-inp--warn', l.warn);
            setText(refs.unit, l.unit);
            setText(refs.rec, ' · recomendada ' + nf(l.recommended, 4) + ' ' + l.unit);

            setText(refs.capTotal, d.multi ? 'Total (' + d.fieldCount + ' parcelas)' : 'Total parcela');
            setVal(refs.total, l.override ? own.total : C.numberToText(l.total, 2));
            refs.total.disabled = !d.single;
            refs.total.title = d.single ? '' : 'Con varias parcelas el total se calcula por parcela';
            refs.total.setAttribute('aria-label', 'Total de ' + l.name + (d.multi ? ' (suma de las parcelas)' : ''));
            refs.total.setAttribute('aria-invalid', String(!!(tried && l.override && !l.valid)));
            setText(refs.totalUnit, l.totalUnit);
            setText(refs.cost, costText(l));
            setText(refs.load, d.isSpray ? (l.perLoad !== null ? nf(l.perLoad, 4) + ' ' + l.totalUnit : '—') : '');
            let hint = 'Recomendada ' + nf(l.recommended, 4) + ' ' + l.unit;
            if (l.perLoad !== null) hint += ' · ' + nf(l.perLoad, 4) + ' ' + l.totalUnit + ' por máquina';
            setText(refs.hint, hint);

            if (l.warn) notes.push(['tf-note-warn', 'Se aparta bastante de la recomendada. Revísala.']);
            if (l.doseRoundedUp && !l.override) notes.push(['', 'Se redondea hacia arriba a ' + nf(l.dose, 3) + ' ' + l.unit + '.']);
            if (l.needsWater) notes.push(['tf-note-warn', 'Pon el mojado para calcular la dosis.']);
            if (l.override) notes.push(['tf-note-manual', 'Total ajustado a mano.', true]);
        }
        (serverMsgs || []).forEach((m) => notes.push(['tf-note-err', m]));

        const sig = JSON.stringify(notes);
        if (refs.notesSig !== sig) {
            refs.notesSig = sig;
            refs.notes.textContent = '';
            notes.forEach((n) => {
                const p = el('p', { 'class': n[0] }, n[1] + (n[2] ? ' ' : ''));
                if (n[2]) p.appendChild(el('button', { type: 'button', 'class': 'tf-link', 'data-act': 'clear-total' }, 'Restablecer dosis'));
                refs.notes.appendChild(p);
            });
        }
    }

    function paintLines(d) {
        const keep = new Set();
        d.lines.forEach((l, i) => {
            keep.add(l.key);
            let refs = lineEls.get(l.key);
            if (!refs) { refs = createLine(l.key); lineEls.set(l.key, refs); }
            paintLine(refs, l, d, srv.lines[l.key]);
            if (ui_.lines.children[i] !== refs.node) ui_.lines.insertBefore(refs.node, ui_.lines.children[i] || null);
        });
        Array.from(lineEls.keys()).forEach((key) => {
            if (!keep.has(key)) { lineEls.get(key).node.remove(); lineEls.delete(key); }
        });
        setHidden(ui_.orderHint, d.lines.length < 2 || !d.isSpray);
        setHidden(ui_.multiTotalNote, !(d.multi && d.lines.length));
        setText(ui_.totalHead, d.multi ? 'Total (' + d.fieldCount + ' parcelas)' : 'Total parcela');
        setText(ui_.loadHead, d.isSpray ? 'Por máquina' : '');
        setHidden(ui_.loadHead, !d.isSpray);
        root.classList.toggle('tf--ferti', !d.isSpray);      // la rejilla de escritorio quita la columna sin dejar hueco
        setText(ui_.addLabel, d.lines.length ? 'Añadir otro producto' : 'Añadir producto');
    }

    function paintField(d) {
        ui_.segBtns.forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.type === state.type)));
        setText(ui_.fieldLbl, isEdit ? 'Parcela' : 'Parcela o parcelas');
        const sel = d.selectedFields;
        const title = !sel.length ? 'Elegir parcela' : (d.single ? sel[0].name : sel.length + ' parcelas');
        setText(ui_.fieldTitle, title);
        ui_.fieldTitle.classList.toggle('tf-pick-title--empty', !sel.length);
        let sub = '';
        if (!sel.length) sub = isEdit ? '' : 'Puedes elegir varias a la vez';
        else if (d.single) {
            const f = sel[0];
            const area = d.partialActive && !d.areaError && f.effectiveArea !== f.area ? nf(f.effectiveArea) + ' de ' + nf(f.area) + ' ha' : nf(f.area) + ' ha';
            sub = f.crop + ' · ' + area + (d.partialActive && state.zone.trim() ? ' · ' + state.zone.trim() : '');
        } else sub = sel.map((f) => f.name).join(', ') + ' · ' + nf(d.totalArea) + ' ha';
        setText(ui_.fieldSub, sub);
        setHidden(ui_.multiNote, !d.multi);
        setHidden(ui_.partialOpen, !(d.single && !d.partialActive));
        setHidden(ui_.partial, !d.partialActive);
        if (d.partialActive) {
            setVal(ui_.area, state.appliedArea);
            setVal(ui_.zone, state.zone);
            ui_.area.placeholder = 'Máx. ' + nf(d.selectedFields[0].area);
            ui_.area.setAttribute('aria-invalid', String(!!d.areaError));
        }
    }

    function machineChip(m, selected) {
        const b = el('button', { type: 'button', 'class': 'tf-chip', role: 'radio', 'aria-checked': String(selected), 'data-machine': String(m.id) });
        b.appendChild(document.createTextNode(m.name + ' '));
        b.appendChild(el('small', {}, nf(m.capacity, 0) + ' L'));
        return b;
    }

    function loadText(l, multi) {
        let txt = l.fullLoads ? l.fullLoads + ' ' + plural(l.fullLoads, 'cuba llena', 'cubas llenas') : '';
        if (l.partialLoad) txt += (txt ? ' + ' : '') + '1 de ' + nf(l.partialWater, 0) + ' L';
        if (!txt) txt = 'Menos de una cuba';
        return (multi ? l.fieldName + ': ' : '') + txt;
    }

    function paintApp(d) {
        setHidden(ui_.secApp, !d.isSpray);
        if (!d.isSpray) return;
        setHidden(ui_.machineChips, d.machineMode !== 'multi');
        setHidden(ui_.machineSingle, d.machineMode !== 'single');
        if (d.machineMode === 'multi') {
            const sig = data.machines.map((m) => m.id + ':' + (d.machine && d.machine.id === m.id)).join('|');
            if (ui_.machineChips.dataset.sig !== sig) {
                ui_.machineChips.dataset.sig = sig;
                ui_.machineChips.textContent = '';
                data.machines.forEach((m) => ui_.machineChips.appendChild(machineChip(m, !!d.machine && d.machine.id === m.id)));
            }
        } else if (d.machineMode === 'single') {
            setText(ui_.machineName, d.machine.name);
            setText(ui_.machineCap, nf(d.machine.capacity, 0) + ' L · tu única máquina');
        }
        setVal(ui_.water, state.water);
        ui_.water.setAttribute('aria-invalid', String(state.tried && d.errors.application.some((m) => /mojado/.test(m))));
        setHidden(ui_.loads, !d.loads.length);
        if (d.loads.length) {
            setText(ui_.loadsHead, nf(d.loadsTotalWater, 0) + ' L de caldo con ' + d.machine.name + ' (' + nf(d.machine.capacity, 0) + ' L)');
            ui_.loadRows.textContent = '';
            d.loads.forEach((l) => ui_.loadRows.appendChild(el('div', { 'class': 'tf-loads-row' }, loadText(l, d.multi))));
        }
    }

    function paintDate(d) {
        const today = data.today;
        const options = [['hoy', 'Hoy', today], ['manana', 'Mañana', addDays(today, 1)], ['pasado', weekdayShort(addDays(today, 2)), addDays(today, 2)]];
        const presetKey = (options.find((o) => o[2] === state.date) || [null])[0];
        const custom = uiState.customDate || !presetKey;
        const sig = state.date + '|' + custom + '|' + today;
        if (ui_.dateChips.dataset.sig !== sig) {
            ui_.dateChips.dataset.sig = sig;
            ui_.dateChips.textContent = '';
            options.forEach((o) => {
                const b = el('button', { type: 'button', 'class': 'tf-chip', role: 'radio', 'aria-checked': String(!custom && presetKey === o[0]), 'data-date': o[2] }, o[1]);
                ui_.dateChips.appendChild(b);
            });
            ui_.dateChips.appendChild(el('button', { type: 'button', 'class': 'tf-chip', role: 'radio', 'aria-checked': String(custom), 'data-date': 'custom' }, 'Otra fecha'));
        }
        setText(ui_.dateTitle, state.done ? 'Fecha programada' : 'Cuándo');
        setHidden(ui_.customDate, !custom);
        setVal(ui_.customDate, state.date);
        setText(ui_.dateLong, state.date ? longDate(state.date) : 'Elige una fecha');
        ui_.done.setAttribute('aria-checked', String(state.done));
        setHidden(ui_.doneFields, !state.done);
        ui_.doneFields.classList.toggle('tf-done-fields--one', !d.isSpray);
        setHidden(ui_.realWrap, !d.isSpray);
        if (state.done) {
            ui_.finish.max = data.today;
            setVal(ui_.finish, state.finishDate);
            setVal(ui_.realWater, state.realWater);
            ui_.realWater.placeholder = state.water ? 'Previsto ' + state.water : '';
        }
    }

    function paintName() {
        setVal(ui_.name, state.name);
    }

    function paintSummary(d) {
        const s = d.summary;
        setText(ui_.sumMain, s.ready ? eur(s.totalCost) : '— €');
        let loadsShort = '';
        if (d.isSpray && d.loads.length) loadsShort = d.single ? loadText(d.loads[0], false) : d.loads.length + ' parcelas';
        setText(ui_.sumSub, s.ready ? nf(d.totalArea) + ' ha · ' + eur(s.costPerHa) + '/ha' + (d.single && loadsShort ? ' · ' + loadsShort : '') : 'Se calcula al completar los datos');
        const missing = d.missingText;
        setText(ui_.missing, missing);
        ui_.missing.classList.toggle('tf-missing--err', state.tried);
        if (missing) ui_.summary.setAttribute('data-missing', '1'); else ui_.summary.removeAttribute('data-missing');

        const kv = [['Parcela', d.selectedFields.length ? (d.single ? d.selectedFields[0].name : d.fieldCount + ' parcelas') : '—'],
            ['Superficie', d.selectedFields.length ? nf(d.totalArea) + ' ha' : '—'],
            ['Fecha', state.date ? shortDate(state.date) : '—']];
        if (d.isSpray) {
            kv.push(['Caldo', d.loadsTotalWater ? nf(d.loadsTotalWater, 0) + ' L' : '—']);
            kv.push(['Cubas', loadsShort || '—']);
        }
        kv.push(['Productos', String(s.validLines)]);
        ui_.kv.textContent = '';
        kv.forEach((row) => {
            const wrap = el('div');
            wrap.appendChild(el('dt', {}, row[0]));
            wrap.appendChild(el('dd', {}, row[1]));
            ui_.kv.appendChild(wrap);
        });

        const n = d.fieldCount;
        ui_.save.textContent = '';
        if (isEdit) ui_.save.append('Guardar', el('span', { 'class': 'd-none d-lg-inline' }, ' cambios'));
        else if (n > 1) ui_.save.append('Crear ' + n, el('span', { 'class': 'd-none d-lg-inline' }, ' tratamientos'));
        else ui_.save.append('Crear', el('span', { 'class': 'd-none d-lg-inline' }, ' tratamiento'));
    }

    function paintStatus(d) {
        setHidden(ui_.status, !isEdit);
        if (!isEdit) return;
        const labels = { pending: 'Pendiente', delayed: 'Atrasado', completed: 'Hecho' };
        setText(ui_.status, labels[d.status]);
        ui_.status.className = 'tf-status' + (d.status === 'pending' ? '' : ' tf-status--' + d.status);
    }

    function paintErrors(d) {
        SECTIONS.forEach((sec) => {
            const msgs = [];
            if (state.tried) d.errors[sec].forEach((m) => { if (msgs.indexOf(m) < 0) msgs.push(m); });
            (srv.sections[sec] || []).forEach((m) => { if (msgs.indexOf(m) < 0) msgs.push(m); });
            sectionEl[sec].classList.toggle('tf-card--err', msgs.length > 0);
            const box = errEl[sec];
            const sig = msgs.join('\u0001');
            if (box.dataset.sig !== sig) {
                box.dataset.sig = sig;
                box.textContent = '';
                msgs.forEach((m) => box.appendChild(el('span', {}, m)));
            }
        });
        ui_.summary.classList.toggle('tf-summary--tried', state.tried);
    }

    function render() {
        const d = S.derive(state, data);
        paintStatus(d);
        paintField(d);
        paintLines(d);
        paintApp(d);
        paintDate(d);
        paintName(d);
        paintSummary(d);
        paintErrors(d);
        renderPickers(d);
        lastDerived = d;
    }
    let lastDerived = null;

    // ── Selectores (parcelas y productos) ─────────────────────────────────────

    const sheets = { fields: $('tfFieldsSheet'), products: $('tfProductsSheet') };
    const pops = { fields: $('tfFieldsPop'), products: $('tfProductsPop') };
    const lists = {
        fields: Array.from(root.querySelectorAll('[data-list="fields"]')),
        products: Array.from(root.querySelectorAll('[data-list="products"]')),
    };
    const searchEls = Array.from(root.querySelectorAll('[data-search]'));

    function sheetOf(kind) {
        return window.bootstrap && window.bootstrap.Offcanvas ? window.bootstrap.Offcanvas.getOrCreateInstance(sheets[kind]) : null;
    }

    function optBox(on, radio) {
        const box = el('span', { 'class': 'tf-opt-box' + (radio ? ' tf-opt-box--radio' : ''), 'aria-hidden': 'true' });
        if (on) box.appendChild(el('i', { 'class': 'bi bi-check-lg' }));
        return box;
    }

    function fieldOptions() {
        const q = norm(uiState.fieldsQuery.trim());
        const picked = new Set(state.fieldIds);
        return data.fields.filter((f) => !q || norm(f.name + ' ' + f.crop).indexOf(q) >= 0).map((f) => {
            const b = el('button', { type: 'button', 'class': 'tf-opt', role: 'option', 'aria-selected': String(picked.has(f.id)), 'data-field': String(f.id) });
            const main = el('span', { 'class': 'tf-opt-body' });
            main.appendChild(el('span', { 'class': 'tf-opt-name' }, f.name));
            let sub = f.crop + ' · ' + nf(f.area) + ' ha';
            if (f.last_treatment_date) {
                const days = daysBetween(f.last_treatment_date, data.today);
                sub += ' · ' + (days <= 0 ? 'tratada hoy' : 'hace ' + days + ' d');
            }
            main.appendChild(el('span', { 'class': 'tf-opt-sub' }, sub));
            b.appendChild(optBox(picked.has(f.id), isEdit));
            b.appendChild(main);
            return b;
        });
    }

    // Admitidos (según el tipo actual) → recientes → nombre; los que no admiten el tipo van al final, desactivados
    // (salvo que ya estén añadidos: se pueden quitar desde la lista aunque ya no valgan para este tipo)
    function productOptions() {
        const q = norm(uiState.productsQuery.trim());
        const used = new Set(state.lines.map((l) => l.productId));
        const supports = (p) => !!(state.type === 'spraying' ? p.spraying : p.fertigation);
        const list = data.products.filter((p) => !q || norm(p.name + ' ' + p.type_name).indexOf(q) >= 0);
        list.sort((a, b) => (supports(b) - supports(a)) || ((b.recent ? 1 : 0) - (a.recent ? 1 : 0)) || a.name.localeCompare(b.name, 'es'));
        return list.map((p) => {
            const ok = supports(p);
            const added = used.has(p.id);
            const b = el('button', { type: 'button', 'class': 'tf-opt', role: 'option', 'data-product': String(p.id), 'aria-selected': String(added) });
            if (!ok && !added) b.disabled = true;
            const main = el('span', { 'class': 'tf-opt-body' });
            const name = el('span', { 'class': 'tf-opt-name' }, p.name);
            if (p.recent) name.appendChild(el('span', { 'class': 'tf-tag' }, 'Reciente'));
            main.appendChild(name);
            const opt = state.type === 'spraying' ? p.spraying : p.fertigation;
            const other = opt || p.spraying || p.fertigation;
            let sub = p.type_name;
            if (ok) sub += ' · ' + nf(opt.dose, 3) + ' ' + opt.label;
            else sub += ' · no admite ' + (state.type === 'spraying' ? 'pulverización' : 'fertirrigación') + (added ? ' · toca para quitarlo' : '');
            main.appendChild(el('span', { 'class': 'tf-opt-sub' }, sub));
            b.appendChild(optBox(added, false));
            b.appendChild(main);
            if (other) b.appendChild(el('span', { 'class': 'tf-opt-side' }, p.price > 0 ? p.price.toLocaleString('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' €/' + C.totalUnit(other.dose_type) : 'Sin precio'));
            return b;
        });
    }

    function fillList(kind, nodes, emptyText) {
        lists[kind].forEach((box) => {
            box.textContent = '';
            if (!nodes.length) box.appendChild(el('p', { 'class': 'tf-hint tf-opts-empty' }, emptyText));
            nodes.forEach((n) => box.appendChild(n.cloneNode(true)));
        });
    }

    const validIds = (nodes) => nodes.filter((n) => !n.disabled && n.getAttribute('aria-selected') !== 'true').map((n) => Number(n.dataset.product));

    function renderPickers() {
        const kind = uiState.picker;
        root.classList.toggle('tf--nosheet', !hasSheets());
        // Pie de las hojas: «Listo · N parcelas/productos»
        const nF = state.fieldIds.length, nP = state.lines.length;
        root.querySelectorAll('[data-done="fields"]').forEach((b) => setText(b, nF ? 'Listo · ' + nF + ' ' + plural(nF, 'parcela', 'parcelas') : 'Listo'));
        root.querySelectorAll('[data-done="products"]').forEach((b) => setText(b, nP ? 'Listo · ' + nP + ' ' + plural(nP, 'producto', 'productos') : 'Listo'));
        setHidden(ui_.addClose, kind !== 'products' || !usePop());
        ui_.fieldBtn.setAttribute('aria-expanded', String(kind === 'fields'));
        ui_.addBtn.setAttribute('aria-expanded', String(kind === 'products'));
        ui_.addInput.setAttribute('aria-expanded', String(kind === 'products' && usePop()));
        if (!kind) return;
        if (kind === 'fields') fillList('fields', fieldOptions(), 'No hay parcelas que coincidan.');
        else {
            const nodes = productOptions();
            fillList('products', nodes, 'No hay productos que coincidan.');
            const ids = validIds(nodes);
            const hi = ids.indexOf(uiState.hi) >= 0 ? uiState.hi : (ids.length ? ids[0] : -1);
            const show = !!uiState.productsQuery.trim() || uiState.hi !== -1;     // sin escribir ni navegar no se resalta nada
            if (usePop()) lists.products.forEach((box) => {
                Array.from(box.querySelectorAll('.tf-opt')).forEach((n) => {
                    const on = show && Number(n.dataset.product) === hi;
                    n.dataset.active = String(on);
                    if (on && n.scrollIntoView) n.scrollIntoView({ block: 'nearest' });
                });
            });
        }
    }

    function openPicker(kind) {
        if (uiState.picker && uiState.picker !== kind) closePicker();
        uiState.picker = kind;
        if (usePop()) {
            setHidden(pops[kind], false);
            renderPickers();
            const input = kind === 'products' ? ui_.addInput : pops.fields.querySelector('[data-search]');
            if (input && document.activeElement !== input) input.focus();
        } else {
            renderPickers();
            const sheet = sheetOf(kind);
            if (sheet) sheet.show();
        }
    }

    function closePicker() {
        const kind = uiState.picker;
        if (!kind) return;
        uiState.picker = null;
        uiState.fieldsQuery = uiState.productsQuery = '';
        uiState.hi = -1;
        searchEls.forEach((s) => { s.value = ''; });
        ui_.addInput.value = '';
        setHidden(pops.fields, true);
        setHidden(pops.products, true);
        const sheet = sheets[kind].classList.contains('show') ? sheetOf(kind) : null;
        if (sheet) sheet.hide();
        renderPickers();
    }

    // Intro: añade el producto resaltado (por defecto, el primero válido)
    function addHighlighted() {
        const ids = validIds(productOptions());
        if (!ids.length) return;
        dispatch('addProduct', { productId: ids.indexOf(uiState.hi) >= 0 ? uiState.hi : ids[0] });
        uiState.productsQuery = '';
        uiState.hi = -1;
        ui_.addInput.value = '';
        renderPickers();
    }

    // ↓/↑: mueven el resaltado entre los productos válidos (dan la vuelta)
    function moveHighlight(step) {
        if (uiState.picker !== 'products') openPicker('products');
        const ids = validIds(productOptions());
        if (!ids.length) return;
        const at = Math.max(0, ids.indexOf(uiState.hi));
        uiState.hi = ids[(at + step + ids.length) % ids.length];
        renderPickers();
    }

    // ── Eventos ───────────────────────────────────────────────────────────────

    const keyOf = (node) => { const row = node.closest('.tf-line'); return row ? Number(row.dataset.key) : null; };
    const only = (input, re) => { const clean = input.value.replace(re, ''); if (clean !== input.value) input.value = clean; return clean; };
    const DIGITS = /[^0-9]/g;
    const DECIMAL = /[^0-9.,]/g;

    root.addEventListener('click', (e) => {
        const t = e.target.closest('button, a');
        if (!t) return;
        if (t.classList.contains('tf-seg-btn')) { dispatch('setType', { type: t.dataset.type }); return; }
        if (t === ui_.fieldBtn) { uiState.picker === 'fields' ? closePicker() : openPicker('fields'); return; }
        if (t === ui_.addBtn) { openPicker('products'); return; }
        if (t === ui_.addClose) { closePicker(); return; }
        if (t.dataset.done && usePop()) { closePicker(); return; }
        if (t === ui_.partialOpen) { dispatch('setPartial', { partial: true }); return; }
        if (t.id === 'tfPartialClose') { dispatch('setPartial', { partial: false }); return; }
        if (t === ui_.done) { dispatch('setDone', { done: ui_.done.getAttribute('aria-checked') !== 'true' }); return; }
        if (t.dataset.machine) { dispatch('setMachine', { id: Number(t.dataset.machine) }); return; }
        if (t.dataset.date) {
            if (t.dataset.date === 'custom') { uiState.customDate = true; render(); ui_.customDate.focus(); }
            else { uiState.customDate = false; dispatch('setDate', { date: t.dataset.date }); render(); }
            return;
        }
        if (t.dataset.field) {
            dispatch('toggleField', { id: Number(t.dataset.field) });
            if (isEdit) closePicker(); else renderPickers();
            return;
        }
        if (t.dataset.product) {
            const id = Number(t.dataset.product);
            const line = state.lines.find((l) => l.productId === id);
            dispatch(line ? 'removeProduct' : 'addProduct', line ? { key: line.key } : { productId: id });
            renderPickers();
            return;
        }
        const act = t.dataset.act;
        const key = keyOf(t);
        if (act === 'remove' && key) dispatch('removeProduct', { key: key });
        else if (act === 'clear-total' && key) dispatch('clearOverride', { key: key });
    });

    root.addEventListener('input', (e) => {
        const t = e.target;
        if (t.dataset.search) {
            uiState[t.dataset.search === 'fields' ? 'fieldsQuery' : 'productsQuery'] = t.value;
            uiState.hi = -1;
            searchEls.forEach((s) => { if (s !== t && s.dataset.search === t.dataset.search) s.value = t.value; });
            renderPickers();
            return;
        }
        if (t === ui_.addInput) {
            const typed = t.value;
            if (uiState.picker && uiState.picker !== 'products') closePicker();   // cierra el otro selector (y limpia las búsquedas)
            t.value = typed;
            uiState.productsQuery = typed;
            uiState.hi = -1;
            if (uiState.picker !== 'products') openPicker('products'); else renderPickers();
            return;
        }
        const key = keyOf(t);
        if (t.dataset.role === 'dose' && key) dispatch('setDose', { key: key, dose: only(t, DECIMAL) });
        else if (t.dataset.role === 'total' && key) dispatch('setTotal', { key: key, total: only(t, DECIMAL) });
        else if (t === ui_.water) dispatch('setWater', { water: only(t, DIGITS) });
        else if (t === ui_.realWater) dispatch('setRealWater', { water: only(t, DIGITS) });
        else if (t === ui_.area) dispatch('setAppliedArea', { area: only(t, DECIMAL) });
        else if (t === ui_.zone) dispatch('setZone', { zone: t.value });
        else if (t === ui_.name) dispatch('setName', { name: t.value });
        else if (t === ui_.customDate) { if (t.value) dispatch('setDate', { date: t.value }); }
        else if (t === ui_.finish) dispatch('setFinishDate', { date: t.value });
    });

    root.addEventListener('change', (e) => {
        if (e.target === ui_.customDate && e.target.value) dispatch('setDate', { date: e.target.value });
    });

    // Al salir de un campo de la línea se repinta: el otro valor derivado (p. ej. un total vaciado) vuelve a enseñarse
    root.addEventListener('focusout', (e) => {
        if (e.target.dataset && (e.target.dataset.role === 'total' || e.target.dataset.role === 'dose')) render();
    });

    form.addEventListener('keydown', (e) => {
        const t = e.target;
        if (t === ui_.addInput) {
            if (e.key === 'Enter') { e.preventDefault(); addHighlighted(); }
            else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); moveHighlight(e.key === 'ArrowDown' ? 1 : -1); }
            else if (e.key === 'Escape') { e.preventDefault(); closePicker(); }
            return;
        }
        if (e.key === 'Escape' && uiState.picker) { closePicker(); return; }
        if (e.key === 'Enter' && t.tagName === 'INPUT' && t.type !== 'submit') e.preventDefault();   // Intro no envía el formulario
    });

    document.addEventListener('click', (e) => {
        if (!uiState.picker || !usePop()) return;
        if (!e.target.isConnected) return;   // el clic era sobre una opción que se acaba de repintar
        const inside = e.target.closest('#tfFieldsPop, #tfProductsPop, #tfFieldBtn, #tfAddInline, #tfAddBtn');
        if (!inside) closePicker();
    });

    Object.keys(sheets).forEach((kind) => {
        sheets[kind].addEventListener('hidden.bs.offcanvas', () => {
            if (uiState.picker === kind) {
                uiState.picker = null; uiState.fieldsQuery = uiState.productsQuery = '';
                searchEls.forEach((s) => { s.value = ''; });
                renderPickers();
            }
        });
    });
    window.matchMedia('(min-width: 992px)').addEventListener('change', () => closePicker());

    // ── Envío ─────────────────────────────────────────────────────────────────

    let addedRows = [];

    function setReal(input, value) { if (input) input.value = value; }

    function writeReal(v) {
        setReal(real.name, v.name); setReal(real.type, v.type); setReal(real.date, v.date);
        setReal(real.field, v.field); setReal(real.machine, v.machine); setReal(real.water, v.water_per_ha);
        setReal(real.finish, v.finish_date); setReal(real.realWater, v.real_water_per_ha);
        setReal(real.area, v.applied_area); setReal(real.zone, v.zone_notes);
        if (real.extra) Array.from(real.extra.options).forEach((o) => { o.selected = v.extra_fields.indexOf(o.value) >= 0; });

        addedRows.forEach((r) => r.remove());
        addedRows = [];
        const free = rowsInfo.slice();
        const q = (row, s) => row.querySelector('[name$="-' + s + '"]');
        const fill = (row, ln) => {
            q(row, 'product').value = String(ln.product);
            q(row, 'dose').value = ln.dose;
            q(row, 'total_dose').value = ln.total_dose;
            q(row, 'total_overridden').value = ln.total_overridden;
            q(row, 'position').value = String(ln.position);
            q(row, 'DELETE').checked = false;
        };
        const rowsBox = $('tfRows');
        const tpl = $('tfRowTpl');
        let index = rowsInfo.length;
        v.lines.forEach((ln) => {
            const at = free.findIndex((r) => r.productId === ln.product);
            if (at >= 0) { fill(free[at].row, ln); free.splice(at, 1); return; }
            const holder = document.createElement('div');
            holder.innerHTML = tpl.innerHTML.replace(/__prefix__/g, String(index));
            const row = holder.firstElementChild;
            index += 1;
            rowsBox.appendChild(row);
            addedRows.push(row);
            fill(row, ln);
        });
        free.forEach((r) => { q(r.row, 'DELETE').checked = true; });   // líneas quitadas: se borran
        real.total.value = String(index);
    }

    function firstErrorTarget() {
        const bad = root.querySelector('.tf-line--bad, .tf-line--err');
        const sec = SECTIONS.map((s) => sectionEl[s]).find((n) => n.classList.contains('tf-card--err') && !n.hidden);
        const target = sec || bad;
        if (!target) return null;
        const line = target.matches('.tf-line') ? target : (target.querySelector('.tf-line--bad, .tf-line--err') || target);
        return line.querySelector('input:not([type=hidden]):not([hidden])') || target.querySelector('input:not([type=hidden]), button:not([disabled])') || target;
    }

    function focusFirstError() {
        const t = firstErrorTarget();
        if (!t) return;
        if (!t.matches('input, button, a')) t.setAttribute('tabindex', '-1');
        t.focus({ preventScroll: true });
        const isName = t === ui_.name;
        (isName ? sectionEl.name : t).scrollIntoView({ block: isName ? 'start' : 'center', behavior: 'smooth' });   // el nombre está arriba del todo
    }

    form.addEventListener('submit', (e) => {
        const d = S.derive(state, data);
        if (!d.canSave) {
            e.preventDefault();
            dispatch('markTried');
            render();
            focusFirstError();
            return;
        }
        writeReal(S.toFormValues(state, data));
    });

    // ── Arranque ──────────────────────────────────────────────────────────────

    if (srv.general.length) {
        ui_.banner.textContent = srv.general.join(' ');
        ui_.banner.hidden = false;
    }
    render();
    if (serverErrors) focusFirstError();
})();
