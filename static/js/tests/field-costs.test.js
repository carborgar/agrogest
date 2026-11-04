// Ejecutar con: npm run test:js
const test = require('node:test');
const assert = require('node:assert/strict');

const FC = require('../field-costs.js');

const SERIES = ['#1', '#2', '#3'];
const OTHER = '#o';
const t = (type_name, total) => ({ type_name, total, products: [] });
const names = (xs) => xs.map(x => x.type_name || x.name);

test('rankTypes: de más a menos gasto (a igualdad, por nombre) y sin «Resto» si caben todos', () => {
    const r = FC.rankTypes([t('B', 10), t('C', 30), t('A', 10)], 6);
    assert.deepEqual(names(r.top), ['C', 'A', 'B']);
    assert.deepEqual(r.rest, []);
});

test('rankTypes: con más de 6 tipos, los 6 primeros arriba y el resto aparte (aunque sobre uno solo)', () => {
    const types = Array.from({ length: 12 }, (_, i) => t('T' + String(i).padStart(2, '0'), 120 - i * 10));
    const r = FC.rankTypes(types, FC.MAX_TYPES);
    assert.equal(r.top.length, 6);
    assert.deepEqual(names(r.rest), ['T06', 'T07', 'T08', 'T09', 'T10', 'T11']);
    assert.equal(FC.rankTypes(types.slice(0, 7), FC.MAX_TYPES).rest.length, 1);
    assert.deepEqual(FC.rankTypes(undefined, 6), { top: [], rest: [] });
});

test('typeColorMap: un color por tipo del ranking, en orden', () => {
    assert.deepEqual(FC.typeColorMap([t('A', 3), t('B', 2), t('C', 0)], SERIES), { A: '#1', B: '#2', C: '#3' });
});

test('restShades: un gris distinto por tipo del «Resto»', () => {
    const shades = FC.restShades(6);
    assert.equal(shades.length, 6);
    assert.equal(new Set(shades).size, 6);
    assert.equal(FC.restShades(1).length, 1);
    assert.deepEqual(FC.restShades(0), []);
});

test('typeShares: % por tipo calculado con los totales de la parcela, de más a menos', () => {
    const shares = FC.typeShares([t('Abono', 25), t('Fungicida', 75), t('Sin precio', 0)]);
    assert.deepEqual(names(shares), ['Fungicida', 'Abono']);
    assert.deepEqual(shares.map(s => s.pct), [75, 25]);
    assert.deepEqual(FC.typeShares(undefined), []);
});

test('barSegments: un tramo por tipo con color y los demás juntos en «Resto» al final', () => {
    const colors = { A: '#1', B: '#2' };
    const segs = FC.barSegments(FC.typeShares([t('C', 10), t('A', 50), t('D', 10), t('B', 30)]), colors, OTHER);
    assert.deepEqual(segs, [
        { name: 'A', pct: 50, color: '#1' },
        { name: 'B', pct: 30, color: '#2' },
        { name: 'Resto', pct: 20, color: OTHER },
    ]);
});

test('barSegments: un tipo real llamado «Otros» no se confunde con el grupo de sobrantes', () => {
    const segs = FC.barSegments(FC.typeShares([t('Otros', 50), t('A', 30), t('B', 10), t('C', 10)]), { Otros: '#1', A: '#2' }, OTHER);
    assert.equal(FC.REST_LABEL, 'Resto');
    assert.deepEqual(names(segs), ['Otros', 'A', 'Resto']);
});

test('sortFields: por gasto o por €/ha, de más a menos y, a igualdad, por nombre; no cambia el original', () => {
    const fields = [
        { name: 'Olivar', total_cost: 500, cost_per_ha: 10 },
        { name: 'Almendros', total_cost: 100, cost_per_ha: 10 },
        { name: 'Viña', total_cost: 300, cost_per_ha: 30 },
    ];
    assert.deepEqual(FC.sortFields(fields, 'cost').map(f => f.name), ['Olivar', 'Viña', 'Almendros']);
    assert.deepEqual(FC.sortFields(fields, 'perha').map(f => f.name), ['Viña', 'Almendros', 'Olivar']);
    assert.equal(fields[0].name, 'Olivar');
});

test('perHaRanking y topField: ignoran parcelas sin gasto o sin superficie', () => {
    const fields = [
        { name: 'Sin superficie', total_cost: 500, area: 0, cost_per_ha: 0 },
        { name: 'Sin gasto', total_cost: 0, area: 2, cost_per_ha: 0 },
        { name: 'Olivar', total_cost: 100, area: 4, cost_per_ha: 25 },
        { name: 'Viña', total_cost: 100, area: 2, cost_per_ha: 50 },
    ];
    assert.deepEqual(FC.perHaRanking(fields).map(f => f.name), ['Viña', 'Olivar']);
    assert.equal(FC.topField(fields).name, 'Viña');
    assert.equal(FC.topField(fields.slice(0, 2)), null);
});

test('allOpen: «Cerrar parcelas» solo con todas abiertas', () => {
    assert.equal(FC.allOpen([true, true]), true);
    assert.equal(FC.allOpen([true, false]), false);
    assert.equal(FC.allOpen([]), false);
});

const sum = (xs) => Math.round(xs.reduce((s, v) => s + v, 0) * 10) / 10;

test('roundPcts: tres tercios suman 100,0 y la décima sobrante va al primero', () => {
    const r = FC.roundPcts([100 / 3, 100 / 3, 100 / 3]);
    assert.deepEqual(r, [33.4, 33.3, 33.3]);
    assert.equal(sum(r), 100);
});

test('roundPcts: el redondeo simple daría 100,1 y el mayor resto deja 100,0', () => {
    const raw = [33.35, 33.35, 33.3];
    const r = FC.roundPcts(raw);
    assert.equal(sum(r), 100);
    r.forEach((v, i) => assert.ok(Math.abs(v - raw[i]) <= 0.1));
});

test('roundPcts: se respetan los repartos exactos y sin reparto completo no inventa décimas', () => {
    assert.deepEqual(FC.roundPcts([75, 25]), [75, 25]);
    assert.deepEqual(FC.roundPcts([]), []);
    assert.deepEqual(FC.roundPcts(undefined), []);
});

test('sharePcts: % sobre la suma que dan 100,0; los importes a 0 quedan en 0 y sin gasto todo es 0', () => {
    for (let n = 2; n <= 12; n++) {
        const totals = Array.from({ length: n }, (_, i) => (i * 37 % 11) + 1.13 * (i + 1));
        assert.equal(sum(FC.sharePcts(totals)), 100, `n=${n}`);
    }
    assert.deepEqual(FC.sharePcts([30, 10, 0]), [75, 25, 0]);
    assert.deepEqual(FC.sharePcts([0, 0]), [0, 0]);
});

test('«Resto» + los 6 primeros suman 100,0 al sumar sus % ya redondeados', () => {
    const types = Array.from({ length: 12 }, (_, i) => t('T' + i, 1000 / (i + 1.7)));
    const r = FC.rankTypes(types, FC.MAX_TYPES);
    const pcts = FC.sharePcts(r.top.concat(r.rest).map(x => x.total));
    const restPct = Math.round(pcts.slice(6).reduce((s, v) => s + v, 0) * 10) / 10;
    assert.equal(sum(pcts.slice(0, 6).concat(restPct)), 100);
});

test('fmt: separador de miles también con 4 cifras y la unidad pegada a la cifra', () => {
    const NB = ' ';
    assert.equal(FC.fmt.eur(2226.83), `2.226,83${NB}€`);
    assert.equal(FC.fmt.eur(52308.29), `52.308,29${NB}€`);
    assert.equal(FC.fmt.eurHa(2226.83), `2.226,83${NB}€/ha`);
    assert.equal(FC.fmt.eur(12.5), `12,50${NB}€`);
    assert.equal(FC.fmt.num(1250), '1.250');
    assert.equal(FC.fmt.pct(28), `28${NB}%`);
    assert.equal(FC.fmt.pct(33.3), `33,3${NB}%`);
});
