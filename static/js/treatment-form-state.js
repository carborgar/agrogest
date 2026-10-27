/**
 * Estado del formulario de tratamiento (sin DOM).
 *
 *  - Un estado plano (JSON) con lo que ha tecleado/elegido el usuario.
 *  - Acciones puras  (state, payload, data) → state.
 *  - derive(state, data) → TODO lo que se pinta: líneas con total, coste, por cuba y aviso;
 *    cubas; resumen; lista «Falta: …»; errores por sección.
 *    (Es el equivalente de renderVals() del prototipo.)
 *  - toFormValues(state, data) → valores normalizados (punto decimal) para los inputs reales
 *    del formulario Django.
 *
 * `data` es el JSON del servidor (build_treatment_form_data): {today, fields, machines, products, lines?}.
 * Los cálculos se delegan en treatment-calc.js, que replica el backend.
 *
 * Se expone en window.TreatmentFormState y en module.exports (para probarlo con Node).
 */
(function (root, factory) {
    'use strict';
    const calc = (typeof module === 'object' && module.exports) ? require('./treatment-calc.js') : root.TreatmentCalc;
    const api = factory(calc);
    if (typeof module === 'object' && module.exports) {
        module.exports = api;
    } else {
        root.TreatmentFormState = api;
    }
})(typeof window !== 'undefined' ? window : globalThis, function (calc) {
    'use strict';

    // ── Utilidades ────────────────────────────────────────────────────────────

    const fmt = (n, d) => n.toLocaleString('es-ES', {
        minimumFractionDigits: 0, maximumFractionDigits: d === undefined ? 2 : d,
    });

    const byId = (list) => {
        const map = {};
        (list || []).forEach((item) => { map[item.id] = item; });
        return map;
    };

    const doseOption = (product, type) => (type === 'spraying' ? product.spraying : product.fertigation) || null;

    /** Dosis → texto para el input (sin ceros finales, máx. 3 decimales, coma decimal como en España). */
    function doseToText(value) {
        if (value === null || value === undefined || !Number.isFinite(value)) return '';
        return fmt(value, 3).replace(/\./g, '');
    }

    function plain(lines, patchByKey) {
        return lines.map((l) => (patchByKey[l.key] ? Object.assign({}, l, patchByKey[l.key]) : l));
    }

    function withoutOverrides(lines) {
        return lines.map((l) => (l.override ? Object.assign({}, l, { override: false, total: '' }) : l));
    }

    // ── Estado inicial ────────────────────────────────────────────────────────

    /**
     * initial (todo opcional): {isEdit, type, fieldIds, machineId, water, date, finishDate, realWater,
     *   appliedArea, zone, name, lines: [{productId, dose, total, override, unitPrice}]}.
     * Los textos numéricos van tal cual los tendría el usuario (coma o punto).
     */
    function initialState(data, initial) {
        initial = initial || {};
        const isEdit = !!initial.isEdit;
        const type = initial.type === 'fertigation' ? 'fertigation' : 'spraying';
        const isSpray = type === 'spraying';
        const lines = (initial.lines || []).map((l, i) => ({
            key: i + 1,
            productId: Number(l.productId),
            dose: l.dose === undefined || l.dose === null ? '' : String(l.dose),
            override: !!l.override,
            total: l.total === undefined || l.total === null ? '' : String(l.total),
            unitPrice: l.unitPrice === undefined ? null : l.unitPrice,
        }));
        const fieldIds = (initial.fieldIds || []).map(Number);
        const state = {
            mode: isEdit ? 'edit' : 'create',
            type: type,
            fieldIds: fieldIds,
            partial: !!(initial.appliedArea || initial.zone),
            appliedArea: initial.appliedArea ? String(initial.appliedArea) : '',
            zone: initial.zone || '',
            lines: lines.map((l) => (l.override && fieldIds.length !== 1 ? Object.assign({}, l, { override: false, total: '' }) : l)),
            nextKey: lines.length + 1,
            machineId: isSpray && initial.machineId ? Number(initial.machineId) : null,
            water: isSpray && initial.water ? String(initial.water) : '',
            date: initial.date || data.today,
            done: !!initial.finishDate,
            finishDate: initial.finishDate || '',
            realWater: isSpray && initial.finishDate && initial.realWater ? String(initial.realWater) : '',
            name: initial.name || '',
            tried: false,
        };
        return state;
    }

    // ── Acciones (puras) ──────────────────────────────────────────────────────

    const actions = {
        /** Regla 1: cambiar el tipo. */
        setType(state, payload, data) {
            const type = payload.type === 'fertigation' ? 'fertigation' : 'spraying';
            if (type === state.type) return state;
            const products = byId(data.products);
            const lines = state.lines.map((l) => {
                const p = products[l.productId];
                const opt = p ? doseOption(p, type) : null;
                return Object.assign({}, l, { dose: opt ? doseToText(opt.dose) : l.dose, override: false, total: '' });
            });
            const next = Object.assign({}, state, { type: type, lines: lines });
            if (type === 'fertigation') {
                // En fertirrigación no hay máquina ni mojado (el backend guarda máquina = null y mojado = 0)
                Object.assign(next, { machineId: null, water: '', realWater: '' });
            }
            return next;
        },

        /** Regla 2: cambiar la dosis quita el total a mano de esa línea. */
        setDose(state, payload) {
            return Object.assign({}, state, {
                lines: plain(state.lines, { [payload.key]: { dose: String(payload.dose), override: false, total: '' } }),
            });
        },

        /** Regla 3: poner el total a mano (solo con una parcela). */
        setTotal(state, payload) {
            if (state.fieldIds.length !== 1) return state;
            return Object.assign({}, state, {
                lines: plain(state.lines, { [payload.key]: { total: String(payload.total), override: true } }),
            });
        },

        /** «Volver a calcularlo»: deja la dosis derivada del total como dosis y quita el total a mano. */
        clearOverride(state, payload, data) {
            const d = derive(state, data);
            const line = d.lines.find((l) => l.key === payload.key);
            if (!line || !state.lines.find((l) => l.key === payload.key).override) return state;
            const fallback = line.recommended;
            const dose = line.dose !== null && line.dose > 0 ? line.dose : fallback;
            return Object.assign({}, state, {
                lines: plain(state.lines, { [payload.key]: { override: false, total: '', dose: doseToText(dose) } }),
            });
        },

        /**
         * Regla 4: elegir parcelas. payload: {ids} (conjunto completo). Si cambia la selección se quitan
         * los totales a mano; con más de una parcela desaparece el tratamiento parcial.
         */
        setFields(state, payload) {
            const ids = payload.ids.map(Number);
            const sameSet = ids.length === state.fieldIds.length && ids.every((id, i) => id === state.fieldIds[i]);
            if (sameSet) return state;
            const next = Object.assign({}, state, { fieldIds: ids, lines: withoutOverrides(state.lines) });
            if (ids.length !== 1) Object.assign(next, { partial: false, appliedArea: '', zone: '' });
            return next;
        },

        /** Marca/desmarca una parcela: en alta se acumulan (la primera es la principal), en edición se sustituye. */
        toggleField(state, payload) {
            const id = Number(payload.id);
            if (state.mode === 'edit') return actions.setFields(state, { ids: [id] });
            const ids = state.fieldIds.indexOf(id) >= 0 ? state.fieldIds.filter((x) => x !== id) : state.fieldIds.concat([id]);
            return actions.setFields(state, { ids: ids });
        },

        /** Regla 5: añadir producto con la dosis recomendada del tipo actual; no se repite ni se añade si no es válido. */
        addProduct(state, payload, data) {
            const id = Number(payload.productId);
            if (state.lines.some((l) => l.productId === id)) return state;
            const p = byId(data.products)[id];
            const opt = p ? doseOption(p, state.type) : null;
            if (!opt) return state;
            const line = { key: state.nextKey, productId: id, dose: doseToText(opt.dose), override: false, total: '', unitPrice: null };
            return Object.assign({}, state, { lines: state.lines.concat([line]), nextKey: state.nextKey + 1 });
        },

        /** Regla 5: quitar (las posiciones se renumeran: son el índice de la línea). */
        removeProduct(state, payload) {
            return Object.assign({}, state, { lines: state.lines.filter((l) => l.key !== payload.key) });
        },

        setMachine(state, payload) {
            return Object.assign({}, state, { machineId: payload.id === null ? null : Number(payload.id) });
        },

        setWater(state, payload) {
            return Object.assign({}, state, { water: String(payload.water) });
        },

        setPartial(state, payload) {
            if (state.fieldIds.length !== 1) return state;
            return payload.partial
                ? Object.assign({}, state, { partial: true })
                : Object.assign({}, state, { partial: false, appliedArea: '', zone: '' });
        },

        setAppliedArea(state, payload) {
            return Object.assign({}, state, { appliedArea: String(payload.area) });
        },

        setZone(state, payload) {
            return Object.assign({}, state, { zone: String(payload.zone) });
        },

        setDate(state, payload) {
            return Object.assign({}, state, { date: String(payload.date) });
        },

        /** Regla 7: «Ya está hecho». Al activarlo la fecha de realización es hoy; al quitarlo se borran fecha y mojado real. */
        setDone(state, payload, data) {
            if (!!payload.done === state.done) return state;
            return payload.done
                ? Object.assign({}, state, { done: true, finishDate: state.finishDate || data.today })
                : Object.assign({}, state, { done: false, finishDate: '', realWater: '' });
        },

        setFinishDate(state, payload) {
            return Object.assign({}, state, { finishDate: String(payload.date) });
        },

        setRealWater(state, payload) {
            return Object.assign({}, state, { realWater: String(payload.water) });
        },

        /** Regla 10: el nombre se escribe a mano (Carlos anuló el nombre automático, 27/10). */
        setName(state, payload) {
            return Object.assign({}, state, { name: String(payload.name) });
        },

        /** Se intentó guardar: a partir de aquí se enseñan los errores de las secciones. */
        markTried(state) {
            return state.tried ? state : Object.assign({}, state, { tried: true });
        },
    };

    function reduce(state, action, data) {
        const fn = actions[action.type];
        if (!fn) throw new Error('Acción desconocida: ' + action.type);
        return fn(state, action, data);
    }

    // ── derive ────────────────────────────────────────────────────────────────

    function derive(state, data) {
        const isSpray = state.type === 'spraying';
        const isEdit = state.mode === 'edit';
        const fieldsById = byId(data.fields);
        const productsById = byId(data.products);

        // Parcelas y superficie (regla 11)
        const selected = state.fieldIds.map((id) => fieldsById[id]).filter(Boolean);
        const single = selected.length === 1;
        const multi = selected.length > 1;
        const partialActive = single && state.partial;
        const areaText = String(state.appliedArea || '').trim();
        let areaError = null;
        let appliedArea = null;
        if (partialActive && areaText) {
            const n = calc.parseNumber(areaText);
            if (n === null || n <= 0 || n > selected[0].area) {
                areaError = 'Tiene que estar entre 0 y ' + fmt(selected[0].area) + ' ha.';
            } else {
                appliedArea = n;
            }
        }
        const areas = selected.map((f) => calc.effectiveArea(f.area, appliedArea));
        const totalArea = areas.reduce((a, b) => a + b, 0);

        // Máquina (regla 9)
        const machines = data.machines || [];
        let machine = null;
        let machineMode = 'none';
        if (isSpray) {
            if (machines.length === 1) {
                machine = machines[0];
                machineMode = 'single';
            } else if (machines.length > 1) {
                machineMode = 'multi';
                machine = machines.find((m) => m.id === state.machineId) || null;
            }
        }

        // Mojado: el real sustituye al previsto cuando está hecho (regla 7, = actual_water_per_ha)
        const plannedWater = isSpray ? calc.parseNumber(state.water) : null;
        const realText = String(state.realWater || '').trim();
        const realWaterNum = isSpray && state.done && realText ? calc.parseNumber(realText) : null;
        const realWaterError = isSpray && state.done && realText !== '' && !(realWaterNum > 0);
        const waterEff = !isSpray ? 0 : (realWaterNum > 0 ? realWaterNum : (plannedWater > 0 ? plannedWater : 0));

        // Líneas de producto
        const lines = state.lines.map((l, index) => {
            const p = productsById[l.productId];
            const base = { key: l.key, productId: l.productId, position: index, number: index + 1, name: p ? p.name : '(producto no disponible)', typeName: p ? p.type_name : '' };
            const opt = p ? doseOption(p, state.type) : null;
            if (!opt) {
                return Object.assign(base, {
                    supported: false, valid: false, dose: null, total: null, cost: null, costState: 'unsupported',
                    unsupportedMessage: 'Este producto no tiene dosis para ' + (isSpray ? 'pulverización' : 'fertirrigación') + '. Quítalo o cambia el tipo.',
                });
            }
            const doseType = opt.dose_type;
            const override = !!l.override && single;
            let dose = null;
            let doseRoundedUp = false;
            let total = null;
            let perField = [];

            if (override) {
                total = calc.parseNumber(l.total);
                if (total !== null) total = calc.roundTo(total, 4);
                dose = total !== null ? calc.doseFromTotal(total, doseType, areas[0], waterEff) : null;
                if (total !== null) perField = [{ fieldId: selected[0].id, total: total }];
            } else {
                const typed = calc.parseNumber(l.dose);
                dose = typed !== null ? calc.roundDoseUp(typed) : null;
                doseRoundedUp = typed !== null && dose !== typed;
                if (dose !== null && dose > 0 && selected.length) {
                    perField = selected.map((f, i) => ({ fieldId: f.id, total: calc.totalFromDose(dose, doseType, areas[i], waterEff) }));
                    total = perField.every((x) => x.total !== null) ? perField.reduce((a, x) => a + x.total, 0) : null;
                    if (total !== null) total = calc.roundTo(total, 4);
                }
            }

            const valid = dose !== null && dose > 0;
            // Precio congelado de la línea guardada (E4); si era 0 el backend usa el del producto
            const unitPrice = l.unitPrice > 0 ? l.unitPrice : p.price;
            let cost = null;
            if (total !== null && perField.length && perField.every((x) => x.total !== null)) {
                cost = calc.roundTo(perField.reduce((a, x) => a + calc.lineCost(x.total, unitPrice), 0), 2);
            }
            let costState = 'ok';
            if (!selected.length) costState = 'pick-field';
            else if (total === null) costState = valid && !override ? 'missing-water' : 'invalid-dose';
            else if (!(unitPrice > 0)) costState = 'no-price';

            return Object.assign(base, {
                supported: true,
                doseType: doseType,
                unit: opt.label || calc.DOSE_UNITS[doseType] || '',
                totalUnit: calc.totalUnit(doseType),
                recommended: opt.dose,
                dose: dose,
                doseRoundedUp: doseRoundedUp,
                valid: valid,
                override: override,
                total: total,
                perField: perField,
                unitPrice: unitPrice,
                cost: cost,
                costState: costState,
                perLoad: isSpray && machine && waterEff > 0 && valid
                    ? calc.dosePerFullLoad(dose, doseType, machine.capacity, waterEff) : null,
                warn: valid && calc.isFarFromRecommended(dose, opt.dose),
            });
        });

        // Cubas (por parcela)
        const loads = [];
        if (isSpray && machine && waterEff > 0) {
            selected.forEach((f, i) => {
                const l = calc.machineLoads(areas[i], waterEff, machine.capacity);
                if (l) loads.push(Object.assign({ fieldId: f.id, fieldName: f.name }, l));
            });
        }
        const loadsTotalWater = loads.reduce((a, l) => a + l.totalWater, 0);
        if (single && loads.length === 1) {
            lines.forEach((l) => {
                l.partialProduct = l.supported && l.valid ? calc.dosePartialLoad(l.dose, l.doseType, loads[0], waterEff) : null;
            });
        }

        const name = state.name;

        // Resumen
        const supportedLines = lines.filter((l) => l.supported);
        const unsupportedLines = lines.filter((l) => !l.supported);
        const validLines = supportedLines.filter((l) => l.valid);
        const costKnown = supportedLines.length > 0 && supportedLines.every((l) => l.cost !== null);
        const totalCost = costKnown && !unsupportedLines.length ? calc.roundTo(supportedLines.reduce((a, l) => a + l.cost, 0), 2) : null;
        const ready = selected.length > 0 && validLines.length > 0 && totalCost !== null;

        // Fechas y estado
        const finishFuture = state.done && !!state.finishDate && state.finishDate > data.today;
        let status = 'pending';
        if (state.done) status = 'completed';
        else if (state.date && state.date < data.today) status = 'delayed';

        // Qué falta + errores por sección (regla 12)
        const missing = [];
        const errors = { field: [], products: [], application: [], date: [], name: [] };
        const add = (section, key, label, message) => {
            missing.push({ section: section, key: key, label: label });
            errors[section].push(message);
        };
        if (!selected.length) add('field', 'field', 'parcela', 'Elige al menos una parcela.');
        if (areaError) add('field', 'area', 'superficie', areaError);
        if (!lines.length) add('products', 'products', 'un producto', 'Añade al menos un producto.');
        else if (unsupportedLines.length) add('products', 'unsupported', 'quitar producto no válido', 'Hay productos sin dosis para este tipo. Quítalos o cambia el tipo.');
        else if (supportedLines.some((l) => !l.valid)) add('products', 'dose', 'dosis', 'Revisa las dosis: tienen que ser mayores que 0.');
        if (isSpray) {
            if (machineMode === 'none') add('application', 'machine', 'máquina', 'No tienes ninguna máquina. Crea una para poder pulverizar.');
            else if (!machine) add('application', 'machine', 'máquina', 'Elige la máquina.');
            if (!(plannedWater > 0)) add('application', 'water', 'mojado', 'Indica el mojado previsto (L/ha).');
        }
        if (!state.date) add('date', 'date', 'fecha', 'Elige una fecha.');
        if (state.done && !state.finishDate) add('date', 'finishDate', 'fecha de realización', 'Indica cuándo se hizo.');
        if (finishFuture) add('date', 'finishFuture', 'fecha de realización', 'La fecha de realización no puede ser futura.');
        if (realWaterError) add('date', 'realWater', 'mojado real', 'El mojado real tiene que ser mayor que 0.');
        if (!String(name).trim()) add('name', 'name', 'nombre', 'Pon un nombre al tratamiento.');

        return {
            isSpray: isSpray,
            isEdit: isEdit,
            status: status,
            selectedFields: selected.map((f, i) => ({ id: f.id, name: f.name, crop: f.crop, area: f.area, effectiveArea: areas[i] })),
            single: single,
            multi: multi,
            fieldCount: selected.length,
            totalArea: totalArea,
            partialActive: partialActive,
            areaError: areaError,
            machineMode: machineMode,
            machine: machine,
            water: waterEff,
            plannedWater: plannedWater,
            usesRealWater: isSpray && realWaterNum > 0,
            lines: lines,
            loads: loads,
            loadsTotalWater: loadsTotalWater,
            summary: {
                lineCount: lines.length,
                validLines: validLines.length,
                costKnown: costKnown,
                totalCost: totalCost,
                costPerHa: totalCost !== null && totalArea > 0 ? calc.roundTo(totalCost / totalArea, 2) : null,
                ready: ready,
            },
            name: name,
            finishFuture: finishFuture,
            missing: missing,
            missingText: missing.length ? 'Falta: ' + missing.map((m) => m.label).join(', ') : '',
            errors: errors,
            canSave: missing.length === 0,
            canEditTotals: single,
        };
    }

    // ── Valores para los inputs reales del formulario Django ──────────────────

    const decimalText = (n, d) => (n === null || n === undefined ? '' : n.toFixed(d));

    /**
     * Valores normalizados (punto decimal) que el controlador escribe en los inputs ocultos antes de enviar.
     * Solo tiene sentido si derive(...).canSave.
     */
    function toFormValues(state, data) {
        const d = derive(state, data);
        const isSpray = d.isSpray;
        const partial = d.single && d.partialActive;
        const lines = d.lines.map((l) => {
            const overridden = l.supported && l.override;
            return {
                product: l.productId,
                // El backend vuelve a redondear la dosis hacia arriba a 3 decimales; con total a mano la deriva del total.
                dose: l.dose === null ? '' : (overridden ? decimalText(l.dose, 4) : decimalText(l.dose, 3)),
                total_dose: l.total === null || d.multi ? '' : decimalText(l.total, 4),
                total_overridden: overridden ? 'true' : 'false',
                position: l.position,
            };
        });
        const ids = state.fieldIds.slice();
        return {
            name: d.name,
            type: state.type,
            date: state.date,
            field: ids.length ? String(ids[0]) : '',
            extra_fields: state.mode === 'create' ? ids.slice(1).map(String) : [],
            machine: isSpray && d.machine ? String(d.machine.id) : '',
            water_per_ha: isSpray ? String(Math.round(d.plannedWater || 0)) : '0',
            finish_date: state.done ? state.finishDate : '',
            real_water_per_ha: isSpray && state.done && d.usesRealWater ? String(Math.round(d.water)) : '',
            applied_area: partial && d.areaError === null && calc.parseNumber(state.appliedArea) > 0
                ? String(calc.parseNumber(state.appliedArea)) : '',
            zone_notes: partial ? String(state.zone || '').trim() : '',
            lines: lines,
        };
    }

    return {
        doseToText,
        initialState,
        actions,
        reduce,
        derive,
        toFormValues,
    };
});
