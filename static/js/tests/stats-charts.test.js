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
    other: '#gris',
    muted: '#muted',
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

test('readPalette lee los tokens --cs-* y usa respaldo si faltan', () => {
    const seen = [];
    const p = SC.readPalette(name => { seen.push(name); return name === '--cs-1' ? ' #123456 ' : ''; });
    assert.equal(p.categorical[0], '#123456');
    assert.equal(p.categorical.length, 6);
    assert.equal(p.other, '#7A8577');
    assert.equal(p.muted, '#5F665C');
    assert.equal(p.primary, '#2E7D32');
    assert.equal(p.highlight, p.categorical[2], 'el mes más activo usa --cs-3, no el ámbar ni el rojo semántico');
    assert.deepEqual(seen.filter(n => n.startsWith('--cs-')), ['--cs-1', '--cs-2', '--cs-3', '--cs-4', '--cs-5', '--cs-6', '--cs-other', '--cs-3']);
    for (const bad of ['--tl-0-fg', '--bs-warning', '--bs-secondary', '--bs-info']) assert.ok(!seen.includes(bad), bad);
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
    assert.equal(d.datasets[1].backgroundColor, '#ambar');   // el color del mes lo decide la paleta
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

// ── Configuraciones (puras: reciben los datos y los colores ya leídos) ──
const ui = {
    palette, ink: '#ink', muted: '#muted', line: '#line', surface: '#surface', font: 'Inter', reduceMotion: true,
    Chart: { overrides: { doughnut: { plugins: { legend: { labels: { generateLabels: () => [{ text: 'Fungicida', index: 0 }, { text: 'Otros tipos', index: 1 }] } } } } } },
};

test('doughnutConfig: leyenda con el valor y tooltip con porcentaje y coste', () => {
    const items = [{ label: 'Fungicida', value: 3, cost: 12.5 }, { label: 'Otros tipos', value: 1, other: true }];
    const cfg = SC.doughnutConfig(items, ui, { seriesLabel: 'Usos', format: v => SC.formatCount(v, 'uso', 'usos'), extra: it => (it.cost ? 'Coste: ' + SC.formatEuro(it.cost) : '') });
    assert.equal(cfg.type, 'doughnut');
    assert.equal(cfg.options.plugins.legend.position, 'bottom');
    assert.equal(cfg.data.datasets[0].borderColor, '#surface');
    assert.deepEqual(cfg.data.datasets[0].backgroundColor, ['#a', '#gris']);
    const labels = cfg.options.plugins.legend.labels.generateLabels({});
    assert.deepEqual(labels.map(l => l.text), ['Fungicida · 3 usos', 'Otros tipos · 1 uso']);
    const cb = cfg.options.plugins.tooltip.callbacks;
    assert.equal(cb.label({ label: 'Fungicida', raw: 3 }), ' Fungicida: 3 usos (75 %)');
    assert.equal(cb.afterLabel({ dataIndex: 0 }), 'Coste: 12,50 €');
    assert.equal(cb.afterLabel({ dataIndex: 1 }), '');
});

test('doughnutConfig sin Chart.overrides no rompe la leyenda', () => {
    const cfg = SC.doughnutConfig([{ label: 'A', value: 1 }], Object.assign({}, ui, { Chart: null }), { seriesLabel: 'Gasto', format: SC.formatEuro });
    assert.deepEqual(cfg.options.plugins.legend.labels.generateLabels({}), []);
});

test('harvestsConfig: barras horizontales, sin leyenda, etiqueta recortada y kg en el tooltip', () => {
    const items = [{ label: 'Parcela con un nombre larguísimo', value: 12500 }];
    const cfg = SC.harvestsConfig(items, ui);
    assert.equal(cfg.options.indexAxis, 'y');
    assert.equal(cfg.options.plugins.legend.display, false);
    assert.equal(cfg.options.plugins.tooltip.callbacks.title([{ dataIndex: 0 }]), items[0].label);
    assert.equal(cfg.options.plugins.tooltip.callbacks.title([]), '');
    assert.equal(cfg.options.plugins.tooltip.callbacks.label({ raw: 12500 }), ' 12.500 kg');
    const tick = cfg.options.scales.y.ticks.callback.call({ getLabelForValue: () => items[0].label }, 0);
    assert.ok(tick.length <= 18 && tick.endsWith('…'));
    assert.equal(cfg.options.scales.x.ticks.callback(1500), '1.500');
});

test('monthsConfig: leyenda solo si hay mes más activo y barras apiladas', () => {
    const withPeak = SC.monthsConfig({ labels: ['Ene', 'Feb'], counts: [1, 3], peak: 1 }, ui);
    assert.equal(withPeak.options.plugins.legend.display, true);
    assert.equal(withPeak.options.scales.x.stacked, true);
    const noPeak = SC.monthsConfig({ labels: ['Ene', 'Feb'], counts: [2, 2], peak: null }, ui);
    assert.equal(noPeak.options.plugins.legend.display, false);
});
