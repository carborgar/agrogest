/**
 * Cálculos de tratamientos en el cliente (sin DOM).
 *
 * Es un espejo EXACTO de la lógica del backend, que es la fuente de verdad:
 *   farm/models.py → TreatmentProduct.calculate_total_dose / calculate_dose_from_total /
 *   get_dose_per_load / calculate_prices, Treatment.calculate_machine_loads /
 *   calculate_product_for_partial_load, y farm/forms.py → TreatmentProductForm.clean_dose.
 * Los dos lados se prueban contra el mismo fichero de casos
 * (farm/tests/fixtures/treatment_calc_cases.json): si cambia uno, fallan los tests.
 *
 * Todas las funciones devuelven `null` cuando no se puede calcular (falta el mojado,
 * área 0, dato no numérico...). Nunca 0 ni NaN en silencio.
 *
 * Se expone en window.TreatmentCalc y en module.exports (para probarlo con Node).
 */
(function (root, factory) {
    'use strict';
    const api = factory();
    if (typeof module === 'object' && module.exports) {
        module.exports = api;
    } else {
        root.TreatmentCalc = api;
    }
})(typeof window !== 'undefined' ? window : globalThis, function () {
    'use strict';

    /** Por debajo de este volumen (L) la última cuba no cuenta como cuba parcial. */
    const PARTIAL_LOAD_THRESHOLD_L = 50;
    /** Desviación (relativa) respecto a la dosis recomendada a partir de la cual se avisa. */
    const DOSE_WARNING_RATIO = 0.25;

    /** Etiquetas de unidad por tipo de dosis (Product.*_DOSE_TYPE_CHOICES). */
    const DOSE_UNITS = {
        l_per_1000l: 'L/1000L',
        kg_per_1000l: 'kg/1000L',
        kg_per_ha: 'kg/ha',
        l_per_ha: 'L/ha',
        pct: '%',
    };

    // ── Utilidades numéricas ──────────────────────────────────────────────────

    function isNum(v) {
        return typeof v === 'number' && Number.isFinite(v);
    }

    /** Redondeo a `d` decimales (mitad hacia arriba) sin ruido de coma flotante. */
    function roundTo(value, d) {
        if (!isNum(value)) return null;
        const shifted = Number(Math.abs(value) + 'e' + d);
        const r = Number(Math.round(shifted) + 'e-' + d);
        return value < 0 ? -r : r;
    }

    /** Equivale al round() de Python con 0 decimales (mitad al par): Treatment.calculate_machine_loads. */
    function roundHalfEven(x) {
        const f = Math.floor(x);
        const diff = x - f;
        if (diff > 0.5) return f + 1;
        if (diff < 0.5) return f;
        return f % 2 === 0 ? f : f + 1;
    }

    /** 'ha' | '1000l' | 'pct' | null, igual que las ramas del modelo. */
    function doseKind(doseType) {
        if (doseType === 'kg_per_ha' || doseType === 'l_per_ha') return 'ha';
        if (doseType === 'kg_per_1000l' || doseType === 'l_per_1000l') return '1000l';
        if (doseType === 'pct') return 'pct';
        return null;
    }

    const positive = (v) => isNum(v) && v > 0;

    // ── Parseo y redondeo de lo que teclea el usuario ─────────────────────────

    /**
     * Texto → número. Acepta coma o punto decimal y espacios. Devuelve null si está
     * vacío, no es un número o es negativo.
     *
     * Decisión sobre «1.000»: es ambiguo (¿uno o mil?), así que se RECHAZA (null) cuando
     * tiene un punto seguido de exactamente tres dígitos y la parte entera no es 0
     * (agrupación de miles). «0.075» sí es válido; «1,000» (coma) es 1. Lo mismo con
     * «1.000.000» o «1.000,5».
     */
    function parseNumber(input) {
        if (isNum(input)) return input >= 0 ? input : null;
        if (typeof input !== 'string') return null;
        const s = input.replace(/\s+/g, '');
        if (s === '') return null;
        if (/^\d{1,3}(\.\d{3})+(,\d+)?$/.test(s) && !/^0\./.test(s)) return null; // miles con punto
        if (!/^(\d+[.,]?\d*|[.,]\d+)$/.test(s)) return null;
        const n = parseFloat(s.replace(',', '.'));
        return isNum(n) ? n : null;
    }

    /**
     * true si el texto tecleado tiene un punto de miles (1.500, 2.381, 1.000.000): es ambiguo, así que
     * parseNumber lo rechaza y la pantalla pide usar la coma («1,5»). «0.075» no cuenta.
     */
    function hasThousandsDot(input) {
        if (typeof input !== 'string') return false;
        const s = input.replace(/\s+/g, '');
        return /^\d{1,3}(\.\d{3})+(,\d+)?$/.test(s) && !/^0\./.test(s);
    }

    /**
     * Número que viene del SERVIDOR (inputs del formset, JSON): siempre con punto decimal, nunca miles.
     * «1.500» es uno y medio. Estricto: solo dígitos con un punto opcional; si no, null.
     */
    function parseServerNumber(input) {
        if (isNum(input)) return input >= 0 ? input : null;
        if (typeof input !== 'string') return null;
        const s = input.trim();
        if (!/^\d+(\.\d+)?$/.test(s)) return null;
        const n = parseFloat(s);
        return isNum(n) ? n : null;
    }

    /** Número → texto como lo teclearía el usuario en España: coma decimal, sin miles, sin ceros finales. */
    function numberToText(n, maxDecimals) {
        if (!isNum(n)) return '';
        return n.toLocaleString('es-ES', { useGrouping: false, minimumFractionDigits: 0, maximumFractionDigits: maxDecimals === undefined ? 4 : maxDecimals });
    }

    /**
     * Redondeo de la dosis tecleada: hacia arriba a 3 decimales (clean_dose, ROUND_UP).
     * Trabaja con enteros para evitar la coma flotante (0,0754 → 0,076; 2,1 → 2,1; 0,3 → 0,3).
     * Usa 9 decimales de resolución (el plan sugería 6) para no perder el redondeo hacia
     * arriba en entradas con 7+ decimales.
     */
    function roundDoseUp(value) {
        if (!isNum(value) || value < 0) return null;
        return Math.ceil(Math.round(value * 1e9) / 1e6) / 1e3;
    }

    // ── Área y unidades ───────────────────────────────────────────────────────

    /** Treatment.effective_area: el área parcial si es > 0; si no, la de la parcela. */
    function effectiveArea(fieldArea, appliedArea) {
        if (positive(appliedArea)) return appliedArea;
        return isNum(fieldArea) ? fieldArea : null;
    }

    /** TreatmentProduct.set_dose_units: kg para kg_per_*; litros para el resto (también %). */
    function totalUnit(doseType) {
        return typeof doseType === 'string' && doseType.indexOf('kg_per_') === 0 ? 'kg' : 'L';
    }

    // ── Dosis ↔ total ─────────────────────────────────────────────────────────

    /** TreatmentProduct.calculate_total_dose (4 decimales). */
    function totalFromDose(dose, doseType, area, waterPerHa) {
        if (!isNum(dose) || dose < 0 || !positive(area)) return null;
        const kind = doseKind(doseType);
        if (kind === 'ha') return roundTo(dose * area, 4);
        if (kind === '1000l') return positive(waterPerHa) ? roundTo((dose * (waterPerHa * area)) / 1000, 4) : null;
        if (kind === 'pct') return positive(waterPerHa) ? roundTo((dose / 100) * (waterPerHa * area), 4) : null;
        return null;
    }

    /** TreatmentProduct.calculate_dose_from_total (4 decimales). */
    function doseFromTotal(total, doseType, area, waterPerHa) {
        if (!isNum(total) || total < 0 || !positive(area)) return null;
        const kind = doseKind(doseType);
        if (kind === 'ha') return roundTo(total / area, 4);
        if (kind === '1000l') return positive(waterPerHa) ? roundTo((total * 1000) / (waterPerHa * area), 4) : null;
        if (kind === 'pct') return positive(waterPerHa) ? roundTo((total * 100) / (waterPerHa * area), 4) : null;
        return null;
    }

    // ── Cubas ─────────────────────────────────────────────────────────────────

    /** TreatmentProduct.get_dose_per_load (4 decimales). Solo pulverización con máquina y mojado. */
    function dosePerFullLoad(dose, doseType, capacity, waterPerHa) {
        if (!isNum(dose) || dose <= 0 || !positive(capacity) || !positive(waterPerHa)) return null;
        const kind = doseKind(doseType);
        if (kind === 'ha') return roundTo(dose * (capacity / waterPerHa), 4);
        if (kind === '1000l') return roundTo((dose * capacity) / 1000, 4);
        if (kind === 'pct') return roundTo((dose * capacity) / 100, 4);
        return null;
    }

    /**
     * Treatment.calculate_machine_loads. null si falta máquina, mojado o área.
     * partialLoad = la última cuba lleva más de 50 L.
     */
    function machineLoads(area, waterPerHa, capacity) {
        if (!positive(area) || !positive(waterPerHa) || !positive(capacity)) return null;
        const totalWater = roundHalfEven(area * waterPerHa);
        const partialWater = totalWater % capacity;
        return {
            totalWater: totalWater,
            fullLoads: Math.floor(totalWater / capacity),
            partialWater: partialWater,
            partialLoad: partialWater > PARTIAL_LOAD_THRESHOLD_L,
        };
    }

    /**
     * Treatment.calculate_product_for_partial_load (4 decimales).
     * `loads` es el resultado de machineLoads. Devuelve 0 si no hay cuba parcial (como el modelo).
     */
    function dosePartialLoad(dose, doseType, loads, waterPerHa) {
        if (!loads || !loads.partialLoad) return 0;
        if (!isNum(dose) || dose < 0) return null;
        const kind = doseKind(doseType);
        if (kind === 'ha') return positive(waterPerHa) ? roundTo(dose * (loads.partialWater / waterPerHa), 4) : null;
        if (kind === '1000l') return roundTo((dose * loads.partialWater) / 1000, 4);
        if (kind === 'pct') return roundTo((dose * loads.partialWater) / 100, 4);
        return null;
    }

    // ── Dinero ────────────────────────────────────────────────────────────────

    /** TreatmentProduct.calculate_prices: total_price = unit_price × total_dose (2 decimales). */
    function lineCost(total, unitPrice) {
        if (!isNum(total) || !isNum(unitPrice) || total < 0 || unitPrice < 0) return null;
        return roundTo(total * unitPrice, 2);
    }

    /** price_per_ha = total_price / área efectiva (2 decimales). */
    function costPerHa(totalCost, area) {
        if (!isNum(totalCost) || !positive(area)) return null;
        return roundTo(totalCost / area, 2);
    }

    // ── Aviso de dosis ────────────────────────────────────────────────────────

    /** |dosis − recomendada| / recomendada; null si no se puede comparar. */
    function deviation(dose, recommended) {
        if (!isNum(dose) || !positive(recommended)) return null;
        return Math.abs(dose - recommended) / recommended;
    }

    /** true si la dosis se aparta de la recomendada en DOSE_WARNING_RATIO o más. */
    function isFarFromRecommended(dose, recommended) {
        const d = deviation(dose, recommended);
        return d !== null && d >= DOSE_WARNING_RATIO;
    }

    return {
        PARTIAL_LOAD_THRESHOLD_L,
        DOSE_WARNING_RATIO,
        DOSE_UNITS,
        roundTo,
        roundHalfEven,
        parseNumber,
        hasThousandsDot,
        parseServerNumber,
        numberToText,
        roundDoseUp,
        effectiveArea,
        totalUnit,
        totalFromDose,
        doseFromTotal,
        dosePerFullLoad,
        machineLoads,
        dosePartialLoad,
        lineCost,
        costPerHa,
        deviation,
        isFarFromRecommended,
    };
});
