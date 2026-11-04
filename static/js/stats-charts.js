/**
 * Gráficas de Estadísticas (Chart.js 4.4.0, versionado en static/js/vendor).
 * - Los datos llegan con json_script (#stats-charts-data); aquí no se interpola nada del servidor.
 * - Los colores salen de los tokens CSS del proyecto (getComputedStyle), sin duplicar valores.
 * - Las funciones puras (formato es-ES, paleta, datasets) se exportan para los tests de node.
 * - Si Chart.js no carga, se ocultan los lienzos y se abren los «Ver datos»: las tablas siguen ahí.
 */
(function (root, factory) {
    if (typeof module === 'object' && module.exports) module.exports = factory();
    else root.StatsCharts = factory();
}(typeof self !== 'undefined' ? self : this, function () {
    'use strict';

    // Paleta categórica de la app (--cs-1…6, la misma de las gráficas de costes de Parcelas; ver treatment-styles.css).
    // El segundo valor es solo el respaldo si el token no existe en la página.
    const PALETTE_TOKENS = [
        ['--cs-1', '#008300'],
        ['--cs-2', '#EDA100'],
        ['--cs-3', '#6250D6'],
        ['--cs-4', '#EB6834'],
        ['--cs-5', '#2A78D6'],
        ['--cs-6', '#E87BA4'],
    ];
    const OTHER_TOKEN = ['--cs-other', '#7A8577'];
    const MUTED_TOKEN = ['--tl-muted', '#5F665C'];
    // Serie única de barras mensuales: verde de marca; el mes más activo, morado (--cs-3, contraste 5,8:1 sobre blanco)
    const PRIMARY_TOKEN = ['--bs-primary', '#2E7D32'];
    const HIGHLIGHT_TOKEN = PALETTE_TOKENS[2];
    const MAX_LABEL = 22;

    // ── Formato es-ES (manual: no depende de los datos de ICU del navegador/node) ──
    function formatNumber(value, decimals) {
        const d = decimals || 0;
        const n = Number(value);
        if (!Number.isFinite(n)) return '—';
        const fixed = Math.abs(n).toFixed(d);
        const parts = fixed.split('.');
        const int = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, '.');
        const sign = n < 0 && Number(fixed) !== 0 ? '-' : '';
        return sign + int + (parts[1] ? ',' + parts[1] : '');
    }
    function formatEuro(value) { return formatNumber(value, 2) + ' €'; }
    function formatKg(value) { return formatNumber(value, 0) + ' kg'; }
    function formatPercent(part, total) {
        return total > 0 ? formatNumber(part * 100 / total, 0) + ' %' : '—';
    }
    function formatCount(n, singular, plural) {
        return formatNumber(n, 0) + ' ' + (Number(n) === 1 ? singular : plural);
    }
    function shortLabel(text, max) {
        const s = String(text == null ? '' : text);
        const limit = max || MAX_LABEL;
        return s.length > limit ? s.slice(0, limit - 1).trimEnd() + '…' : s;
    }

    // ── Paleta ──
    function readToken(getVar, token) {
        const v = getVar(token[0]);
        return v && String(v).trim() ? String(v).trim() : token[1];
    }
    function readPalette(getVar) {
        return {
            categorical: PALETTE_TOKENS.map(t => readToken(getVar, t)),
            other: readToken(getVar, OTHER_TOKEN),
            muted: readToken(getVar, MUTED_TOKEN),
            primary: readToken(getVar, PRIMARY_TOKEN),
            highlight: readToken(getVar, HIGHLIGHT_TOKEN),
        };
    }
    // Cada elemento normal toma el siguiente color categórico; «otros» va en gris (--cs-other).
    function assignColors(items, palette) {
        let i = 0;
        return items.map(it => it.other ? palette.other : palette.categorical[i++ % palette.categorical.length]);
    }

    // ── Constructores de datasets (puros) ──
    function buildMonths(data, palette) {
        const counts = data.counts || [];
        const peak = Number.isInteger(data.peak) ? data.peak : null;
        const base = { borderRadius: 4, borderSkipped: false, maxBarThickness: 36 };
        if (peak === null) {
            return { labels: data.labels, datasets: [Object.assign({ label: 'Tratamientos', data: counts, backgroundColor: palette.primary }, base)] };
        }
        return {
            labels: data.labels,
            datasets: [
                Object.assign({ label: 'Tratamientos', data: counts.map((c, i) => (i === peak ? null : c)), backgroundColor: palette.primary }, base),
                Object.assign({ label: 'Mes más activo', data: counts.map((c, i) => (i === peak ? c : null)), backgroundColor: palette.highlight }, base),
            ],
        };
    }
    function buildDoughnut(items, palette, label) {
        return {
            labels: items.map(it => it.label),
            datasets: [{
                label: label,
                data: items.map(it => it.value),
                backgroundColor: assignColors(items, palette),
                borderWidth: 2,
                hoverOffset: 4,
            }],
        };
    }
    function buildHarvests(items, palette) {
        return {
            labels: items.map(it => it.label),
            datasets: [{
                label: 'Cosecha (kg)',
                data: items.map(it => it.value),
                backgroundColor: assignColors(items, palette),
                borderRadius: 4,
                borderSkipped: false,
                maxBarThickness: 28,
            }],
        };
    }

    // ── Dibujo (solo navegador) ──
    function baseOptions(ui) {
        return {
            responsive: true,
            maintainAspectRatio: false,
            animation: ui.reduceMotion ? false : undefined,
            font: { family: ui.font },
            plugins: { legend: { labels: { color: ui.ink, boxWidth: 12, padding: 14, font: { size: 12 } } } },
        };
    }

    function monthsConfig(data, ui) {
        const cd = buildMonths(data, ui.palette);
        const opts = baseOptions(ui);
        opts.plugins.legend.display = cd.datasets.length > 1;
        opts.plugins.tooltip = {
            callbacks: { label: c => ' ' + formatCount(c.raw, 'tratamiento', 'tratamientos') },
        };
        opts.scales = {
            x: { stacked: true, grid: { display: false }, ticks: { color: ui.muted } },
            y: { stacked: true, beginAtZero: true, ticks: { precision: 0, color: ui.muted }, grid: { color: ui.line } },
        };
        return { type: 'bar', data: cd, options: opts };
    }

    function doughnutConfig(items, ui, opts2) {
        const cd = buildDoughnut(items, ui.palette, opts2.seriesLabel);
        cd.datasets[0].borderColor = ui.surface;
        const total = items.reduce((a, it) => a + it.value, 0);
        const opts = baseOptions(ui);
        opts.cutout = '58%';
        opts.plugins.legend.position = 'bottom';
        // La leyenda incluye el valor: el dato no depende solo del color del sector.
        const defaultLabels = ui.Chart && ui.Chart.overrides && ui.Chart.overrides.doughnut.plugins.legend.labels.generateLabels;
        opts.plugins.legend.labels.generateLabels = function (chart) {
            const base = defaultLabels ? defaultLabels(chart) : [];
            return base.map(l => Object.assign(l, { text: shortLabel(l.text, 28) + ' · ' + opts2.format(items[l.index].value), fontColor: ui.ink }));
        };
        opts.plugins.tooltip = {
            callbacks: {
                label: c => ' ' + c.label + ': ' + opts2.format(c.raw) + ' (' + formatPercent(c.raw, total) + ')',
                afterLabel: c => (opts2.extra ? opts2.extra(items[c.dataIndex]) : ''),
            },
        };
        return { type: 'doughnut', data: cd, options: opts };
    }

    function harvestsConfig(items, ui) {
        const cd = buildHarvests(items, ui.palette);
        const opts = baseOptions(ui);
        opts.indexAxis = 'y';
        opts.plugins.legend.display = false;
        opts.plugins.tooltip = {
            callbacks: {
                title: c => (c.length ? items[c[0].dataIndex].label : ''),
                label: c => ' ' + formatKg(c.raw),
            },
        };
        opts.scales = {
            x: { beginAtZero: true, ticks: { color: ui.muted, callback: v => formatNumber(v, 0) }, grid: { color: ui.line } },
            y: { grid: { display: false }, ticks: { color: ui.ink, callback: function (v) { return shortLabel(this.getLabelForValue(v), 18); } } },
        };
        return { type: 'bar', data: cd, options: opts };
    }

    function readUi(win, Chart) {
        const style = win.getComputedStyle(win.document.documentElement);
        const getVar = name => style.getPropertyValue(name);
        const body = win.getComputedStyle(win.document.body);
        return {
            Chart: Chart,
            palette: readPalette(getVar),
            ink: readToken(getVar, ['--tl-ink', '#1B1F1A']),
            muted: readToken(getVar, MUTED_TOKEN),
            line: readToken(getVar, ['--tl-line', '#EEF0EC']),
            surface: readToken(getVar, ['--tl-head-bg', '#ffffff']),
            font: body.fontFamily,
            reduceMotion: !!(win.matchMedia && win.matchMedia('(prefers-reduced-motion: reduce)').matches),
        };
    }

    function showFallback(doc) {
        doc.querySelectorAll('[data-st-chart]').forEach(c => { c.parentElement.hidden = true; });
        doc.querySelectorAll('details[data-st-data]').forEach(d => { d.open = true; });
    }

    function init(win) {
        const doc = win.document;
        const holder = doc.getElementById('stats-charts-data');
        if (!doc.querySelector('[data-st-chart]')) return;
        const Chart = win.Chart;
        let data;
        try { data = holder ? JSON.parse(holder.textContent) : null; } catch (e) { data = null; }
        if (!Chart || !data) { showFallback(doc); return; }

        const ui = readUi(win, Chart);
        const builders = {
            months: () => monthsConfig(data.months, ui),
            expenses: () => doughnutConfig(data.expenses, ui, { seriesLabel: 'Gasto', format: formatEuro }),
            harvests: () => harvestsConfig(data.harvests, ui),
            types: () => doughnutConfig(data.productTypes, ui, {
                seriesLabel: 'Usos',
                format: v => formatCount(v, 'uso', 'usos'),
                extra: it => (it && it.cost ? 'Coste: ' + formatEuro(it.cost) : ''),
            }),
        };
        doc.querySelectorAll('canvas[data-st-chart]').forEach(canvas => {
            const build = builders[canvas.dataset.stChart];
            if (!build) return;
            try {
                new Chart(canvas, build());
            } catch (e) {
                canvas.parentElement.hidden = true;
                const d = canvas.closest('section') && canvas.closest('section').querySelector('details[data-st-data]');
                if (d) d.open = true;
            }
        });
    }

    if (typeof window !== 'undefined' && window.document) {
        if (window.document.readyState === 'loading') window.document.addEventListener('DOMContentLoaded', () => init(window));
        else init(window);
    }

    return {
        PALETTE_TOKENS, formatNumber, formatEuro, formatKg, formatPercent, formatCount, shortLabel,
        readPalette, assignColors, buildMonths, buildDoughnut, buildHarvests,
        monthsConfig, doughnutConfig, harvestsConfig, init,
    };
}));
