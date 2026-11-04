// Ejecutar con: npm run test:js
const test = require('node:test');
const assert = require('node:assert/strict');

const FC = require('../field-costs.js');

const SERIES = ['#1', '#2', '#3'];
const OTHER = '#o';
const t = (type_name, total) => ({ type_name, total, products: [] });

test('typeShares: % por tipo calculado con los totales de la parcela, de más a menos', () => {
    const shares = FC.typeShares([t('Abono', 25), t('Fungicida', 75), t('Sin precio', 0)]);
    assert.deepEqual(shares.map(s => s.type_name), ['Fungicida', 'Abono']);
    assert.deepEqual(shares.map(s => s.pct), [75, 25]);
});

test('typeShares: sin gasto o sin desglose no hay tramos', () => {
    assert.deepEqual(FC.typeShares([t('Abono', 0)]), []);
    assert.deepEqual(FC.typeShares(undefined), []);
});

test('typeColorMap: mismo orden que la rosquilla y «Resto» cuando no hay colores para todos', () => {
    assert.deepEqual(FC.typeColorMap([t('A', 3), t('B', 2), t('C', 0)], SERIES, OTHER), { A: '#1', B: '#2' });
    assert.deepEqual(FC.typeColorMap([t('A', 4), t('B', 3), t('C', 2), t('D', 1)], SERIES, OTHER),
        { A: '#1', B: '#2', C: OTHER, D: OTHER });
});

test('barSegments: un tramo por tipo y los de «Resto» juntos al final', () => {
    const colors = { A: '#1', B: '#2', C: OTHER, D: OTHER };
    const segs = FC.barSegments(FC.typeShares([t('C', 10), t('A', 50), t('D', 10), t('B', 30)]), colors, OTHER);
    assert.deepEqual(segs, [
        { name: 'A', pct: 50, color: '#1' },
        { name: 'B', pct: 30, color: '#2' },
        { name: 'Resto', pct: 20, color: OTHER },
    ]);
});

test('barSegments: un tipo que no está en el mapa general cae en «Resto»', () => {
    assert.deepEqual(FC.barSegments([{ type_name: 'Z', total: 1, pct: 100 }], {}, OTHER), [{ name: 'Resto', pct: 100, color: OTHER }]);
});

test('sortFields: de más a menos €/ha y, a igualdad, por nombre; no cambia el original', () => {
    const fields = [{ name: 'Olivar', cost_per_ha: 10 }, { name: 'Almendros', cost_per_ha: 10 }, { name: 'Viña', cost_per_ha: 30 }];
    assert.deepEqual(FC.sortFields(fields).map(f => f.name), ['Viña', 'Almendros', 'Olivar']);
    assert.equal(fields[0].name, 'Olivar');
});

test('topField: ignora parcelas sin gasto o sin superficie', () => {
    const fields = [
        { name: 'Sin superficie', total_cost: 500, area: 0, cost_per_ha: 0 },
        { name: 'Sin gasto', total_cost: 0, area: 2, cost_per_ha: 0 },
        { name: 'Viña', total_cost: 100, area: 2, cost_per_ha: 50 },
        { name: 'Olivar', total_cost: 100, area: 4, cost_per_ha: 25 },
    ];
    assert.equal(FC.topField(fields).name, 'Viña');
    assert.equal(FC.topField(fields.slice(0, 2)), null);
});

test('allOpen: «Plegar todo» solo con todas abiertas', () => {
    assert.equal(FC.allOpen([true, true]), true);
    assert.equal(FC.allOpen([true, false]), false);
    assert.equal(FC.allOpen([]), false);
});

test('barSegments: un tipo real llamado «Otros» no se confunde con el grupo de sobrantes', () => {
    const colors = { Otros: '#1', A: '#2', B: OTHER, C: OTHER };
    const segs = FC.barSegments(FC.typeShares([t('Otros', 50), t('A', 30), t('B', 10), t('C', 10)]), colors, OTHER);
    assert.equal(FC.REST_LABEL, 'Resto');
    assert.deepEqual(segs.map(s => s.name), ['Otros', 'A', 'Resto']);
});

const sum = (xs) => Math.round(xs.reduce((s, v) => s + v, 0) * 10) / 10;

test('roundPcts: tres tercios suman 100,0 y la décima sobrante va al primero', () => {
    const r = FC.roundPcts([100 / 3, 100 / 3, 100 / 3]);
    assert.deepEqual(r, [33.4, 33.3, 33.3]);
    assert.equal(sum(r), 100);
});

test('roundPcts: el redondeo simple daría 100,1 y el mayor resto deja 100,0', () => {
    const raw = [33.35, 33.35, 33.3];  // a una décima: 33,4 + 33,4 + 33,3 = 100,1
    const r = FC.roundPcts(raw);
    assert.equal(sum(r), 100);
    r.forEach((v, i) => assert.ok(Math.abs(v - raw[i]) <= 0.1));
});

test('roundPcts: se respetan los repartos exactos y siempre suma 100,0', () => {
    assert.deepEqual(FC.roundPcts([75, 25]), [75, 25]);
    assert.deepEqual(FC.roundPcts([100]), [100]);
    for (let n = 2; n <= 9; n++) {
        const totals = Array.from({ length: n }, (_, i) => (i * 37 % 11) + 1.13 * (i + 1));
        const all = totals.reduce((s, v) => s + v, 0);
        assert.equal(sum(FC.roundPcts(totals.map(v => v / all * 100))), 100, `n=${n}`);
    }
});

test('roundPcts: sin reparto completo (vacío) no inventa décimas', () => {
    assert.deepEqual(FC.roundPcts([]), []);
    assert.deepEqual(FC.roundPcts(undefined), []);
});

test('coalesce: muchas peticiones seguidas (plegar todo) dan una sola sincronización', () => {
    let calls = 0;
    const queue = [];
    const sync = FC.coalesce(() => { calls += 1; }, (cb) => queue.push(cb));
    for (let i = 0; i < 50; i++) sync();
    assert.equal(queue.length, 1);
    assert.equal(calls, 0);
    queue.shift()();
    assert.equal(calls, 1);
    sync();  // tras sincronizar, un nuevo «toggle» vuelve a programar
    assert.equal(queue.length, 1);
});
