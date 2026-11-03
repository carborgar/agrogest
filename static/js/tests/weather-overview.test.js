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
        max_precipitation_probability: 80, total_precipitation: 4.5,
        hours: [hour('2099-01-02', 7, { level: 'bad' }), hour('2099-01-02', 12, { level: 'bad' })] }),
];

function localToday() {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

async function setup(load, before = () => {}) {
    const dom = new JSDOM(`<!DOCTYPE html><body>
        <span id="wov-subtitle"></span>
        <div id="wov-grid" data-url="/api/weather/summary/"></div>
        <div id="wov-skeletons"></div>
        <script type="application/json" id="wov-fields">${JSON.stringify(FIELDS)}</script>
    </body>`, { runScripts: 'outside-only' });
    const { window } = dom;
    before(window);
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
    const cards = doc.querySelectorAll('[data-card-id]');
    assert.deepEqual([...doc.querySelectorAll('.dt-card-title')].map(e => e.textContent.trim()), ['Alcalá', 'Sevilla']);
    assert.equal(doc.querySelector('.pl-chip').textContent.trim(), 'Olivar <b>grande</b>');   // texto, no HTML
    assert.match(cards[0].textContent, /Sin datos nuevos de AEMET/);
    assert.ok(cards[0].querySelector('.dt-status.dt-tone-1'));
    assert.ok(!cards[1].querySelector('.dt-status'));
    assert.match(cards[1].querySelector('.dt-muted').textContent, /1 parcela · Actualizado a las/);
    assert.equal(doc.getElementById('wov-subtitle').textContent, '2 municipios · AEMET');
    assert.ok(doc.getElementById('wov-skeletons').classList.contains('d-none'));
    assert.equal(doc.getElementById('wov-skeletons').getAttribute('aria-busy'), 'false');
});

test('abre en el día de hoy y marca la pestaña activa', async () => {
    const today = localToday();
    const daily = [day('2000-01-01', 'Sáb 1'), day(today, 'Hoy', { level: 'warn', max_temp: 18 }), day('2099-01-02', 'Vie 2')];
    const w = await setup(ok({ municipalities: [{ name: 'Sevilla', fields: [], daily }], errors: [] }));
    const tabs = [...w.document.querySelectorAll('[data-day-idx]')];
    assert.deepEqual(tabs.map(t => t.getAttribute('aria-pressed')), ['true', 'false']);   // el día pasado ya no tiene pestaña
    assert.equal(tabs[0].querySelector('span').textContent, 'Hoy');
    assert.match(w.document.querySelector('.wx-verdict').textContent, /Precaución/);
});

test('elegir un día cambia el resumen y las horas, y mueve la pestaña activa', async () => {
    const w = await setup(ok({ municipalities: [{ name: 'Sevilla', fields: [], daily: DAILY }], errors: [] }));
    const doc = w.document;
    const card = doc.querySelector('[data-card-id]');
    assert.match(card.querySelector('.wx-verdict').textContent, /Apto para tratar/);
    card.querySelectorAll('[data-day-idx]')[1].click();
    const cells = [...card.querySelectorAll('.dt-cell')].map(c => c.textContent.replace(/\s+/g, ' ').trim());
    assert.match(cells[0], /Adverso Sin horas buenas/);
    assert.match(cells[1], /Viento máx\. 8 km\/h/);
    assert.match(cells[2], /Lluvia 80 % 4,5 L\/m²/);
    assert.match(cells[3], /Temperatura 2° – 9° Despejado/);
    assert.ok(card.querySelector('.wx-verdict').classList.contains('dt-tone-0'));
    assert.deepEqual([...card.querySelectorAll('[data-day-idx]')].map(d => d.getAttribute('aria-pressed')), ['false', 'true']);
    assert.ok(card.querySelector('.hm-hours').getAttribute('aria-label').startsWith('Hora a hora, Vie 2'));
});

test('el veredicto da las horas buenas del día y el viento usa el nivel del servidor', async () => {
    const d = day('2099-01-01', 'Jue 1', { wind_level: 3, max_wind_speed: 24,
        hours: [hour('2099-01-01', 8), hour('2099-01-01', 9), hour('2099-01-01', 10, { level: 'bad' }), hour('2099-01-01', 15)] });
    const w = await setup(ok({ municipalities: [{ name: 'Sevilla', fields: [], daily: [d] }], errors: [] }));
    assert.match(w.document.querySelector('.wx-verdict').textContent, /08:00–10:00 · 15:00–16:00/);
    assert.ok(w.document.querySelectorAll('.dt-cell')[1].querySelector('.dt-fg-0'));   // nivel 3 → rojo
});

test('un día sin horas lo dice en vez de dejar un hueco', async () => {
    const d = day('2099-01-01', 'Jue 1', { hours: [] });
    const w = await setup(ok({ municipalities: [{ name: 'Sevilla', fields: [], daily: [d] }], errors: [] }));
    assert.match(w.document.querySelector('.wx-verdict').textContent, /Sin detalle por horas/);
    assert.match(w.document.querySelector('.hm-wx-day').textContent, /solo da la previsión por horas/);
    assert.equal(w.document.querySelector('.hm-hours'), null);
});

test('los errores se agrupan por motivo y se escapan', async () => {
    const w = await setup(ok({ municipalities: [], errors: [{ reason: 'AEMET <no> responde', fields: ['A', 'B'] }] }));
    const card = w.document.querySelector('.hm-empty');
    assert.match(card.textContent, /Sin previsión por ahora/);
    assert.equal(card.querySelector('li').textContent, 'A, B — AEMET <no> responde');
    assert.ok(card.querySelector('.wov-retry'));
    assert.equal(w.document.getElementById('wov-subtitle').textContent, 'Sin datos disponibles');
});

test('con municipios y algunas parcelas fallidas, el aviso va después de las tarjetas', async () => {
    const w = await setup(ok({ municipalities: [{ name: 'Sevilla', fields: [], daily: DAILY }], errors: [{ reason: 'Sin ubicación', fields: ['Huerta'] }] }));
    const grid = w.document.getElementById('wov-grid');
    assert.equal(grid.children.length, 2);
    assert.match(grid.lastElementChild.textContent, /No se pudo cargar la previsión de esta parcela/);
    assert.ok(!grid.querySelector('.wov-retry'));
});

test('si falla la llamada, todas las parcelas con el motivo del servidor', async () => {
    const w = await setup(() => Promise.reject({ status: 503, msg: 'Falta la clave de AEMET en la configuración.' }));
    const items = [...w.document.querySelectorAll('.hm-empty li')].map(li => li.textContent);
    assert.equal(items.length, 1);
    assert.match(items[0], /Huerta/);
    assert.match(items[0], /Falta la clave de AEMET/);
});

test('sin municipios ni errores: aviso de que no hay datos', async () => {
    const w = await setup(ok({ municipalities: [], errors: [] }));
    assert.match(w.document.querySelector('.hm-empty').textContent, /Sin datos de tus parcelas/);
});

test('las horas son celdas con su nivel y el detalle en el título', async () => {
    const w = await setup(ok({ municipalities: [], errors: [] }));
    const html = w.AgroWeatherOverview.hourCell(hour('2099-01-01', 7, { level: 'bad', precipitation: 1.5, precipitation_probability: 70, wind_speed: 26.4, temperature: 9.6 }));
    assert.match(html, /hm-h hm-h--bad/);
    assert.match(html, /title="07:00 · hora mala · 10° · viento 26 km\/h · lluvia 70 % · 1,5 L\/m²"/);
    assert.match(html, /<span>7<\/span><em>10°<\/em><b>26<\/b><i>70<\/i>/);
});

test('nombres y textos del servidor se escapan', async () => {
    const evil = day('2099-01-01', 'Jue <i>1</i>', { label_weather: '<img src=x onerror=alert(1)>' });
    const w = await setup(ok({ municipalities: [{ name: '<script>x</script>', fields: [], daily: [evil] }], errors: [] }));
    const doc = w.document;
    assert.equal(doc.querySelector('script:not([type])'), null);
    assert.equal(doc.querySelector('img'), null);
    assert.equal(doc.querySelector('.dt-card-title').textContent.trim(), '<script>x</script>');
});

test('si falla al pintar se avisa y se quita la carga', async () => {
    const errors = [];
    const w = await setup(() => Promise.resolve({ municipalities: [{ name: 'Roto' }] }), (win) => { win.console.error = (e) => errors.push(e); });
    assert.ok(w.document.querySelector('[role="alert"]'));
    assert.ok(w.document.getElementById('wov-skeletons').classList.contains('d-none'));
    assert.equal(errors.length, 1);
});

test('hoy se enseñan solo las horas que quedan', async () => {
    const now = new Date();
    const date = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
    const hours = [...Array(24).keys()].map(h => hour(date, h));
    const today = day(date, 'Hoy', { hours, sunrise: null, sunset: null });
    const w = await setup(ok({ municipalities: [{ name: 'Sevilla', fields: [], daily: [today] }], errors: [] }));
    const times = [...w.document.querySelectorAll('.hm-h > span')].map(e => Number.parseInt(e.textContent, 10));
    assert.equal(times[0], now.getHours());
    assert.equal(times.length, 24 - now.getHours());
});

test('sin mensaje del servidor: sesión caducada (401) o mensaje general', async () => {
    let w = await setup(() => Promise.reject({ status: 401 }));
    assert.match(w.document.querySelector('.hm-empty li').textContent, /sesión ha caducado/);
    w = await setup(() => Promise.reject({ status: 500 }));
    assert.match(w.document.querySelector('.hm-empty li').textContent, /No se ha podido cargar la previsión/);
});

test('con datos antiguos las pestañas empiezan en hoy y no pasan de 7', async () => {
    const today = localToday();
    const past = [day('2000-01-01', 'Sáb 1'), day('2000-01-02', 'Dom 2')];
    const future = [...Array(9).keys()].map(i => day(i === 0 ? today : `2099-02-${String(i + 1).padStart(2, '0')}`, i === 0 ? 'Hoy' : `D${i}`));
    const w = await setup(ok({ municipalities: [{ name: 'Sevilla', fields: [], daily: [...past, ...future], stale: true }], errors: [] }));
    const tabs = [...w.document.querySelectorAll('[data-day-idx]')];
    assert.equal(tabs.length, 7);
    assert.equal(tabs[0].dataset.dayIdx, '2');
    assert.equal(tabs[0].querySelector('span').textContent, 'Hoy');
    assert.equal(tabs[0].getAttribute('aria-pressed'), 'true');
    tabs[6].click();
    assert.equal(w.document.querySelector('[data-wx-body]').getAttribute('aria-live'), 'polite');
    assert.match(w.document.querySelector('.hm-hours').getAttribute('aria-label'), /^Hora a hora, D6/);
});

test('si todos los días son pasados se avisa en vez de enseñar uno como hoy', async () => {
    const w = await setup(ok({ municipalities: [{ name: 'Sevilla', fields: [], daily: [day('2000-01-01', 'Sáb 1')], stale: true }], errors: [] }));
    assert.match(w.document.querySelector('[data-card-id]').textContent, /Previsión caducada/);
    assert.equal(w.document.querySelector('[data-day-idx]'), null);
    assert.equal(w.document.querySelector('.dt-summary'), null);
});

test('el viento máximo lleva coma decimal', async () => {
    const d = day('2099-01-01', 'Jue 1', { max_wind_speed: 12.5, wind_level: 1 });
    const w = await setup(ok({ municipalities: [{ name: 'Sevilla', fields: [], daily: [d] }], errors: [] }));
    assert.match(w.document.querySelectorAll('.dt-cell')[1].textContent.replace(/\s+/g, ' '), /12,5 km\/h/);
});

test('los tres niveles de viento se pintan verde, ámbar y rojo', async () => {
    const expected = { 0: 'dt-fg-3', 1: 'dt-fg-1', 2: 'dt-fg-1', 3: 'dt-fg-0' };
    for (const [level, cls] of Object.entries(expected)) {
        const d = day('2099-01-01', 'Jue 1', { wind_level: Number(level) });
        const w = await setup(ok({ municipalities: [{ name: 'Sevilla', fields: [], daily: [d] }], errors: [] }));
        assert.ok(w.document.querySelectorAll('.dt-cell')[1].querySelector(`.dt-value.${cls}`), `nivel ${level}`);
    }
});

test('la lluvia es ámbar desde el 20 % y roja desde el 50 %, como la rejilla', async () => {
    const expected = { 10: null, 20: 'dt-fg-1', 49: 'dt-fg-1', 50: 'dt-fg-0' };
    for (const [prob, cls] of Object.entries(expected)) {
        const d = day('2099-01-01', 'Jue 1', { max_precipitation_probability: Number(prob) });
        const w = await setup(ok({ municipalities: [{ name: 'Sevilla', fields: [], daily: [d] }], errors: [] }));
        const v = w.document.querySelectorAll('.dt-cell')[2].querySelector('.dt-value');
        assert.equal(cls ? v.classList.contains(cls) : /dt-fg/.test(v.className), !!cls, `prob ${prob}`);
    }
});

test('start() repetido no duplica el listener de clic', async () => {
    const w = await setup(ok({ municipalities: [{ name: 'Sevilla', fields: [], daily: DAILY }], errors: [] }));
    let adds = 0;
    const orig = w.document.addEventListener.bind(w.document);
    w.document.addEventListener = (...a) => { adds++; return orig(...a); };
    await w.AgroWeatherOverview.start();
    await w.AgroWeatherOverview.start();
    assert.equal(adds, 0);
    const card = w.document.querySelector('[data-card-id]');
    card.querySelectorAll('[data-day-idx]')[1].click();
    assert.equal(card.querySelectorAll('[data-day-idx]')[1].getAttribute('aria-pressed'), 'true');
});
