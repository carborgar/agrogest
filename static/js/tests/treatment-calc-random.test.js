// Test diferencial: casos aleatorios calculados por el MODELO REAL de Django
// (farm/tests/test_treatment_calc_differential.py → farm/tests/fixtures/treatment_calc_random.json).
// treatment-calc.js tiene que dar EXACTAMENTE los mismos valores: sin tolerancia.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const calc = require('../treatment-calc.js');
const CASES = JSON.parse(fs.readFileSync(
    path.join(__dirname, '..', '..', '..', 'farm', 'tests', 'fixtures', 'treatment_calc_random.json'), 'utf8'));

test('hay casos suficientes', () => {
    assert.ok(CASES.length >= 500);
});

test('treatment-calc.js coincide exactamente con el backend en todos los casos aleatorios', () => {
    const bad = [];
    for (const c of CASES) {
        const o = c.out;
        const area = calc.effectiveArea(c.area, c.applied_area);
        const water = c.real_water || c.water;                         // Treatment.actual_water_per_ha
        const price = Number(c.price);
        let total, dose;
        if (c.total_override) {
            total = Number(c.total_override);
            dose = calc.doseFromTotal(total, c.dose_type, area, water);
        } else {
            dose = Number(c.dose);
            total = calc.totalFromDose(dose, c.dose_type, area, water);
        }
        const got = { total_dose: total, dose: dose };
        got.total_price = calc.lineCost(total, price);
        got.price_per_ha = calc.costPerHa(got.total_price, area);
        const want = {
            total_dose: Number(o.total_dose), dose: Number(o.dose),
            total_price: Number(o.total_price), price_per_ha: Number(o.price_per_ha),
        };
        if (c.type === 'spraying') {
            const loads = calc.machineLoads(area, water, c.capacity);
            got.loads = loads && { total_water: loads.totalWater, full_loads: loads.fullLoads, partial_load: loads.partialLoad, partial_water: loads.partialWater };
            want.loads = o.loads;
            got.dose_per_load = calc.dosePerFullLoad(dose, c.dose_type, c.capacity, water);
            want.dose_per_load = o.dose_per_load === null ? null : Number(o.dose_per_load);
            got.partial_product = calc.dosePartialLoad(dose, c.dose_type, loads, water);
            want.partial_product = Number(o.partial_product);
        }
        try {
            assert.deepEqual(got, want);
        } catch (e) {
            bad.push(JSON.stringify({ case: c, got: got }));
        }
    }
    assert.equal(bad.length, 0, `${bad.length} de ${CASES.length} difieren. Primero: ${bad[0]}`);
});
