// Ejecutar con: npm run test:js
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const S = require('../treatment-form-state.js');
const { actions, derive, initialState, toFormValues } = S;

const GOLDEN = JSON.parse(fs.readFileSync(
    path.join(__dirname, '..', '..', '..', 'farm', 'tests', 'fixtures', 'treatment_calc_cases.json'), 'utf8'));

const opt = (dose, dose_type, label) => ({ dose, dose_type, label });
const DATA = {
    today: '2026-10-27',
    fields: [
        { id: 1, name: 'Olivar Norte', crop: 'Olivo', area: 4.2, last_treatment_date: '2026-10-15' },
        { id: 2, name: 'La Vega', crop: 'Almendro', area: 2.8, last_treatment_date: null },
        { id: 3, name: 'Cerro Alto', crop: 'Olivo', area: 6.5, last_treatment_date: null },
        { id: 4, name: 'Huerta', crop: 'Pistacho', area: 1.1, last_treatment_date: null },
    ],
    machines: [
        { id: 1, name: 'Atomizador', capacity: 2000 },
        { id: 2, name: 'Cuba pequeña', capacity: 600 },
    ],
    products: [
        { id: 1, name: 'Oxicloruro de cobre 50%', type_name: 'Fungicida', spraying: opt(3, 'kg_per_1000l', 'kg/1000L'), fertigation: null, price: 9.5, recent: true },
        { id: 2, name: 'Mojante no iónico', type_name: 'Coadyuvante', spraying: opt(0.5, 'l_per_1000l', 'L/1000L'), fertigation: null, price: 6, recent: true },
        { id: 3, name: 'Deltametrina 2,5%', type_name: 'Insecticida', spraying: opt(0.5, 'l_per_1000l', 'L/1000L'), fertigation: null, price: 22, recent: false },
        { id: 4, name: 'Abono NPK 20-20-20', type_name: 'Nutrición', spraying: opt(3, 'kg_per_ha', 'kg/ha'), fertigation: opt(25, 'kg_per_ha', 'kg/ha'), price: 1.8, recent: true },
        { id: 5, name: 'Ácidos húmicos', type_name: 'Bioestimulante', spraying: opt(2, 'l_per_1000l', 'L/1000L'), fertigation: opt(10, 'l_per_ha', 'L/ha'), price: 4, recent: false },
        { id: 6, name: 'Nitrato potásico', type_name: 'Nutrición', spraying: null, fertigation: opt(40, 'kg_per_ha', 'kg/ha'), price: 1.2, recent: false },
        { id: 7, name: 'Aceite parafínico', type_name: 'Insecticida', spraying: opt(1, 'pct', '%'), fertigation: null, price: 3.5, recent: false },
        { id: 8, name: 'Producto sin precio', type_name: 'Otros', spraying: opt(1, 'kg_per_ha', 'kg/ha'), fertigation: null, price: 0, recent: false },
    ],
};
const ONE_MACHINE = Object.assign({}, DATA, { machines: [DATA.machines[0]] });
const NO_MACHINE = Object.assign({}, DATA, { machines: [] });

/** Aplica una secuencia de acciones [[nombre, payload], ...] sobre un estado. */
function run(state, steps, data = DATA) {
    return steps.reduce((s, [name, payload]) => actions[name](s, payload || {}, data), state);
}
const fresh = (initial, data = DATA) => initialState(data, initial);
const lineOf = (d, productId) => d.lines.find((l) => l.productId === productId);
const near = (a, b, eps = 1e-4) => assert.ok(a !== null && Math.abs(a - b) <= eps, `${a} != ${b}`);

/** Estado típico: una parcela, atomizador, mojado 1000, cobre + mojante. */
function base(extra = {}) {
    return run(fresh(Object.assign({ machineId: 1, water: '1000' }, extra)), [
        ['toggleField', { id: 1 }], ['addProduct', { productId: 1 }], ['addProduct', { productId: 2 }],
        ['setName', { name: 'Cobre + Mojante' }],
    ]);
}

// ── Regla 1: cambiar el tipo ──────────────────────────────────────────────────

test('R1 cambiar de tipo: dosis recomendadas, sin totales a mano, máquina y mojado fuera en fertirrigación', () => {
    let s = run(fresh({ machineId: 1, water: '1000' }), [
        ['toggleField', { id: 1 }], ['addProduct', { productId: 4 }], ['addProduct', { productId: 5 }],
    ]);
    s = run(s, [['setDose', { key: 1, dose: '4' }], ['setTotal', { key: 1, total: '10' }]]);
    assert.equal(s.lines[0].override, true);

    s = run(s, [['setType', { type: 'fertigation' }]]);
    assert.equal(s.type, 'fertigation');
    assert.equal(s.lines[0].dose, '25');            // NPK en fertirrigación
    assert.equal(s.lines[1].dose, '10');            // húmicos
    assert.ok(s.lines.every((l) => !l.override && l.total === ''));
    assert.equal(s.machineId, null);
    assert.equal(s.water, '');
    const d = derive(s, DATA);
    assert.equal(d.machine, null);
    assert.equal(d.water, 0);
    assert.equal(toFormValues(s, DATA).water_per_ha, '0');
    assert.equal(toFormValues(s, DATA).machine, '');
});

test('R1 productos sin dosis para el nuevo tipo: no válidos y bloquean el guardado', () => {
    let s = base();                                  // cobre + mojante (solo pulverización)
    s = run(s, [['setType', { type: 'fertigation' }]]);
    const d = derive(s, DATA);
    assert.equal(d.lines[0].supported, false);
    assert.match(d.lines[0].unsupportedMessage, /fertirrigación/);
    assert.equal(d.canSave, false);
    assert.ok(d.missing.some((m) => m.key === 'unsupported'));
    assert.equal(d.name, 'Cobre + Mojante');          // el nombre escrito a mano no cambia con el tipo

    // al volver a pulverización dejan de estar marcados
    s = run(s, [['setType', { type: 'spraying' }]]);
    assert.equal(derive(s, DATA).lines[0].supported, true);
});

test('R1 las líneas no válidas conservan su dosis al cambiar de tipo', () => {
    const s = run(base(), [['setDose', { key: 1, dose: '4' }], ['setType', { type: 'fertigation' }]]);
    assert.equal(s.lines[0].dose, '4');
});

// ── Regla 2: cambiar la dosis ─────────────────────────────────────────────────

test('R2 cambiar la dosis quita el total a mano de esa línea', () => {
    let s = run(base(), [['setTotal', { key: 1, total: '10' }], ['setTotal', { key: 2, total: '3' }]]);
    s = run(s, [['setDose', { key: 1, dose: '2' }]]);
    assert.equal(s.lines[0].override, false);
    assert.equal(s.lines[0].total, '');
    assert.equal(s.lines[1].override, true);          // la otra línea no se toca
    near(derive(s, DATA).lines[0].total, 2 * 4.2 * 1000 / 1000);
});

// ── Regla 3: cambiar el total ─────────────────────────────────────────────────

test('R3 total a mano: marca override y deriva la dosis', () => {
    let s = run(fresh({ machineId: 1, water: '1000' }), [['toggleField', { id: 1 }], ['addProduct', { productId: 4 }]]);
    s = run(s, [['setTotal', { key: 1, total: '10' }]]);
    const l = derive(s, DATA).lines[0];
    assert.equal(l.override, true);
    assert.equal(l.total, 10);
    near(l.dose, 2.381);
    near(l.cost, 18);                                 // 10 kg × 1,8 €
    const v = toFormValues(s, DATA).lines[0];
    assert.deepEqual([v.total_overridden, v.total_dose, v.dose], ['true', '10.0000', '2.3810']);
});

test('R3 con total a mano, cambiar mojado, área parcial o máquina mantiene el total y rederiva la dosis', () => {
    // L/1000L: la dosis depende del mojado
    let s = run(fresh({ machineId: 1, water: '1000' }), [['toggleField', { id: 1 }], ['addProduct', { productId: 2 }]]);
    s = run(s, [['setTotal', { key: 1, total: '5' }]]);
    near(derive(s, DATA).lines[0].dose, 1.1905);

    s = run(s, [['setWater', { water: '800' }]]);
    let l = derive(s, DATA).lines[0];
    assert.equal(l.total, 5);
    near(l.dose, 5 * 1000 / (4.2 * 800));

    s = run(s, [['setPartial', { partial: true }], ['setAppliedArea', { area: '2' }]]);
    l = derive(s, DATA).lines[0];
    assert.equal(l.total, 5);
    near(l.dose, 5 * 1000 / (2 * 800));

    s = run(s, [['setMachine', { id: 2 }]]);
    assert.equal(derive(s, DATA).lines[0].total, 5);

    // y con el mojado real de «ya está hecho»
    s = run(s, [['setDone', { done: true }], ['setRealWater', { water: '1100' }]]);
    l = derive(s, DATA).lines[0];
    assert.equal(l.total, 5);
    near(l.dose, 5 * 1000 / (2 * 1100));
});

test('R3 «volver a calcularlo» deja la dosis derivada como dosis', () => {
    let s = run(fresh({ machineId: 1, water: '1000' }), [['toggleField', { id: 1 }], ['addProduct', { productId: 4 }]]);
    s = run(s, [['setTotal', { key: 1, total: '10' }], ['clearOverride', { key: 1 }]]);
    assert.equal(s.lines[0].override, false);
    assert.equal(s.lines[0].dose, '2,381');
});

test('R3 el total no se puede editar con más de una parcela', () => {
    let s = run(base(), [['toggleField', { id: 2 }]]);
    const before = s;
    s = run(s, [['setTotal', { key: 1, total: '10' }]]);
    assert.equal(s, before);
    assert.equal(derive(s, DATA).canEditTotals, false);
});

// ── Regla 4: cambiar de parcela / varias parcelas ─────────────────────────────

test('R4 cambiar de parcela quita los totales a mano', () => {
    let s = run(base(), [['setTotal', { key: 1, total: '10' }]]);
    assert.equal(s.lines[0].override, true);
    s = run(s, [['setFields', { ids: [3] }]]);
    assert.equal(s.lines[0].override, false);
    assert.equal(s.lines[0].total, '');
});

test('R4 volver a elegir la misma parcela no borra nada', () => {
    const s = run(base(), [['setTotal', { key: 1, total: '10' }]]);
    assert.equal(actions.setFields(s, { ids: [1] }, DATA), s);
});

test('R4 con más de una parcela desaparece el tratamiento parcial y los totales', () => {
    let s = run(base(), [['setPartial', { partial: true }], ['setAppliedArea', { area: '2' }], ['setZone', { zone: 'norte' }], ['setTotal', { key: 1, total: '10' }]]);
    s = run(s, [['toggleField', { id: 2 }]]);
    assert.equal(s.partial, false);
    assert.equal(s.appliedArea, '');
    assert.equal(s.zone, '');
    assert.ok(s.lines.every((l) => !l.override));
    const d = derive(s, DATA);
    assert.equal(d.multi, true);
    assert.equal(d.partialActive, false);
    near(d.totalArea, 7);
    // no se puede reactivar con varias parcelas
    assert.equal(run(s, [['setPartial', { partial: true }]]).partial, false);
});

test('R4 varias parcelas: totales y costes por parcela, sumados', () => {
    const s = run(fresh({ machineId: 1, water: '1000' }), [
        ['toggleField', { id: 1 }], ['toggleField', { id: 2 }], ['toggleField', { id: 3 }], ['addProduct', { productId: 4 }],
    ]);
    const l = derive(s, DATA).lines[0];
    near(l.total, 3 * (4.2 + 2.8 + 6.5));             // NPK 3 kg/ha
    assert.deepEqual(l.perField.map((x) => x.fieldId), [1, 2, 3]);
    near(l.cost, 3 * 4.2 * 1.8 + 3 * 2.8 * 1.8 + 3 * 6.5 * 1.8, 1e-2);
    const v = toFormValues(s, DATA);
    assert.equal(v.field, '1');
    assert.deepEqual(v.extra_fields, ['2', '3']);
    assert.equal(v.lines[0].total_dose, '');          // con varias parcelas no se envía total
});

test('R4 en edición elegir parcela sustituye (no acumula) y no hay extra_fields', () => {
    const s = run(fresh({ isEdit: true, fieldIds: [1], type: 'spraying', machineId: 1, water: '1000', name: 'X',
        lines: [{ productId: 1, dose: '3' }] }), [['toggleField', { id: 3 }]]);
    assert.deepEqual(s.fieldIds, [3]);
    assert.deepEqual(toFormValues(s, DATA).extra_fields, []);
});

// ── Regla 5: añadir / quitar producto ─────────────────────────────────────────

test('R5 añadir: dosis recomendada del tipo actual, sin duplicados ni productos no válidos', () => {
    let s = run(fresh({ machineId: 1, water: '1000' }), [['addProduct', { productId: 4 }]]);
    assert.equal(s.lines[0].dose, '3');
    assert.equal(run(s, [['addProduct', { productId: 4 }]]).lines.length, 1);
    assert.equal(run(s, [['addProduct', { productId: 6 }]]).lines.length, 1);       // nitrato K no tiene dosis de pulverización
    s = run(s, [['setType', { type: 'fertigation' }], ['addProduct', { productId: 6 }]]);
    assert.equal(s.lines[1].dose, '40');
    assert.equal(run(s, [['addProduct', { productId: 999 }]]).lines.length, 2);     // desconocido
});

test('R5 quitar renumera las posiciones', () => {
    let s = run(fresh({ machineId: 1, water: '1000' }), [
        ['addProduct', { productId: 1 }], ['addProduct', { productId: 2 }], ['addProduct', { productId: 3 }],
    ]);
    s = run(s, [['removeProduct', { key: s.lines[0].key }]]);
    const d = derive(s, DATA);
    assert.deepEqual(d.lines.map((l) => [l.productId, l.position, l.number]), [[2, 0, 1], [3, 1, 2]]);
    assert.deepEqual(toFormValues(s, DATA).lines.map((l) => [l.product, l.position]), [[2, 0], [3, 1]]);
});

// ── Regla 6: editar ───────────────────────────────────────────────────────────

test('R6 editar: dosis guardada (no la recomendada), total a mano y precio congelado; el nombre guardado se conserva', () => {
    const s = fresh({
        isEdit: true, type: 'spraying', fieldIds: [1], machineId: 1, water: '1000', date: '2026-10-20', name: 'Mi nombre',
        lines: [
            { productId: 1, dose: '2,5', unitPrice: 8 },                       // precio congelado 8 (ahora vale 9,5)
            { productId: 4, dose: '2,381', override: true, total: '10', unitPrice: 1.5 },
            { productId: 2, dose: '0,5', unitPrice: 0 },                       // se guardó sin precio: usa el del producto
        ],
    });
    assert.equal(s.mode, 'edit');
    const d = derive(s, DATA);
    assert.equal(d.name, 'Mi nombre');
    assert.equal(lineOf(d, 1).dose, 2.5);                                      // no la recomendada (3)
    assert.equal(lineOf(d, 1).warn, false);                                    // 2,5 vs 3: 16,7 %
    near(lineOf(d, 1).cost, 2.5 * 4.2 * 8, 1e-2);                              // con 8, no con 9,5
    assert.equal(lineOf(d, 4).override, true);
    near(lineOf(d, 4).cost, 15);                                               // 10 kg × 1,5 (congelado), no × 1,8
    near(lineOf(d, 2).cost, 0.5 * 4.2 * 6, 1e-2);                              // precio 0 → el del producto (6)
    assert.equal(d.isEdit, true);
    // y lo que se enviaría mantiene el total a mano
    const v = toFormValues(s, DATA).lines;
    assert.deepEqual(v.map((l) => l.total_overridden), ['false', 'true', 'false']);
});

test('R6 editar un hecho: hecho, fecha y mojado real cargados', () => {
    const s = fresh({
        isEdit: true, type: 'spraying', fieldIds: [1], machineId: 1, water: '1000', date: '2026-10-24',
        finishDate: '2026-10-26', realWater: '1100', name: 'Cobre', lines: [{ productId: 1, dose: '3', unitPrice: 9.5 }],
    });
    const d = derive(s, DATA);
    assert.equal(s.done, true);
    assert.equal(d.status, 'completed');
    assert.equal(d.water, 1100);
    near(d.lines[0].total, 3 * 4.2 * 1100 / 1000);
});

// ── Regla 7: «Ya está hecho» ──────────────────────────────────────────────────

test('R7 el mojado real sustituye al previsto en los cálculos', () => {
    let s = run(base(), [['setDose', { key: 1, dose: '3' }]]);
    near(derive(s, DATA).lines[0].total, 12.6);
    s = run(s, [['setDone', { done: true }], ['setRealWater', { water: '1100' }]]);
    let d = derive(s, DATA);
    assert.equal(d.water, 1100);
    assert.equal(d.usesRealWater, true);
    near(d.lines[0].total, 13.86);
    assert.equal(d.status, 'completed');
    assert.equal(toFormValues(s, DATA).real_water_per_ha, '1100');
    assert.equal(toFormValues(s, DATA).water_per_ha, '1000');

    // sin mojado real se usa el previsto
    s = run(s, [['setRealWater', { water: '' }]]);
    d = derive(s, DATA);
    assert.equal(d.water, 1000);
    assert.equal(toFormValues(s, DATA).real_water_per_ha, '');
});

test('R7 al desactivarlo se borran la fecha de realización y el mojado real', () => {
    let s = run(base(), [['setDone', { done: true }]]);
    assert.equal(s.finishDate, DATA.today);          // por defecto, hoy
    s = run(s, [['setFinishDate', { date: '2026-10-20' }], ['setRealWater', { water: '1100' }], ['setDone', { done: false }]]);
    assert.equal(s.finishDate, '');
    assert.equal(s.realWater, '');
    const v = toFormValues(s, DATA);
    assert.equal(v.finish_date, '');
    assert.equal(v.real_water_per_ha, '');
});

test('R7 la fecha de realización no puede ser futura', () => {
    let s = run(base(), [['setDone', { done: true }], ['setFinishDate', { date: '2026-10-28' }]]);
    const d = derive(s, DATA);
    assert.equal(d.finishFuture, true);
    assert.equal(d.canSave, false);
    assert.ok(d.errors.date.some((m) => /futura/.test(m)));
    s = run(s, [['setFinishDate', { date: DATA.today }]]);
    assert.equal(derive(s, DATA).finishFuture, false);
});

test('R7 hecho sin fecha de realización falta; mojado real 0 es un error', () => {
    let s = run(base(), [['setDone', { done: true }], ['setFinishDate', { date: '' }]]);
    assert.ok(derive(s, DATA).missing.some((m) => m.key === 'finishDate'));
    s = run(s, [['setFinishDate', { date: DATA.today }], ['setRealWater', { water: '0' }]]);
    assert.ok(derive(s, DATA).missing.some((m) => m.key === 'realWater'));
});

test('R7 estado: pendiente, atrasado o completado', () => {
    assert.equal(derive(run(base(), [['setDate', { date: '2026-10-27' }]]), DATA).status, 'pending');
    assert.equal(derive(run(base(), [['setDate', { date: '2026-10-26' }]]), DATA).status, 'delayed');
    assert.equal(derive(run(base(), [['setDate', { date: '2026-10-26' }], ['setDone', { done: true }]]), DATA).status, 'completed');
});

// ── Regla 8: pulverización sin mojado ─────────────────────────────────────────

test('R8 sin mojado: /1000L y % sin total ni coste («Falta el mojado»); /ha sí se calculan', () => {
    const s = run(fresh({ machineId: 1 }), [
        ['toggleField', { id: 1 }], ['addProduct', { productId: 1 }], ['addProduct', { productId: 7 }], ['addProduct', { productId: 4 }],
    ]);
    const d = derive(s, DATA);
    assert.equal(lineOf(d, 1).total, null);
    assert.equal(lineOf(d, 1).costState, 'missing-water');
    assert.equal(lineOf(d, 1).cost, null);
    assert.equal(lineOf(d, 7).total, null);
    assert.equal(lineOf(d, 7).costState, 'missing-water');
    near(lineOf(d, 4).total, 12.6);
    assert.equal(lineOf(d, 4).costState, 'ok');
    assert.equal(d.summary.totalCost, null);
    assert.equal(d.summary.ready, false);
    assert.ok(d.missing.some((m) => m.key === 'water'));
});

test('R8 productos en % (E3): total y coste con mojado', () => {
    const s = run(fresh({ machineId: 1, water: '1000' }), [['toggleField', { id: 1 }], ['addProduct', { productId: 7 }]]);
    const l = derive(s, DATA).lines[0];
    near(l.total, 42);                                // 1 % de 4200 L
    near(l.cost, 42 * 3.5, 1e-2);
    near(l.perLoad, 20);
});

test('R8 sin precio: coste 0 y estado «no-price»', () => {
    const s = run(fresh({ machineId: 1, water: '1000' }), [['toggleField', { id: 1 }], ['addProduct', { productId: 8 }]]);
    const l = derive(s, DATA).lines[0];
    assert.equal(l.costState, 'no-price');
    assert.equal(l.cost, 0);
});

// ── Regla 9: máquinas ─────────────────────────────────────────────────────────

test('R9 con una sola máquina queda seleccionada y no hay chips', () => {
    const s = run(fresh({ water: '1000' }, ONE_MACHINE), [['toggleField', { id: 1 }], ['addProduct', { productId: 1 }]], ONE_MACHINE);
    const d = derive(s, ONE_MACHINE);
    assert.equal(d.machineMode, 'single');
    assert.equal(d.machine.id, 1);
    assert.equal(toFormValues(s, ONE_MACHINE).machine, '1');
    assert.equal(d.missing.some((m) => m.key === 'machine'), false);
});

test('R9 con varias máquinas hay que elegir; con ninguna, aviso y bloqueo en pulverización', () => {
    let s = run(fresh({ water: '1000' }), [['toggleField', { id: 1 }], ['addProduct', { productId: 1 }]]);
    let d = derive(s, DATA);
    assert.equal(d.machineMode, 'multi');
    assert.equal(d.machine, null);
    assert.ok(d.missing.some((m) => m.key === 'machine'));
    s = run(s, [['setMachine', { id: 2 }]]);
    assert.equal(derive(s, DATA).machine.id, 2);

    s = run(fresh({ water: '1000' }, NO_MACHINE), [['toggleField', { id: 1 }], ['addProduct', { productId: 1 }]], NO_MACHINE);
    d = derive(s, NO_MACHINE);
    assert.equal(d.machineMode, 'none');
    assert.equal(d.canSave, false);
    assert.match(d.errors.application[0], /ninguna máquina/);
    // en fertirrigación no hace falta máquina
    s = run(fresh({ type: 'fertigation' }, NO_MACHINE), [['toggleField', { id: 1 }], ['addProduct', { productId: 6 }], ['setName', { name: 'Abonado' }]], NO_MACHINE);
    d = derive(s, NO_MACHINE);
    assert.equal(d.machineMode, 'none');
    assert.equal(d.canSave, true);
});

test('cubas: llenas + parcial por parcela y por cuba llena', () => {
    const s = run(base(), [['setDose', { key: 1, dose: '3' }]]);
    const d = derive(s, DATA);
    assert.equal(d.loads.length, 1);
    assert.deepEqual([d.loads[0].totalWater, d.loads[0].fullLoads, d.loads[0].partialWater, d.loads[0].partialLoad], [4200, 2, 200, true]);
    near(d.lines[0].perLoad, 6);                      // 3 kg/1000L × 2000 L
    near(d.lines[0].partialProduct, 0.6);
    assert.equal(d.loadsTotalWater, 4200);
});

// ── Regla 10: el nombre se escribe a mano (D2 anulada por Carlos, 27/10) ─────

test('R10 el nombre no se rellena solo: vacío al crear y obligatorio', () => {
    const s = run(fresh({ machineId: 1, water: '1000' }), [['addProduct', { productId: 1 }], ['addProduct', { productId: 2 }]]);
    const d = derive(s, DATA);
    assert.equal(d.name, '');
    assert.equal(d.canSave, false);
    assert.deepEqual(d.errors.name, ['Pon un nombre al tratamiento.']);
    assert.match(d.missingText, /nombre/);
    assert.equal('autoName' in d || 'nameHint' in d, false);
});

test('R10 con nombre escrito a mano se puede guardar y añadir productos no lo toca', () => {
    let s = run(fresh({ machineId: 1, water: '1000' }), [['addProduct', { productId: 1 }], ['setName', { name: 'Mi cobre' }]]);
    s = run(s, [['addProduct', { productId: 2 }]]);
    const d = derive(s, DATA);
    assert.equal(d.name, 'Mi cobre');
    assert.deepEqual(d.errors.name, []);
    assert.equal(toFormValues(s, DATA).name, 'Mi cobre');
});

test('R10 un nombre de solo espacios cuenta como vacío', () => {
    const s = run(fresh({ machineId: 1, water: '1000' }), [['addProduct', { productId: 1 }], ['setName', { name: '   ' }]]);
    assert.deepEqual(derive(s, DATA).errors.name, ['Pon un nombre al tratamiento.']);
});

// ── Regla 11: área parcial ────────────────────────────────────────────────────

test('R11 área parcial: entre 0 y el área de la parcela; si no, error en la sección', () => {
    const s = run(base(), [['setPartial', { partial: true }]]);
    assert.equal(derive(s, DATA).areaError, null);                         // vacío = parcela entera
    for (const bad of ['0', '-1', '4,3', 'abc', '1.000']) {
        const d = derive(run(s, [['setAppliedArea', { area: bad }]]), DATA);
        assert.match(d.areaError, /entre 0 y 4,2 ha/, bad);
        assert.ok(d.errors.field.length >= 1, bad);
        assert.ok(d.missing.some((m) => m.key === 'area'), bad);
        near(d.totalArea, 4.2);                                            // un área inválida no se usa
    }
    const ok = derive(run(s, [['setAppliedArea', { area: '2,5' }]]), DATA);
    assert.equal(ok.areaError, null);
    near(ok.totalArea, 2.5);
    near(ok.lines[0].total, 7.5);                                           // 3 kg/1000L × 2500 L
    assert.equal(run(s, [['setPartial', { partial: false }]]).appliedArea, '');
});

test('R11 valores del formulario con tratamiento parcial', () => {
    const s = run(base(), [['setPartial', { partial: true }], ['setAppliedArea', { area: '2,5' }], ['setZone', { zone: ' sector norte ' }]]);
    const v = toFormValues(s, DATA);
    assert.equal(v.applied_area, '2.5');
    assert.equal(v.zone_notes, 'sector norte');
    const whole = toFormValues(run(s, [['setPartial', { partial: false }]]), DATA);
    assert.equal(whole.applied_area, '');
    assert.equal(whole.zone_notes, '');
});

// ── Regla 12: errores y «Falta» desde derive() ────────────────────────────────

test('R12 formulario vacío: lista «Falta» en orden y errores por sección', () => {
    const d = derive(fresh({}), DATA);
    assert.equal(d.canSave, false);
    assert.deepEqual(d.missing.map((m) => m.key), ['field', 'products', 'machine', 'water', 'name']);
    assert.equal(d.missingText, 'Falta: parcela, un producto, máquina, mojado, nombre');
    assert.deepEqual(Object.keys(d.errors), ['field', 'products', 'application', 'date', 'name']);
    assert.equal(d.errors.field[0], 'Elige al menos una parcela.');
    assert.equal(d.errors.name[0], 'Pon un nombre al tratamiento.');
    assert.equal(derive(base({ machineId: null }), DATA).missingText, 'Falta: máquina');
    assert.equal(derive(base(), DATA).missingText, '');
});

test('R12 formulario completo: se puede guardar, sin «Falta»', () => {
    const s = run(base(), [['setMachine', { id: 1 }]]);
    const d = derive(s, DATA);
    assert.equal(d.canSave, true);
    assert.equal(d.missingText, '');
    assert.equal(d.summary.ready, true);
    // cobre 3 kg/1000L × 9,5 + mojante 0,5 L/1000L × 6 sobre 4200 L de caldo
    near(d.summary.totalCost, 12.6 * 9.5 + 2.1 * 6, 1e-2);
    near(d.summary.costPerHa, (12.6 * 9.5 + 2.1 * 6) / 4.2, 1e-2);
    assert.equal(d.name, 'Cobre + Mojante');
});

test('R12 dosis vacía o 0 bloquea; markTried no cambia los cálculos', () => {
    let s = run(base(), [['setMachine', { id: 1 }], ['setDose', { key: 1, dose: '' }]]);
    assert.ok(derive(s, DATA).missing.some((m) => m.key === 'dose'));
    s = run(s, [['setDose', { key: 1, dose: '0' }]]);
    assert.ok(derive(s, DATA).missing.some((m) => m.key === 'dose'));
    const tried = actions.markTried(s);
    assert.equal(tried.tried, true);
    assert.deepEqual(derive(tried, DATA).missing, derive(s, DATA).missing);
});

test('la dosis tecleada se redondea hacia arriba a 3 decimales, como el backend', () => {
    const s = run(base(), [['setMachine', { id: 1 }], ['setDose', { key: 2, dose: '0,0754' }]]);
    const l = derive(s, DATA).lines[1];
    assert.equal(l.dose, 0.076);
    assert.equal(l.doseRoundedUp, true);
    assert.equal(toFormValues(s, DATA).lines[1].dose, '0.076');
    near(l.total, 0.076 * 4.2);
});

test('aviso de dosis lejos de la recomendada (25 %)', () => {
    const s = run(base(), [['setDose', { key: 1, dose: '2' }]]);   // 2 vs 3: -33 %
    assert.equal(derive(s, DATA).lines[0].warn, true);
    assert.equal(derive(run(s, [['setDose', { key: 1, dose: '2,5' }]]), DATA).lines[0].warn, false);
});

test('reduce despacha por nombre y rechaza acciones desconocidas', () => {
    const s = S.reduce(fresh({}), { type: 'setWater', water: '900' }, DATA);
    assert.equal(s.water, '900');
    assert.throws(() => S.reduce(s, { type: 'nope' }, DATA), /desconocida/);
});

test('las acciones no mutan el estado anterior', () => {
    const s = base();
    const copy = JSON.parse(JSON.stringify(s));
    run(s, [['setDose', { key: 1, dose: '9' }], ['setType', { type: 'fertigation' }], ['toggleField', { id: 2 }], ['removeProduct', { key: 1 }]]);
    assert.deepEqual(s, copy);
});

// ── Valores del formulario ────────────────────────────────────────────────────

test('toFormValues de una pulverización completa', () => {
    const s = run(base(), [['setMachine', { id: 1 }], ['setDate', { date: '2026-10-29' }]]);
    assert.deepEqual(toFormValues(s, DATA), {
        name: 'Cobre + Mojante',
        type: 'spraying', date: '2026-10-29', field: '1', extra_fields: [], machine: '1', water_per_ha: '1000',
        finish_date: '', real_water_per_ha: '', applied_area: '', zone_notes: '',
        lines: [
            { product: 1, dose: '3.000', total_dose: '12.6000', total_overridden: 'false', position: 0 },
            { product: 2, dose: '0.500', total_dose: '2.1000', total_overridden: 'false', position: 1 },
        ],
    });
});

// ── Los mismos casos que el backend, pasando por el estado del formulario ─────

for (const c of GOLDEN.cases) {
    test(`golden ${c.id} a través del estado: ${c.title}`, () => {
        const i = c.input;
        const spray = i.type === 'spraying';
        const opt1 = { dose: Number(i.dose), dose_type: i.dose_type, label: i.dose_type };
        const data = {
            today: '2026-10-27',
            fields: [{ id: 1, name: 'F', crop: 'Olivo', area: i.field_area, last_treatment_date: null }],
            machines: i.capacity ? [{ id: 1, name: 'M', capacity: i.capacity }] : [],
            products: [{ id: 1, name: 'P', type_name: 'T', spraying: spray ? opt1 : null, fertigation: spray ? null : opt1, price: Number(i.price), recent: false }],
        };
        let s = initialState(data, { type: i.type, water: spray ? String(i.water_per_ha) : '' });
        const steps = [['toggleField', { id: 1 }], ['addProduct', { productId: 1 }]];
        if (i.applied_area) steps.push(['setPartial', { partial: true }], ['setAppliedArea', { area: String(i.applied_area) }]);
        if (i.finish_date) steps.push(['setDone', { done: true }]);
        if (i.real_water_per_ha) steps.push(['setRealWater', { water: String(i.real_water_per_ha) }]);
        s = run(s, steps, data);
        if (i.total_override) s = run(s, [['setTotal', { key: 1, total: i.total_override }]], data);
        else s = run(s, [['setDose', { key: 1, dose: i.dose }]], data);

        const d = derive(s, data);
        const l = d.lines[0];
        const e = c.expected;
        near(l.total, e.total_dose);
        near(l.dose, e.dose);
        assert.equal(l.totalUnit, e.total_dose_unit);
        near(l.cost, e.total_price, 1e-2);
        near(d.summary.costPerHa, e.price_per_ha, 1e-2);
        if (spray) {
            if (e.dose_per_load === null) assert.equal(l.perLoad, null);
            else near(l.perLoad, e.dose_per_load);
        }
        if (e.loads === null) assert.equal(d.loads.length, 0);
        else {
            assert.deepEqual(
                [d.loads[0].totalWater, d.loads[0].fullLoads, d.loads[0].partialWater, d.loads[0].partialLoad],
                [e.loads.total_water, e.loads.full_loads, e.loads.partial_water, e.loads.partial_load]);
            near(l.partialProduct, e.partial_product);
        }
    });
}
