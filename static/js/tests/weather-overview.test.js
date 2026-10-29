// Ejecutar con: npm run test:js
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');

const WEATHER = fs.readFileSync(path.join(__dirname, '..', 'weather.js'), 'utf8');
const OVERVIEW = fs.readFileSync(path.join(__dirname, '..', 'weather-overview.js'), 'utf8');

const FIELDS = [
    { id: 1, name: 'Olivar <b>grande</b>', crop: 'Olivo', area: 3 },
    { id: 2, name: 'Huerta', crop: 'Tomate', area: 1 },
];

function hour(date, hr, extra = {}) {
    return { date, hour: `${String(hr).padStart(2, '0')}:00`, temperature: 15, precipitation: 0,
        precipitation_probability: 0, wind_speed: 5, wind_level: 0, level: 'ok', icon: 'fa-sun', ...extra };
}

function day(date, label, extra = {}) {
    return { date, label, icon: 'fa-sun', label_weather: 'Despejado', max_temp: 20, min_temp: 10,
        max_wind_speed: 8, wind_level: 0, max_precipitation_probability: 0, total_precipitation: 0, level: 'ok',
        sunrise: '08:10', sunset: '18:40', hours: [hour(date, 7), hour(date, 12), hour(date, 19)], ...extra };
}

const DAILY = [
    day('2099-01-01', 'Jue 1'),
    day('2099-01-02', 'Vie 2', { max_temp: 9, min_temp: 2, icon: 'fa-cloud-rain', level: 'bad',
        max_precipitation_probability: 80, total_precipitation: 4.5 }),
];

async function setup(load) {
    const dom = new JSDOM(`<!DOCTYPE html><body>
        <span id="wov-subtitle"></span>
        <div id="wov-grid" data-url="/api/weather/summary/"></div>
        <div id="wov-skeletons"></div>
        <script type="application/json" id="wov-fields">${JSON.stringify(FIELDS)}</script>
    </body>`, { runScripts: 'outside-only' });
    const { window } = dom;
    window.eval(WEATHER);
    window.AgroWeather.load = load;
    window.eval(OVERVIEW);
    await new Promise(r => setTimeout(r, 0));
    return window;
}

const ok = (data) => () => Promise.resolve(data);

test('una tarjeta por municipio, ordenadas, con sus parcelas escapadas', async () => {
    const w = await setup(ok({
        municipalities: [
            { name: 'Sevilla', fields: [{ id: 2, name: 'Huerta' }], daily: DAILY, updated_at: new Date().toISOString(), stale: false },
            { name: 'Alcalá', fields: [{ id: 1, name: 'x' }], daily: DAILY, updated_at: new Date().toISOString(), stale: true },
        ],
        errors: [],
    }));
    const doc = w.document;
    const names = [...doc.querySelectorAll('.muni-name')].map(e => e.textContent.trim());
    assert.deepEqual(names, ['Alcalá', 'Sevilla']);
    assert.equal(doc.querySelector('.muni-field-chip').textContent.trim(), 'Olivar <b>grande</b>');   // texto, no HTML
    assert.match(doc.querySelectorAll('.muni-card')[0].textContent, /Sin datos nuevos de AEMET/);
    assert.ok(doc.querySelectorAll('.muni-card')[0].querySelector('.badge.text-bg-warning'));
    assert.ok(!doc.querySelectorAll('.muni-card')[1].querySelector('.badge'));
    assert.equal(doc.getElementById('wov-subtitle').textContent, '2 municipios · AEMET');
    assert.ok(doc.getElementById('wov-skeletons').classList.contains('d-none'));
});

test('elegir un día cambia la cabecera y abre su detalle por horas', async () => {
    const w = await setup(ok({ municipalities: [{ name: 'Sevilla', fields: [], daily: DAILY }], errors: [] }));
    const doc = w.document;
    const card = doc.querySelector('.muni-card');
    card.querySelectorAll('.muni-week-day')[1].click();
    assert.equal(card.querySelector('.muni-temp-max').textContent, '9°');
    assert.ok(card.querySelector('.muni-hero').classList.contains('sky-rain'));
    assert.match(card.querySelector('.muni-treatment-badge').textContent, /Adverso/);
    assert.equal(card.querySelector('.muni-hourly-day-label').textContent, 'Vie 2');
    assert.ok(card.querySelector('.muni-hourly-panel').classList.contains('open'));
    assert.deepEqual([...card.querySelectorAll('.muni-week-day')].map(d => d.classList.contains('active')), [false, true]);
});

test('el botón abre y cierra el detalle por horas', async () => {
    const w = await setup(ok({ municipalities: [{ name: 'Sevilla', fields: [], daily: DAILY }], errors: [] }));
    const card = w.document.querySelector('.muni-card');
    const panel = card.querySelector('.muni-hourly-panel');
    card.querySelector('.muni-hourly-toggle').click();
    assert.ok(panel.classList.contains('open'));
    assert.ok(card.querySelector('.toggle-arrow').classList.contains('fa-chevron-up'));
    card.querySelector('.muni-hourly-toggle').click();
    assert.ok(!panel.classList.contains('open'));
});

test('los errores se agrupan por motivo y se escapan', async () => {
    const w = await setup(ok({ municipalities: [], errors: [{ reason: 'AEMET <no> responde', fields: ['A', 'B'] }] }));
    const alert = w.document.querySelector('.alert-warning');
    assert.match(alert.textContent, /No se pudo obtener la previsión del tiempo/);
    assert.equal(alert.querySelector('li').textContent, 'A, B — AEMET <no> responde');
    assert.ok(alert.querySelector('.wov-retry'));
    assert.equal(w.document.getElementById('wov-subtitle').textContent, 'Sin datos disponibles');
});

test('si falla la llamada, todas las parcelas con el motivo del servidor', async () => {
    const w = await setup(() => Promise.reject({ status: 503, msg: 'Falta la clave de AEMET en la configuración.' }));
    const items = [...w.document.querySelectorAll('.alert-warning li')].map(li => li.textContent);
    assert.equal(items.length, 1);
    assert.match(items[0], /Huerta/);
    assert.match(items[0], /Falta la clave de AEMET/);
});

test('sin municipios ni errores: aviso de que no hay datos', async () => {
    const w = await setup(ok({ municipalities: [], errors: [] }));
    assert.ok(w.document.querySelector('.alert-secondary'));
});

test('amanecer y atardecer van intercalados en su hora', async () => {
    const w = await setup(ok({ municipalities: [], errors: [] }));
    const d = DAILY[0];
    const html = w.AgroWeatherOverview.hourCards(d, d.hours);
    const order = [...html.matchAll(/hr-card-time">([\d:]+)|hr-sun-lbl">([\d:]+)/g)].map(m => m[1] || `sol ${m[2]}`);
    assert.deepEqual(order, ['07:00', 'sol 08:10', '12:00', 'sol 18:40', '19:00']);
});

test('sin horas después del atardecer, se añade al final', async () => {
    const w = await setup(ok({ municipalities: [], errors: [] }));
    const d = DAILY[0];
    const html = w.AgroWeatherOverview.hourCards(d, d.hours.slice(0, 2));
    assert.ok(html.trim().endsWith('<span class="hr-sun-lbl">18:40</span></div>'));
});
