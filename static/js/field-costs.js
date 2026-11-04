// Resumen de gastos por parcela: pestañas de periodo + filtros, y los datos de la API api-field-costs-data
// pintados como rankings de barras (HTML y CSS, sin librería de gráficos) y una tabla de parcelas plegable.
// Las funciones puras (ranking, colores, orden, redondeo, formato) se exportan para los tests de node.
(function (root, factory) {
    if (typeof module === 'object' && module.exports) module.exports = factory();
    else root.FieldCosts = factory();
}(typeof self !== 'undefined' ? self : this, function () {
    'use strict';

    // Tipos con color propio; el resto se agrupa en «Resto» (no «Otros», que puede ser un tipo real)
    const MAX_TYPES = 6;
    const REST_LABEL = 'Resto';

    // Tipos de más a menos gasto (a igualdad, por nombre): los MAX primeros y el resto aparte
    function rankTypes(breakdown, max) {
        const sorted = [...(breakdown || [])].sort((a, b) => b.total - a.total || a.type_name.localeCompare(b.type_name, 'es'));
        return sorted.length <= max ? { top: sorted, rest: [] } : { top: sorted.slice(0, max), rest: sorted.slice(max) };
    }

    // Color de cada tipo del ranking: un color de la serie por tipo, en el orden del ranking
    function typeColorMap(top, series) {
        const map = {};
        (top || []).forEach((t, i) => { map[t.type_name] = series[i]; });
        return map;
    }

    // Grises distintos (de más oscuro a más claro) para los tipos de «Resto» al desplegarlos: van agrupados
    // bajo la fila «Resto», pero cada uno se distingue del de al lado
    function restShades(n) {
        if (n <= 0) return [];
        const from = 48, to = 80, step = n > 1 ? (to - from) / (n - 1) : 0;
        return Array.from({ length: n }, (_, i) => `hsl(100 5% ${Math.round(from + step * i)}%)`);
    }

    // % del gasto de cada tipo dentro de una parcela, calculado con los totales (suma 100 con lo que hay)
    function typeShares(breakdown) {
        const types = (breakdown || []).filter(t => t.total > 0);
        const sum = types.reduce((s, t) => s + t.total, 0);
        return types.map(t => ({ type_name: t.type_name, total: t.total, pct: sum ? t.total / sum * 100 : 0 }))
            .sort((a, b) => b.total - a.total || a.type_name.localeCompare(b.type_name, 'es'));
    }

    // Tramos de la barra apilada: un tramo por tipo con color; los demás se juntan en uno («Resto») al final
    function barSegments(shares, colors, other) {
        const segs = [];
        let rest = null;
        shares.forEach(s => {
            if (colors[s.type_name]) {
                segs.push({ name: s.type_name, pct: s.pct, color: colors[s.type_name] });
            } else {
                rest = rest || { name: REST_LABEL, pct: 0, color: other };
                rest.pct += s.pct;
            }
        });
        if (rest) segs.push(rest);
        return segs;
    }

    // Parcelas de más a menos gasto ('cost') o €/ha ('perha'); a igualdad, por nombre. No cambia el original
    function sortFields(fields, key) {
        const v = key === 'perha' ? (f => f.cost_per_ha) : (f => f.total_cost);
        return [...(fields || [])].sort((a, b) => v(b) - v(a) || a.name.localeCompare(b.name, 'es'));
    }

    // Ranking de €/ha: solo parcelas con gasto y superficie (sin superficie no hay €/ha que comparar)
    function perHaRanking(fields) {
        return sortFields((fields || []).filter(f => f.total_cost > 0 && f.area > 0), 'perha');
    }

    function topField(fields) { return perHaRanking(fields)[0] || null; }

    // % redondeados a un decimal que suman exactamente 100,0 (método del mayor resto): se trunca cada uno
    // a décimas y las décimas que faltan van a los de mayor parte decimal (a igualdad, al primero).
    function roundPcts(pcts) {
        const tenths = (pcts || []).map(p => p * 10);
        const total = Math.round(tenths.reduce((s, v) => s + v, 0));
        if (total !== 1000) return tenths.map(v => Math.round(v) / 10);  // no es un reparto completo
        const floors = tenths.map(v => Math.floor(v + 1e-9));
        let missing = 1000 - floors.reduce((s, v) => s + v, 0);
        tenths.map((v, i) => ({ i, rem: v - floors[i] }))
            .sort((a, b) => b.rem - a.rem || a.i - b.i)
            .forEach(({ i }) => { if (missing > 0) { floors[i] += 1; missing -= 1; } });
        return floors.map(v => v / 10);
    }

    // % de cada importe sobre la suma de todos (mayor resto: suman 100,0); sin gasto, todos 0
    function sharePcts(values) {
        const sum = (values || []).reduce((s, v) => s + (v > 0 ? v : 0), 0);
        if (!sum) return (values || []).map(() => 0);
        return roundPcts(values.map(v => (v > 0 ? v : 0) / sum * 100));
    }

    // «Abrir parcelas» mientras quede alguna cerrada; «Cerrar parcelas» cuando están todas abiertas
    function allOpen(states) { return states.length > 0 && states.every(Boolean); }

    // Formato es-ES con separador de miles siempre: Intl no agrupa los números de 4 cifras en es-ES
    // (2226,83) y sí los de 5 (52.308,29); en una misma pantalla se verían distintos.
    const nfCache = {};
    function nf(min, max) {
        const k = min + '-' + max;
        return nfCache[k] || (nfCache[k] = new Intl.NumberFormat('es-ES',
            { minimumFractionDigits: min, maximumFractionDigits: max, useGrouping: 'always' }));
    }
    const NBSP = ' ';  // la unidad nunca se separa de la cifra
    const fmt = {
        eur: (n) => nf(2, 2).format(n) + NBSP + '€',
        eurHa: (n) => nf(2, 2).format(n) + NBSP + '€/ha',
        num: (n) => nf(0, 2).format(n),
        pct: (n) => nf(0, 1).format(n) + NBSP + '%',
    };

    return {
        MAX_TYPES, REST_LABEL, rankTypes, typeColorMap, restShades, typeShares, barSegments,
        sortFields, perHaRanking, topField, roundPcts, sharePcts, allOpen, fmt
    };
}));

if (typeof document !== 'undefined') document.addEventListener('DOMContentLoaded', function () {
    const FC = window.FieldCosts;
    const $ = (id) => document.getElementById(id);
    const dateFromInput = $('dateFrom');
    const dateToInput = $('dateTo');
    const applyFilterBtn = $('applyDateFilter');
    const fieldsContainer = $('fieldsContainer');
    const fieldsInput = $('fieldSelectorDropdown');
    const viewModeSelector = $('viewMode');
    const body = $('costsBody');

    // Salir si no estamos en la página de resumen de gastos
    if (!dateFromInput || !dateToInput || !applyFilterBtn || !fieldsContainer || !fieldsInput || !viewModeSelector || !body) {
        return;
    }

    const currentYear = new Date().getFullYear();
    const tabs = Array.from(document.querySelectorAll('#periodTabs .tl-tab'));
    const states = { loading: $('costsLoading'), empty: $('costsEmpty'), error: $('costsError'), body };

    // Colores de las series: variables --cs-* de treatment-styles.css (la paleta de la app)
    const css = getComputedStyle(document.documentElement);
    const SERIES = [1, 2, 3, 4, 5, 6].map(i => css.getPropertyValue('--cs-' + i).trim() || '#2E7D32');
    const OTHER = css.getPropertyValue('--cs-other').trim() || '#7A8577';
    const PERHA_VISIBLE = 10;  // filas del ranking de €/ha antes de «Ver todas» (alto parecido al de tipos)

    const { eur, eurHa, num, pct } = FC.fmt;
    const esc = (v) => String(v ?? '').replace(/[&<>"']/g, c => (
        { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;
    const chev = '<i class="fa fa-chevron-down cs-chev" aria-hidden="true"></i>';

    let viewMode = 'cost';
    try { viewMode = localStorage.getItem('fieldCostsViewMode') || 'cost'; } catch (e) { /* sin almacenamiento */ }
    viewModeSelector.value = viewMode === 'quantity' ? 'quantity' : 'cost';
    viewMode = viewModeSelector.value;

    let currentData = null;
    // Lo que el usuario abrió se mantiene al repintar (cambio de modo o de periodo)
    const ui = { openTypes: new Set(), restOpen: false, perHaAll: false, openFields: new Set(), openFieldTypes: new Set(), sort: 'cost' };

    // ── Periodo ────────────────────────────────────────────────────────────────
    function setPeriod(value) {
        if (value === 'all') {
            dateFromInput.value = '';
            dateToInput.value = '';
        } else {
            dateFromInput.value = `${value}-01-01`;
            dateToInput.value = `${value}-12-31`;
        }
    }

    // Pestaña activa = la que coincide con las fechas; con fechas a medida no hay ninguna
    function activePeriod() {
        const from = dateFromInput.value, to = dateToInput.value;
        if (!from && !to) return 'all';
        const m = /^(\d{4})-01-01$/.exec(from);
        return m && to === `${m[1]}-12-31` ? m[1] : null;
    }

    function syncUi() {
        const active = activePeriod();
        tabs.forEach(t => {
            const on = t.dataset.period === active;
            t.classList.toggle('active', on);
            if (on) t.setAttribute('aria-current', 'true'); else t.removeAttribute('aria-current');
        });
        // Contador del botón de filtros (móvil): parcelas elegidas, fechas a medida y modo cantidades
        const selected = selectedFieldIds().length;
        const count = (selected ? 1 : 0) + (active === null ? 1 : 0) + (viewMode === 'quantity' ? 1 : 0);
        const badge = $('filtersBadge'), btn = $('filtersBtn');
        if (badge) { badge.hidden = !count; badge.textContent = count; }
        if (btn) btn.setAttribute('aria-label', count ? `Filtros (${count} activos)` : 'Filtros');
    }

    function selectedFieldIds() {
        return Array.from(fieldsInput.querySelectorAll('input[type="checkbox"]:checked')).map(cb => cb.value);
    }

    function closePanel() {
        const panel = $('filtersPanel');
        if (panel && window.bootstrap && bootstrap.Offcanvas) {
            const oc = bootstrap.Offcanvas.getInstance(panel);
            if (oc) oc.hide();
        }
    }

    function show(name) {
        Object.entries(states).forEach(([k, el]) => { if (el) el.hidden = k !== name; });
        // Las cifras clave solo acompañan a los datos: así nunca quedan las de una carga anterior
        const key = $('costKey');
        if (key) key.hidden = name !== 'body';
        // Al cargar avisa #costsLoading (role="status"); aquí solo se vacía para no anunciarlo dos veces
        if (name === 'loading') $('costSummary').textContent = '';
    }

    // ── Carga ──────────────────────────────────────────────────────────────────
    let requestSeq = 0;  // solo vale la respuesta de la última petición (filtros cambiados deprisa)
    function showError(expired) {
        $('costsErrorTitle').textContent = expired ? 'Tu sesión ha caducado' : 'No se han podido cargar los datos';
        $('costsErrorText').textContent = expired ? 'Inicia sesión de nuevo para ver los gastos.' : 'Comprueba la conexión e inténtalo de nuevo.';
        const login = $('costsLogin');
        if (login) { login.hidden = !expired; login.href = states.error.dataset.loginUrl || '#'; }
        $('costsRetry').hidden = expired;
        show('error');
        $('costSummary').textContent = $('costsErrorTitle').textContent;
    }

    function loadFieldCostsData() {
        const seq = ++requestSeq;
        const params = new URLSearchParams();
        const from = dateFromInput.value, to = dateToInput.value;
        if (!from && !to) {
            params.append('all', '1');
        } else {
            if (from) params.append('date_from', from);
            if (to) params.append('date_to', to);
        }
        selectedFieldIds().forEach(id => params.append('field_ids', id));
        syncUi();
        show('loading');

        fetch(`${API_URLS.fieldCosts}?${params.toString()}`)
            .then(response => {
                if (!response.ok) throw new Error(response.status);
                return response.json();
            })
            .then(data => {
                if (seq !== requestSeq) return;
                currentData = data;
                renderNoPriceWarning(data.no_price_products || []);
                renderAll();
            })
            .catch(error => {
                if (seq !== requestSeq) return;
                console.error('Error cargando datos:', error);
                showError(String(error && error.message) === '401');
            });
    }

    // Colores del periodo: los 6 tipos con más gasto con color propio; los del «Resto», grises distintos
    // al desplegarlos (en las barras apiladas van juntos en un tramo «Resto»)
    let ranked = { top: [], rest: [] };
    let colors = {};
    let restColors = {};
    const colorOf = (name) => colors[name] || restColors[name] || OTHER;

    function renderAll() {
        const data = currentData;
        if (!data) return;
        // En cantidades, lo que cuenta es que haya producto (un producto sin precio tiene cantidad y coste 0)
        const hasData = viewMode === 'quantity'
            ? data.product_breakdown.some(t => (t.products || []).some(p => p.quantity > 0))
            : data.fields.some(f => f.total_cost > 0);
        if (!hasData) {
            const all = activePeriod() === 'all' && !selectedFieldIds().length;
            $('costsEmptyTitle').textContent = all ? 'Todavía no hay costes' : 'No hay costes con estos filtros';
            $('costsEmptyText').textContent = all
                ? 'Los costes salen de los productos de los tratamientos con precio.'
                : 'Prueba con otro periodo u otras parcelas.';
            $('costsEmptyAll').hidden = all;
            show('empty');
            $('costSummary').textContent = $('costsEmptyTitle').textContent;
            return;
        }
        show('body');
        ranked = FC.rankTypes(data.product_breakdown, FC.MAX_TYPES);
        colors = FC.typeColorMap(ranked.top, SERIES);
        const shades = FC.restShades(ranked.rest.length);
        restColors = {};
        ranked.rest.forEach((t, i) => { restColors[t.type_name] = shades[i]; });
        const all = ranked.top.concat(ranked.rest);
        const shares = FC.sharePcts(all.map(t => t.total));
        typePctMap = {};
        all.forEach((t, i) => { typePctMap[t.type_name] = shares[i]; });
        renderSummary(data);
        renderTypes();
        renderPerHa(data.fields);
        renderFields(data.fields);
    }

    // ── Cifras clave ───────────────────────────────────────────────────────────
    // Siempre en euros, también en modo cantidades: litros y kilos no se pueden sumar en una cifra, y el gasto
    // total y por hectárea es lo que se consulta primero (igual que los rankings de barras).
    function setText(id, text) { const el = $(id); if (el) el.textContent = text; }

    function renderSummary(data) {
        const n = data.fields.length;
        const area = num(data.total_area);
        setText('costKeyTotal', eur(data.total_cost));
        setText('costKeyTotalSub', plural(n, 'parcela', 'parcelas'));
        setText('costKeyPerHa', eurHa(data.cost_per_ha));
        setText('costKeyPerHaSub', `sobre ${area} ha`);

        const topType = ranked.top[0] && ranked.top[0].total > 0 ? ranked.top[0] : null;
        setText('costKeyType', topType ? topType.type_name : '—');
        setText('costKeyTypeSub', topType ? `${eur(topType.total)} · ${pct(typePct(topType.type_name))}` : 'sin precio');
        const topField = FC.topField(data.fields);
        setText('costKeyField', topField ? topField.name : '—');
        setText('costKeyFieldSub', topField ? eurHa(topField.cost_per_ha) : 'sin precio');

        setText('costSummary', `Gasto total ${eur(data.total_cost)} en ${plural(n, 'parcela', 'parcelas')}; ` +
            `${eurHa(data.cost_per_ha)} sobre ${area} ha.`);
    }

    // ── Cantidades: cada unidad por separado (no se suman litros con kilos) ────
    function qtyLabel(products) {
        const byUnit = {};
        (products || []).forEach(p => { byUnit[p.unit || ''] = (byUnit[p.unit || ''] || 0) + p.quantity; });
        return Object.entries(byUnit).map(([unit, q]) => `${num(q)} ${esc(unit)}`.trim()).join(' + ') || '—';
    }
    const isCost = () => viewMode === 'cost';
    const typeValue = (t) => isCost() ? eur(t.total) : qtyLabel(t.products);
    const productValue = (p) => isCost() ? eur(p.total) : `${num(p.quantity)} ${esc(p.unit || '')}`.trim();

    // % de cada tipo sobre el total del periodo (suman 100,0); se calcula una vez por repintado
    let typePctMap = {};
    const typePct = (name) => typePctMap[name] || 0;

    // Productos de un tipo: importe normal y el % dentro del tipo, con su etiqueta (no se confunde con el del tipo)
    function productList(products, id, open) {
        const list = products || [];
        const shares = FC.sharePcts(list.map(p => p.total));
        return `<ul class="cs-prods" id="${id}"${open ? '' : ' hidden'}>${list.map((p, i) => `
            <li class="cs-prod"><span class="cs-prod-name">${esc(p.name)}</span>
                <span class="cs-prod-val">${productValue(p)}</span>${isCost() ? `<span class="cs-prod-pct">${pct(shares[i])} del tipo</span>` : ''}</li>`).join('')
            || '<li class="cs-prod text-muted">Sin productos.</li>'}</ul>`;
    }

    // Barra de una fila de ranking: proporcional al mayor importe de la lista (solo en euros)
    function rankBar(value, max, color) {
        if (!isCost()) return '<span class="cs-rank-bar cs-rank-bar--empty" aria-hidden="true"></span>';
        const w = max > 0 ? Math.max(value / max * 100, value > 0 ? 1 : 0) : 0;
        return `<span class="cs-rank-bar" aria-hidden="true"><i style="width:${w.toFixed(2)}%;background:${color}"></i></span>`;
    }

    // ── Gasto por tipo de producto: ranking de barras (6 tipos y «Resto»), cada tipo despliega sus productos ──
    let uid = 0;
    function typeRow(t, max, color) {
        const id = 'cs-tp-' + (++uid);
        const open = ui.openTypes.has(t.type_name);
        const n = (t.products || []).length;
        return `<li class="cs-rank-item">
            <button class="cs-rank-row" type="button" data-act="type" data-key="${esc(t.type_name)}" aria-expanded="${open}" aria-controls="${id}">
                <i class="cs-dot" style="background:${color}" aria-hidden="true"></i>
                <span class="cs-rank-name"><span class="cs-rank-label">${esc(t.type_name)}</span><small>${plural(n, 'producto', 'productos')}</small></span>
                ${rankBar(t.total, max, color)}
                <span class="cs-rank-val">${typeValue(t)}</span>
                <span class="cs-rank-pct">${isCost() ? pct(typePct(t.type_name)) : ''}</span>
                ${chev}
            </button>
            ${productList(t.products, id, open)}
        </li>`;
    }

    function renderTypes() {
        const box = $('productTypeDetails');
        const more = $('typesMore');
        const all = ranked.top.concat(ranked.rest);
        if (!all.length) { box.innerHTML = '<li class="hm-group-empty">Sin datos en este periodo.</li>'; more.hidden = true; return; }

        const restTotal = ranked.rest.reduce((s, t) => s + t.total, 0);
        const max = Math.max(ranked.top[0] ? ranked.top[0].total : 0, restTotal);
        let html = ranked.top.map(t => typeRow(t, max, colors[t.type_name])).join('');
        if (ranked.rest.length) {
            // «Resto» suma los % ya redondeados de sus tipos: con los de arriba da 100,0
            const restPct = Math.round(ranked.rest.reduce((s, t) => s + typePct(t.type_name), 0) * 10) / 10;
            const restAll = ranked.rest.flatMap(t => t.products || []);
            html += `<li class="cs-rank-item cs-rank-item--rest">
                <div class="cs-rank-row cs-rank-row--static">
                    <i class="cs-dot" style="background:${OTHER}" aria-hidden="true"></i>
                    <span class="cs-rank-name"><span class="cs-rank-label">${FC.REST_LABEL} · ${plural(ranked.rest.length, 'tipo', 'tipos')}</span></span>
                    ${rankBar(restTotal, max, OTHER)}
                    <span class="cs-rank-val">${isCost() ? eur(restTotal) : qtyLabel(restAll)}</span>
                    <span class="cs-rank-pct">${isCost() ? pct(restPct) : ''}</span>
                    <span class="cs-chev" aria-hidden="true"></span>
                </div>
                <ul class="cs-rank cs-rank--rest" id="typesRest"${ui.restOpen ? '' : ' hidden'}>
                    ${ranked.rest.map(t => typeRow(t, max, restColors[t.type_name])).join('')}
                </ul>
            </li>`;
        }
        box.innerHTML = html;
        more.hidden = !ranked.rest.length;
        syncMore(more, ui.restOpen, `Ver todos los tipos (${all.length})`, 'Ver menos tipos');
    }

    function syncMore(btn, open, closedText, openText) {
        btn.setAttribute('aria-expanded', String(open));
        btn.textContent = open ? openText : closedText;
    }

    // ── Coste por hectárea: ranking compacto (siempre en euros; el detalle está en «Por parcela») ──
    function renderPerHa(fields) {
        const box = $('perHaList');
        const more = $('perHaMore');
        const list = FC.perHaRanking(fields);
        if (!list.length) {
            box.innerHTML = '<li class="hm-group-empty">Sin parcelas con gasto y superficie.</li>';
            more.hidden = true;
            return;
        }
        const max = list[0].cost_per_ha;
        box.innerHTML = list.map((f, i) => `
            <li class="cs-perha-row"${i >= PERHA_VISIBLE && !ui.perHaAll ? ' hidden' : ''}>
                <span class="cs-perha-name">${esc(f.name)}</span>
                <span class="cs-rank-bar" aria-hidden="true"><i style="width:${(f.cost_per_ha / max * 100).toFixed(2)}%"></i></span>
                <span class="cs-perha-val">${eurHa(f.cost_per_ha)}</span>
            </li>`).join('');
        more.hidden = list.length <= PERHA_VISIBLE;
        syncMore(more, ui.perHaAll, `Ver todas las parcelas (${list.length})`, 'Ver menos parcelas');
    }

    // ── Por parcela: tabla con una fila por parcela (plegada); al abrir, sus tipos (plegados) y, al abrir un
    // tipo, sus productos. El desglose se pinta al abrir por primera vez: con muchas parcelas no se genera
    // de golpe lo que casi nadie va a mirar.
    // Barra apilada con el % de gasto por tipo; el texto alternativo lleva los mismos % (no solo color)
    function fieldBar(f, extra) {
        const segs = FC.barSegments(FC.typeShares(f.product_breakdown), colors, OTHER);
        // Sin gasto: la barra vacía ya es gris (fondo --tl-line) y el lector de pantalla oye «Sin gasto»
        if (!segs.length) return `<span class="cs-bar${extra}" role="img" aria-label="Sin gasto"></span>`;
        const shown = FC.roundPcts(segs.map(s => s.pct));
        const label = 'Reparto del gasto: ' + segs.map((s, i) => `${s.name} ${pct(shown[i])}`).join(', ');
        return `<span class="cs-bar${extra}" role="img" aria-label="${esc(label)}">${segs.map(s =>
            `<i style="width:${s.pct.toFixed(2)}%;background:${s.color}"></i>`).join('')}</span>`;
    }

    const fieldTypeKey = (fid, name) => fid + '|' + name;

    function fieldDetail(f) {
        const types = FC.rankTypes(f.product_breakdown, Infinity).top;
        if (!types.length) return '<p class="cs-ft-empty">Sin tratamientos con productos en este periodo.</p>';
        const shares = FC.sharePcts(types.map(t => t.total));  // % sobre la parcela: suman 100,0
        const max = types[0].total;
        return `<ul class="cs-ftypes">${types.map((t, i) => {
            const id = 'cs-ftp-' + (++uid);
            const open = ui.openFieldTypes.has(fieldTypeKey(f.id, t.type_name));
            const color = colorOf(t.type_name);
            return `<li class="cs-ft">
                <button class="cs-rank-row cs-rank-row--sub" type="button" data-act="ftype" data-key="${esc(fieldTypeKey(f.id, t.type_name))}" aria-expanded="${open}" aria-controls="${id}">
                    <i class="cs-dot" style="background:${color}" aria-hidden="true"></i>
                    <span class="cs-rank-name"><span class="cs-rank-label">${esc(t.type_name)}</span></span>
                    ${rankBar(t.total, max, color)}
                    <span class="cs-rank-val">${typeValue(t)}</span>
                    <span class="cs-rank-pct">${isCost() ? `${pct(shares[i])}<span class="visually-hidden"> de la parcela</span>` : ''}</span>
                    ${chev}
                </button>
                ${productList(t.products, id, open)}
            </li>`;
        }).join('')}</ul>`;
    }

    let fieldsById = new Map();   // id → datos de la parcela (para pintar su desglose al abrirla)
    let fieldRows = [];           // { id, btn, detail } de cada parcela, en orden

    function sortHead(key, label) {
        const on = ui.sort === key;
        const only = key === 'perha' ? ' d-none d-sm-table-cell' : '';
        return `<th scope="col" class="text-end cs-th-sort${only}" aria-sort="${on ? 'descending' : 'none'}">
            <button class="cs-sort" type="button" data-act="sort" data-key="${key}"><i class="fa fa-arrow-down-long" aria-hidden="true"></i>${label}</button></th>`;
    }

    function renderFields(fields) {
        const cost = isCost();
        fieldsById = new Map(fields.map(f => [String(f.id), f]));
        const rows = FC.sortFields(fields, cost ? ui.sort : 'cost').map(f => {
            const id = String(f.id);
            const open = ui.openFields.has(id);
            const perHa = cost ? (f.area > 0 ? eurHa(f.cost_per_ha) : '—') : '';
            return `<tbody class="cs-f${open ? ' is-open' : ''}" data-id="${esc(id)}">
                <tr class="cs-f-row">
                    <th scope="row" class="cs-f-name">
                        <button class="cs-f-btn" type="button" data-act="field" aria-expanded="${open}" aria-controls="cs-fd-${esc(id)}">${esc(f.name)}</button>
                        <small class="cs-f-sub d-md-none">${num(f.area)} ha${perHa ? `<span class="d-sm-none"> · ${perHa}</span>` : ''}</small>
                        ${cost ? fieldBar(f, ' d-md-none') : ''}
                    </th>
                    <td class="cs-f-area d-none d-md-table-cell">${num(f.area)} ha</td>
                    <td class="cs-f-bar d-none d-md-table-cell">${cost ? fieldBar(f, '') : ''}</td>
                    <td class="cs-f-val">${cost ? eur(f.total_cost) : qtyLabel((f.product_breakdown || []).flatMap(t => t.products))}</td>
                    <td class="cs-f-perha d-none d-sm-table-cell">${perHa}</td>
                    <td class="cs-f-chev">${chev}</td>
                </tr>
                <tr class="cs-f-detail" id="cs-fd-${esc(id)}"${open ? '' : ' hidden'}><td colspan="6">${open ? fieldDetail(f) : ''}</td></tr>
            </tbody>`;
        }).join('');
        const head = cost
            ? `${sortHead('cost', 'Gasto')}${sortHead('perha', '€/ha')}`
            : '<th scope="col" class="text-end">Cantidad</th><th scope="col" class="d-none d-sm-table-cell"><span class="visually-hidden">€/ha</span></th>';
        fieldsContainer.innerHTML = `<table class="cs-table">
            <caption class="visually-hidden">Gasto por parcela. Pulsa una parcela para ver sus tipos de producto.</caption>
            <thead><tr>
                <th scope="col">Parcela</th>
                <th scope="col" class="text-end d-none d-md-table-cell">Superficie</th>
                <th scope="col" class="d-none d-md-table-cell">${cost ? 'Reparto por tipo' : ''}</th>
                ${head}
                <th scope="col" class="cs-f-chev"><span class="visually-hidden">Desglose</span></th>
            </tr></thead>${rows}</table>`;
        fieldRows = Array.from(fieldsContainer.querySelectorAll('tbody.cs-f')).map(tb => ({
            id: tb.dataset.id, tbody: tb, btn: tb.querySelector('.cs-f-btn'), detail: tb.querySelector('.cs-f-detail')
        }));
        syncToggleAll();
    }

    // Abre o cierra una parcela; el desglose se pinta la primera vez que se abre
    function setFieldOpen(row, open) {
        if (open && !row.detail.firstElementChild.childElementCount) {
            row.detail.firstElementChild.innerHTML = fieldDetail(fieldsById.get(row.id));
        }
        row.detail.hidden = !open;
        row.tbody.classList.toggle('is-open', open);
        row.btn.setAttribute('aria-expanded', String(open));
        if (open) ui.openFields.add(row.id); else ui.openFields.delete(row.id);
    }

    // «Abrir parcelas / Cerrar parcelas»: solo las parcelas (los tipos siguen como estaban); una pasada
    const toggleAllBtn = $('fieldsToggleAll');
    function syncToggleAll() {
        if (!toggleAllBtn) return;
        toggleAllBtn.hidden = fieldRows.length < 2;
        const expanded = FC.allOpen(fieldRows.map(r => !r.detail.hidden));
        toggleAllBtn.textContent = expanded ? 'Cerrar parcelas' : 'Abrir parcelas';
        toggleAllBtn.setAttribute('aria-expanded', String(expanded));
    }

    function toggleControlled(btn, set, key) {
        const open = btn.getAttribute('aria-expanded') !== 'true';
        btn.setAttribute('aria-expanded', String(open));
        $(btn.getAttribute('aria-controls')).hidden = !open;
        if (open) set.add(key); else set.delete(key);
    }

    // Un único oyente para todos los botones de la pantalla de datos (las filas se repintan a menudo)
    body.addEventListener('click', (e) => {
        const btn = e.target.closest('[data-act]');
        if (!btn) {
            // En la tabla, toda la fila de la parcela abre y cierra (el botón es el objetivo de teclado)
            const tr = e.target.closest('.cs-f-row');
            if (tr) tr.querySelector('.cs-f-btn').click();
            return;
        }
        const act = btn.dataset.act;
        if (act === 'type') toggleControlled(btn, ui.openTypes, btn.dataset.key);
        else if (act === 'ftype') toggleControlled(btn, ui.openFieldTypes, btn.dataset.key);
        else if (act === 'field') {
            const row = fieldRows.find(r => r.btn === btn);
            if (row) { setFieldOpen(row, row.detail.hidden); syncToggleAll(); }
        } else if (act === 'rest') {
            ui.restOpen = !ui.restOpen;
            $('typesRest').hidden = !ui.restOpen;
            syncMore(btn, ui.restOpen, `Ver todos los tipos (${ranked.top.length + ranked.rest.length})`, 'Ver menos tipos');
        } else if (act === 'perha') {
            ui.perHaAll = !ui.perHaAll;
            renderPerHa(currentData.fields);
        } else if (act === 'sort' && btn.dataset.key !== ui.sort) {
            ui.sort = btn.dataset.key;
            renderFields(currentData.fields);
            const again = fieldsContainer.querySelector(`.cs-sort[data-key="${ui.sort}"]`);
            if (again) again.focus();  // el repintado no debe mandar el foco al principio de la página
        } else if (act === 'toggle-fields') {
            const open = !FC.allOpen(fieldRows.map(r => !r.detail.hidden));
            fieldRows.forEach(r => setFieldOpen(r, open));
            syncToggleAll();
        }
    });

    // ── Aviso de productos sin precio ──────────────────────────────────────────
    function renderNoPriceWarning(products) {
        const container = $('noPriceWarning');
        if (!products || !products.length) { container.innerHTML = ''; return; }
        const totalTreatments = products.reduce((sum, p) => sum + p.treatment_count, 0);
        const rows = products.map(p => `
            <li><b>${esc(p.name)}</b> <span class="text-muted">· ${p.treatment_count} ${p.treatment_count === 1 ? 'tratamiento' : 'tratamientos'} en ${esc(p.fields.join(', '))}</span></li>`).join('');
        container.innerHTML = `
            <details class="cs-warn">
                <summary>
                    <i class="fa fa-triangle-exclamation" aria-hidden="true"></i>
                    <span><b>${products.length} producto${products.length > 1 ? 's' : ''} sin precio</b>
                        · ${totalTreatments} tratamiento${totalTreatments !== 1 ? 's' : ''} afectado${totalTreatments !== 1 ? 's' : ''}.
                        El coste mostrado puede estar subestimado.</span>
                    ${chev}
                </summary>
                <div class="cs-warn-body">
                    <ul>${rows}</ul>
                    <a class="fw-semibold" href="/productos/">Actualizar precios <i class="fa fa-arrow-right fa-xs" aria-hidden="true"></i></a>
                </div>
            </details>`;
    }

    // ── Eventos ────────────────────────────────────────────────────────────────
    tabs.forEach(t => t.addEventListener('click', () => { setPeriod(t.dataset.period); loadFieldCostsData(); }));

    applyFilterBtn.addEventListener('click', () => { closePanel(); loadFieldCostsData(); });

    fieldsInput.querySelectorAll('input[type="checkbox"]').forEach(cb => cb.addEventListener('change', loadFieldCostsData));

    // Cambiar el modo no recarga: se repintan los datos que ya hay
    viewModeSelector.addEventListener('change', function () {
        viewMode = this.value;
        try { localStorage.setItem('fieldCostsViewMode', viewMode); } catch (e) { /* sin almacenamiento */ }
        syncUi();
        renderAll();
    });

    // Limpiar: año en curso, todas las parcelas y euros
    $('resetFiltersBtn').addEventListener('click', () => {
        setPeriod(String(currentYear));
        viewModeSelector.value = 'cost';
        viewMode = 'cost';
        try { localStorage.setItem('fieldCostsViewMode', viewMode); } catch (e) { /* sin almacenamiento */ }
        fieldsInput.querySelectorAll('input[type="checkbox"]').forEach(cb => { cb.checked = false; });
        const search = fieldsInput.querySelector('.filter-dd-search');
        if (search) { search.value = ''; search.dispatchEvent(new Event('input')); }
        // base.html repinta la etiqueta del desplegable al oír «change»; sin recargar por cada casilla
        const first = fieldsInput.querySelector('input[type="checkbox"]');
        if (first) first.dispatchEvent(new Event('change'));
        else loadFieldCostsData();
    });

    $('costsRetry').addEventListener('click', loadFieldCostsData);
    $('costsEmptyAll').addEventListener('click', () => { setPeriod('all'); loadFieldCostsData(); });

    // Inicio: año en curso
    setPeriod(String(currentYear));
    loadFieldCostsData();
});
