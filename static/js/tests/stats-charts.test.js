// Ejecutar con: npm run test:js
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');

const SC = require('../stats-charts.js');
const SCRIPT = fs.readFileSync(path.join(__dirname, '..', 'stats-charts.js'), 'utf8');

const palette = {
    categorical: ['#a', '#b', '#c'],
    muted: '#gris',
    primary: '#verde',
    highlight: '#ambar',
};

test('formatNumber usa punto de millar y coma decimal (es-ES), también con 4 cifras', () => {
    assert.equal(SC.formatNumber(1234), '1.234');
    assert.equal(SC.formatNumber(999), '999');
    assert.equal(SC.formatNumber(1234567.891, 2), '1.234.567,89');
    assert.equal(SC.formatNumber(0.5, 1), '0,5');
    assert.equal(SC.formatNumber(-1500), '-1.500');
    assert.equal(SC.formatNumber(-0.001, 2), '0,00');
    assert.equal(SC.formatNumber(null), '0');
    assert.equal(SC.formatNumber(undefined), '—');
    assert.equal(SC.formatNumber('x'), '—');
});

test('formatEuro, formatKg, formatPercent y formatCount', () => {
    assert.equal(SC.formatEuro(1234.5), '1.234,50 €');
    assert.equal(SC.formatKg(12500), '12.500 kg');
    assert.equal(SC.formatPercent(1, 4), '25 %');
    assert.equal(SC.formatPercent(1, 0), '—');
    assert.equal(SC.formatCount(1, 'uso', 'usos'), '1 uso');
    assert.equal(SC.formatCount(0, 'uso', 'usos'), '0 usos');
    assert.equal(SC.formatCount(1200, 'uso', 'usos'), '1.200 usos');
});

test('shortLabel recorta con puntos suspensivos solo si hace falta', () => {
    assert.equal(SC.shortLabel('Cartuja', 18), 'Cartuja');
    const out = SC.shortLabel('Parcela con un nombre larguísimo', 10);
    assert.equal(out.length, 10);
    assert.ok(out.endsWith('…'));
    assert.equal(SC.shortLabel(null), '');
});

test('readPalette lee los tokens CSS y usa respaldo si faltan', () => {
    const seen = [];
    const p = SC.readPalette(name => { seen.push(name); return name === '--bs-primary' ? ' #123456 ' : ''; });
    assert.equal(p.primary, '#123456');
    assert.equal(p.categorical[0], '#123456');
    assert.equal(p.categorical.length, SC.PALETTE_TOKENS.length);
    assert.ok(p.categorical.length >= 6 && p.categorical.length <= 8);
    assert.equal(p.muted, '#5F665C');
    assert.ok(seen.includes('--tl-0-fg') && seen.includes('--bs-secondary'));
    assert.equal(new Set(p.categorical).size, p.categorical.length, 'colores categóricos distintos');
});

test('assignColors: «otros» en gris y el resto cicla la paleta sin gastar colores', () => {
    const items = [{ other: false }, { other: true }, { other: false }, { other: false }, { other: false }];
    assert.deepEqual(SC.assignColors(items, palette), ['#a', '#gris', '#b', '#c', '#a']);
});

test('buildMonths separa el mes más activo en su propia serie', () => {
    const d = SC.buildMonths({ labels: ['Ene', 'Feb', 'Mar'], counts: [1, 0, 3], peak: 2 }, palette);
    assert.equal(d.datasets.length, 2);
    assert.deepEqual(d.datasets[0].data, [1, 0, null]);
    assert.deepEqual(d.datasets[1].data, [null, null, 3]);
    assert.equal(d.datasets[0].backgroundColor, '#verde');
    assert.equal(d.datasets[1].backgroundColor, '#ambar');
    assert.equal(d.datasets[1].label, 'Mes más activo');
});

test('buildMonths sin mes destacado (empate o vacío) devuelve una sola serie', () => {
    const d = SC.buildMonths({ labels: ['Ene', 'Feb'], counts: [2, 2], peak: null }, palette);
    assert.equal(d.datasets.length, 1);
    assert.deepEqual(d.datasets[0].data, [2, 2]);
});

test('buildDoughnut y buildHarvests mantienen etiquetas, valores y colores alineados', () => {
    const items = [{ label: 'Fungicida', value: 5 }, { label: 'Sin tipo', value: 1, other: true }];
    const d = SC.buildDoughnut(items, palette, 'Usos');
    assert.deepEqual(d.labels, ['Fungicida', 'Sin tipo']);
    assert.deepEqual(d.datasets[0].data, [5, 1]);
    assert.deepEqual(d.datasets[0].backgroundColor, ['#a', '#gris']);
    const h = SC.buildHarvests([{ label: 'A', value: 10 }, { label: 'B', value: 5 }], palette);
    assert.deepEqual(h.labels, ['A', 'B']);
    assert.deepEqual(h.datasets[0].data, [10, 5]);
    assert.deepEqual(h.datasets[0].backgroundColor, ['#a', '#b']);
});

function page(html, withChart) {
    const dom = new JSDOM(`<!DOCTYPE html><body>${html}</body>`, { runScripts: 'outside-only', pretendToBeVisual: true });
    const { window } = dom;
    window.matchMedia = () => ({ matches: false });
    if (withChart) {
        window.created = [];
        window.Chart = function (canvas, cfg) { window.created.push({ canvas, cfg }); };
        window.Chart.overrides = { doughnut: { plugins: { legend: { labels: { generateLabels: () => [] } } } } };
    }
    window.eval(SCRIPT);
    return window;
}

const HTML = `
<section><div><canvas data-st-chart="months"></canvas></div>
<details data-st-data><summary>Ver datos</summary></details></section>
<script id="stats-charts-data" type="application/json">${JSON.stringify({
    months: { labels: ['Ene'], counts: [2], peak: 0 }, expenses: [{ label: 'Agua', value: 5, other: false }],
    harvests: [], productTypes: [],
})}</script>`;

test('init crea las gráficas con la configuración esperada', () => {
    const w = page(HTML, true);
    w.StatsCharts.init(w);
    assert.equal(w.created.length, 1);
    const cfg = w.created[0].cfg;
    assert.equal(cfg.type, 'bar');
    assert.equal(cfg.options.maintainAspectRatio, false);
    assert.equal(cfg.options.plugins.tooltip.callbacks.label({ raw: 1200 }), ' 1.200 tratamientos');
    assert.equal(w.document.querySelector('details').open, false);
});

test('sin Chart.js oculta los lienzos y abre las tablas', () => {
    const w = page(HTML, false);
    w.StatsCharts.init(w);
    assert.equal(w.document.querySelector('canvas').parentElement.hidden, true);
    assert.equal(w.document.querySelector('details').open, true);
});
