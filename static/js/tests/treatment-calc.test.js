// Ejecutar con: npm run test:js
// Comprueba treatment-calc.js contra el MISMO fichero de casos que usa Python
// (farm/tests/fixtures/treatment_calc_cases.json): fórmulas atadas en los dos lados.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const calc = require('../treatment-calc.js');

const DATA = JSON.parse(fs.readFileSync(
    path.join(__dirname, '..', '..', '..', 'farm', 'tests', 'fixtures', 'treatment_calc_cases.json'), 'utf8'));

const near = (actual, expected, eps, msg) => {
    assert.ok(actual !== null && Math.abs(actual - expected) <= eps, `${msg}: ${actual} != ${expected}`);
};

// ── Casos compartidos con Python ──────────────────────────────────────────────

for (const c of DATA.cases) {
    test(`caso ${c.id}: ${c.title}`, () => {
        const i = c.input, e = c.expected;
        const area = calc.effectiveArea(i.field_area, i.applied_area);
        const water = i.real_water_per_ha || i.water_per_ha;       // Treatment.actual_water_per_ha
        const price = Number(i.price);

        let total, dose;
        if (i.total_override) {
            total = Number(i.total_override);
            dose = calc.doseFromTotal(total, i.dose_type, area, water);
        } else {
            dose = Number(i.dose);
            total = calc.totalFromDose(dose, i.dose_type, area, water);
        }
        assert.equal(total, e.total_dose, 'total');        // igualdad EXACTA, sin tolerancia
        assert.equal(dose, e.dose, 'dosis');
        assert.equal(calc.totalUnit(i.dose_type), e.total_dose_unit);

        const cost = calc.lineCost(total, price);
        assert.equal(cost, e.total_price, 'coste');
        assert.equal(calc.costPerHa(cost, area), e.price_per_ha, '€/ha');

        const loads = i.type === 'spraying' ? calc.machineLoads(area, water, i.capacity) : null;
        if (e.loads === null) {
            assert.equal(loads, null);
        } else {
            assert.deepEqual(loads, {
                totalWater: e.loads.total_water, fullLoads: e.loads.full_loads,
                partialWater: e.loads.partial_water, partialLoad: e.loads.partial_load,
            });
        }

        // En fertirrigación el modelo devuelve el total; el JS no tiene «por cuba» ahí.
        if (i.type === 'spraying') {
            const perLoad = calc.dosePerFullLoad(dose, i.dose_type, i.capacity, water);
            if (e.dose_per_load === null) assert.equal(perLoad, null);
            else assert.equal(perLoad, e.dose_per_load, 'por cuba');
        }
        assert.equal(calc.dosePartialLoad(dose, i.dose_type, loads, water), e.partial_product, 'cuba parcial');
    });
}

test('redondeo de dosis hacia arriba a 3 decimales (caso J)', () => {
    for (const r of DATA.rounding) {
        assert.equal(calc.roundDoseUp(calc.parseNumber(r.input)), Number(r.expected), r.id);
    }
    assert.equal(calc.roundDoseUp(0.0754), 0.076);
    assert.equal(calc.roundDoseUp(1.0001), 1.001);
    assert.equal(calc.roundDoseUp(2.1), 2.1);
    assert.equal(calc.roundDoseUp(0.3), 0.3);
    assert.equal(calc.roundDoseUp(0.0750004), 0.076); // Python: ROUND_UP
    assert.equal(calc.roundDoseUp(-1), null);
    assert.equal(calc.roundDoseUp(NaN), null);
});

// ── Casos límite ──────────────────────────────────────────────────────────────

test('sin mojado, las dosis por volumen y % no se pueden calcular (null, nunca 0 ni NaN)', () => {
    for (const dt of ['kg_per_1000l', 'l_per_1000l', 'pct']) {
        assert.equal(calc.totalFromDose(2, dt, 4.2, null), null, dt);
        assert.equal(calc.totalFromDose(2, dt, 4.2, 0), null, dt);
        assert.equal(calc.doseFromTotal(5, dt, 4.2, null), null, dt);
    }
    // por hectárea no depende del mojado
    assert.equal(calc.totalFromDose(3, 'kg_per_ha', 4.2, null), 12.6);
    assert.equal(calc.doseFromTotal(10, 'l_per_ha', 4, undefined), 2.5);
});

test('área 0, negativa o ausente → null', () => {
    assert.equal(calc.totalFromDose(3, 'kg_per_ha', 0, 1000), null);
    assert.equal(calc.totalFromDose(3, 'kg_per_ha', -1, 1000), null);
    assert.equal(calc.totalFromDose(3, 'kg_per_ha', null, 1000), null);
    assert.equal(calc.doseFromTotal(3, 'kg_per_ha', 0, 1000), null);
    assert.equal(calc.machineLoads(0, 1000, 2000), null);
});

test('dosis o total no numéricos o negativos → null', () => {
    assert.equal(calc.totalFromDose(NaN, 'kg_per_ha', 4, 1000), null);
    assert.equal(calc.totalFromDose(null, 'kg_per_ha', 4, 1000), null);
    assert.equal(calc.totalFromDose(-1, 'kg_per_ha', 4, 1000), null);
    assert.equal(calc.doseFromTotal(-5, 'kg_per_ha', 4, 1000), null);
    assert.equal(calc.totalFromDose(1, 'desconocido', 4, 1000), null);
});

test('máquina o mojado ausentes → sin cubas', () => {
    assert.equal(calc.machineLoads(4.2, 1000, null), null);
    assert.equal(calc.machineLoads(4.2, null, 2000), null);
    assert.equal(calc.dosePerFullLoad(1, 'l_per_1000l', null, 1000), null);
    assert.equal(calc.dosePerFullLoad(1, 'kg_per_ha', 2000, null), null);
});

test('umbral de cuba parcial: 50 L no cuenta, 51 sí', () => {
    assert.equal(calc.machineLoads(1, 2050, 2000).partialLoad, false);
    assert.equal(calc.machineLoads(1, 2051, 2000).partialLoad, true);
    assert.equal(calc.dosePartialLoad(1, 'l_per_1000l', calc.machineLoads(1, 2050, 2000), 2050), 0);
});

test('total de agua redondea como Python (mitad al par)', () => {
    assert.equal(calc.machineLoads(1.25, 10, 2000).totalWater, 12);   // round(12.5) = 12
    assert.equal(calc.machineLoads(1.35, 10, 2000).totalWater, 14);   // round(13.5) = 14
    assert.equal(calc.machineLoads(4.2, 1100, 2000).totalWater, 4620); // 4620.000000000001
});

test('effectiveArea', () => {
    assert.equal(calc.effectiveArea(4.2, 2), 2);
    assert.equal(calc.effectiveArea(4.2, null), 4.2);
    assert.equal(calc.effectiveArea(4.2, 0), 4.2);
});

test('totalUnit: pct se mide en litros', () => {
    assert.equal(calc.totalUnit('kg_per_ha'), 'kg');
    assert.equal(calc.totalUnit('kg_per_1000l'), 'kg');
    assert.equal(calc.totalUnit('l_per_ha'), 'L');
    assert.equal(calc.totalUnit('pct'), 'L');
});

test('lineCost y costPerHa', () => {
    assert.equal(calc.lineCost(12.6, 9.5), 119.7);
    assert.equal(calc.lineCost(null, 9.5), null);
    assert.equal(calc.lineCost(12.6, 0), 0);
    assert.equal(calc.costPerHa(119.7, 4.2), 28.5);
    assert.equal(calc.costPerHa(119.7, 0), null);
});

test('deviation y aviso de dosis (25 %)', () => {
    assert.equal(calc.DOSE_WARNING_RATIO, 0.25);
    assert.equal(calc.deviation(1.5, 2), 0.25);
    assert.equal(calc.deviation(1, 0), null);
    assert.equal(calc.deviation(null, 2), null);
    assert.equal(calc.isFarFromRecommended(1.5, 2), true);
    assert.equal(calc.isFarFromRecommended(1.6, 2), false);
});

// ── parseNumber ───────────────────────────────────────────────────────────────

test('parseNumber: coma o punto, espacios, vacío y basura', () => {
    const p = calc.parseNumber;
    assert.equal(p('0,5'), 0.5);
    assert.equal(p('0.5'), 0.5);
    assert.equal(p(' 12 '), 12);
    assert.equal(p('1 000'), 1000);
    assert.equal(p('0,075'), 0.075);
    assert.equal(p('0.075'), 0.075);
    assert.equal(p('1,000'), 1);
    assert.equal(p('.5'), 0.5);
    assert.equal(p('5,'), 5);
    assert.equal(p('0'), 0);
    assert.equal(p(''), null);
    assert.equal(p('   '), null);
    assert.equal(p(null), null);
    assert.equal(p(undefined), null);
    assert.equal(p('abc'), null);
    assert.equal(p('1,2,3'), null);
    assert.equal(p('1e3'), null);
    assert.equal(p('-1'), null);
    assert.equal(p('--'), null);
});

test('parseNumber: «1.000» es ambiguo y se rechaza; «0.075» no', () => {
    assert.equal(calc.parseNumber('1.000'), null);
    assert.equal(calc.parseNumber('2.500'), null);
    assert.equal(calc.parseNumber('1.000.000'), null);
    assert.equal(calc.parseNumber('1.000,5'), null);
    assert.equal(calc.parseNumber('0.075'), 0.075);
    assert.equal(calc.parseNumber('1.25'), 1.25);
    assert.equal(calc.parseNumber('1.2500'), 1.25);
});

test('parseNumber acepta números y rechaza no finitos o negativos', () => {
    assert.equal(calc.parseNumber(3), 3);
    assert.equal(calc.parseNumber(-3), null);
    assert.equal(calc.parseNumber(NaN), null);
    assert.equal(calc.parseNumber(Infinity), null);
});

// ── Números del servidor (punto decimal) frente a lo que teclea el usuario ───

test('parseServerNumber: punto decimal estricto; «1.500» es uno y medio', () => {
    assert.equal(calc.parseServerNumber('1.500'), 1.5);
    assert.equal(calc.parseServerNumber('2.381'), 2.381);
    assert.equal(calc.parseServerNumber('12.6000'), 12.6);
    assert.equal(calc.parseServerNumber('1000'), 1000);
    assert.equal(calc.parseServerNumber(3.25), 3.25);
    for (const bad of ['', ' ', '1,5', '1.2.3', '-1', 'abc', '1e3', null, undefined]) assert.equal(calc.parseServerNumber(bad), null, String(bad));
});

test('parseNumber (lo que teclea el usuario) sigue rechazando «1.500» y hasThousandsDot lo detecta', () => {
    assert.equal(calc.parseNumber('1.500'), null);
    assert.equal(calc.hasThousandsDot('1.500'), true);
    assert.equal(calc.hasThousandsDot('2.381'), true);
    assert.equal(calc.hasThousandsDot('1.500.000'), true);
    for (const ok of ['0.075', '1.5', '1,500', '12', '1.50', '']) assert.equal(calc.hasThousandsDot(ok), false, ok);
});

test('numberToText: coma decimal, sin miles y sin ceros finales', () => {
    assert.equal(calc.numberToText(1.5, 4), '1,5');
    assert.equal(calc.numberToText(1500, 4), '1500');
    assert.equal(calc.numberToText(2.381, 4), '2,381');
    assert.equal(calc.numberToText(2.3810, 4), '2,381');
    assert.equal(calc.numberToText(0.4762, 4), '0,4762');
    assert.equal(calc.numberToText(null), '');
    // ida y vuelta con lo que parsea el usuario
    for (const n of [1.5, 2.381, 0.075, 1500, 12.6, 0.4762]) assert.equal(calc.parseNumber(calc.numberToText(n, 4)), n);
});
