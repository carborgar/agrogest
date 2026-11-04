// Ejecutar con: npm run test:js
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');

const SC = require('../stats-charts.js');
const SCRIPT = fs.readFileSync(path.join(__dirname, '..', 'stats-charts.js'), 'utf8');

function page(html, withChart) {
    const dom = new JSDOM(`<!DOCTYPE html><body>${html}</body>`, { runScripts: 'outside-only', pretendToBeVisual: true });
    const { window } = dom;
    if (withChart) {
        window.created = [];
        window.Chart = function (canvas, cfg) { window.created.push({ canvas, cfg }); };
        window.Chart.defaults = { font: {}, color: '' };
    }
    window.eval(SCRIPT);
    window.StatsCharts.init(window);
    return window;
}

const DATA = {
    months: { labels: ['Ene', 'Feb'], counts: [2, 5], peak: 1 },
    productTypes: { labels: ['Fungicida', 'Abono'], data: [3, 1] },
};
const HTML = `
<section><div><canvas data-st-chart="months"></canvas></div>
<details data-st-data><summary>Ver datos</summary></details></section>
<section><div><canvas data-st-chart="types"></canvas></div>
<details data-st-data><summary>Ver datos</summary></details></section>
<script id="stats-charts-data" type="application/json">${JSON.stringify(DATA)}</script>`;

test('la paleta es la original y la rosquilla la recicla con más de 10 sectores', () => {
    assert.equal(SC.DOUGHNUT_PALETTE.length, 10);
    assert.deepEqual(SC.DOUGHNUT_PALETTE.slice(0, 3), ['#2D6A4F', '#40916C', '#74C69D']);
    const colors = SC.doughnutColors(12);
    assert.equal(colors.length, 12);
    assert.equal(colors[10], SC.DOUGHNUT_PALETTE[0]);
});

test('monthsConfig: barras verdes y solo el mes más activo en dorado', () => {
    const cfg = SC.monthsConfig(DATA.months);
    assert.equal(cfg.type, 'bar');
    assert.deepEqual(cfg.data.datasets[0].data, [2, 5]);
    assert.deepEqual(cfg.data.datasets[0].backgroundColor, [SC.LIME, SC.ACCENT]);
    assert.equal(cfg.options.plugins.legend.display, false);
    assert.equal(cfg.options.scales.y.beginAtZero, true);
    assert.equal(cfg.options.plugins.tooltip.callbacks.label({ raw: 1 }), ' 1 tratamiento');
    assert.equal(cfg.options.plugins.tooltip.callbacks.label({ raw: 3 }), ' 3 tratamientos');
});

test('monthsConfig sin mes destacado no pinta ninguna barra de dorado', () => {
    const cfg = SC.monthsConfig({ labels: ['Ene', 'Feb'], counts: [2, 2], peak: null });
    assert.deepEqual(cfg.data.datasets[0].backgroundColor, [SC.LIME, SC.LIME]);
});

test('typesConfig: rosquilla con leyenda inferior (la de Chart.js, clicable) y tooltip de usos', () => {
    const cfg = SC.typesConfig(DATA.productTypes);
    assert.equal(cfg.type, 'doughnut');
    assert.deepEqual(cfg.data.labels, ['Fungicida', 'Abono']);
    assert.deepEqual(cfg.data.datasets[0].data, [3, 1]);
    assert.equal(cfg.options.cutout, '60%');
    assert.equal(cfg.options.plugins.legend.position, 'bottom');
    assert.equal(cfg.options.plugins.legend.onClick, undefined, 'conserva el comportamiento por defecto: clic oculta/muestra');
    assert.equal(cfg.options.plugins.tooltip.callbacks.label({ label: 'Abono', raw: 1 }), ' Abono: 1 uso');
    assert.equal(cfg.options.plugins.tooltip.callbacks.label({ label: 'Fungicida', raw: 3 }), ' Fungicida: 3 usos');
});

test('init crea una gráfica por lienzo con los datos del json_script', () => {
    const w = page(HTML, true);
    assert.equal(w.created.length, 2);
    assert.deepEqual(w.created.map(c => c.cfg.type), ['bar', 'doughnut']);
    assert.deepEqual(JSON.parse(JSON.stringify(w.created[1].cfg.data.datasets[0].data)), [3, 1]);
    assert.ok([...w.document.querySelectorAll('details')].every(d => !d.open));
});

test('sin Chart.js oculta los lienzos y abre las tablas', () => {
    const w = page(HTML, false);
    assert.ok([...w.document.querySelectorAll('canvas')].every(c => c.parentElement.hidden));
    assert.ok([...w.document.querySelectorAll('details')].every(d => d.open));
});

test('con JSON roto cae al respaldo en tablas', () => {
    const w = page(HTML.replace(/\{"months".*?\}\}/, '{roto'), true);
    assert.equal(w.created.length, 0);
    assert.ok([...w.document.querySelectorAll('details')].every(d => d.open));
});

test('si Chart.js falla al dibujar una gráfica, solo esa cae a su tabla', () => {
    const dom = new JSDOM(`<!DOCTYPE html><body>${HTML}</body>`, { runScripts: 'outside-only' });
    const w = dom.window;
    w.Chart = function (canvas, cfg) { if (cfg.type === 'bar') throw new Error('boom'); };
    w.Chart.defaults = { font: {}, color: '' };
    w.eval(SCRIPT);
    w.StatsCharts.init(w);
    const [months, types] = w.document.querySelectorAll('section');
    assert.equal(months.querySelector('canvas').parentElement.hidden, true);
    assert.equal(months.querySelector('details').open, true);
    assert.equal(types.querySelector('details').open, false);
});

test('una página sin lienzos no hace nada', () => {
    const w = page('<p>vacío</p>', true);
    assert.equal(w.created.length, 0);
});
