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

test('typeColorMap: mismo orden que la rosquilla y «Otros» cuando no hay colores para todos', () => {
    assert.deepEqual(FC.typeColorMap([t('A', 3), t('B', 2), t('C', 0)], SERIES, OTHER), { A: '#1', B: '#2' });
    assert.deepEqual(FC.typeColorMap([t('A', 4), t('B', 3), t('C', 2), t('D', 1)], SERIES, OTHER),
        { A: '#1', B: '#2', C: OTHER, D: OTHER });
});

test('barSegments: un tramo por tipo y los de «Otros» juntos al final', () => {
    const colors = { A: '#1', B: '#2', C: OTHER, D: OTHER };
    const segs = FC.barSegments(FC.typeShares([t('C', 10), t('A', 50), t('D', 10), t('B', 30)]), colors, OTHER);
    assert.deepEqual(segs, [
        { name: 'A', pct: 50, color: '#1' },
        { name: 'B', pct: 30, color: '#2' },
        { name: 'Otros', pct: 20, color: OTHER },
    ]);
});

test('barSegments: un tipo que no está en el mapa general cae en «Otros»', () => {
    assert.deepEqual(FC.barSegments([{ type_name: 'Z', total: 1, pct: 100 }], {}, OTHER), [{ name: 'Otros', pct: 100, color: OTHER }]);
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
