/**
 * Gráficas de Estadísticas (Chart.js 4.4.0, versionado en static/js/vendor).
 * - Los datos llegan con json_script (#stats-charts-data); aquí no se interpola nada del servidor.
 * - Colores, tooltips y leyenda clicable de la pantalla original (barras mensuales + rosquilla de tipos).
 * - Las funciones puras se exportan para los tests de node.
 * - Si Chart.js no carga, se ocultan los lienzos y se abren los «Ver datos»: las tablas siguen ahí.
 */
(function (root, factory) {
    if (typeof module === 'object' && module.exports) module.exports = factory();
    else root.StatsCharts = factory();
}(typeof self !== 'undefined' ? self : this, function () {
    'use strict';

    // Paleta verde-campo original
    const GREEN = '#2D6A4F';
    const TEAL = '#40916C';
    const LIME = '#74C69D';
    const ACCENT = '#D4A017';
    const BLUE = '#3A86FF';
    const PURPLE = '#8338EC';
    const ORANGE = '#FB5607';
    const DOUGHNUT_PALETTE = [GREEN, TEAL, LIME, ACCENT, BLUE, PURPLE, ORANGE, '#FF006E', '#FFBE0B', '#8ECAE6'];
    const FONT = "'Inter', 'Segoe UI', sans-serif";
    const TEXT = '#6c757d';

    function plural(n, singular, pluralForm) {
        return n + ' ' + (n === 1 ? singular : pluralForm);
    }

    // Cada sector toma el siguiente color de la paleta; con más de 10 tipos se repite
    function doughnutColors(count) {
        return Array.from({ length: count }, (_, i) => DOUGHNUT_PALETTE[i % DOUGHNUT_PALETTE.length]);
    }

    // Barras mensuales: verde claro y el mes más activo en dorado (solo si hay uno)
    function monthsConfig(data) {
        const peak = Number.isInteger(data.peak) ? data.peak : null;
        return {
            type: 'bar',
            data: {
                labels: data.labels,
                datasets: [{
                    label: 'Tratamientos',
                    data: data.counts,
                    backgroundColor: data.counts.map((_, i) => (i === peak ? ACCENT : LIME)),
                    borderRadius: 6,
                    borderSkipped: false,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: { callbacks: { label: c => ' ' + plural(c.raw, 'tratamiento', 'tratamientos') } },
                },
                scales: {
                    y: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: 'rgba(0,0,0,0.05)' } },
                    x: { grid: { display: false } },
                },
            },
        };
    }

    // Rosquilla de usos por tipo de producto; la leyenda es la de Chart.js (clic = ocultar/mostrar sector)
    function typesConfig(data) {
        return {
            type: 'doughnut',
            data: {
                labels: data.labels,
                datasets: [{
                    data: data.data,
                    backgroundColor: doughnutColors(data.data.length),
                    borderWidth: 2,
                    borderColor: '#fff',
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '60%',
                plugins: {
                    legend: { position: 'bottom', labels: { boxWidth: 12, padding: 10, font: { size: 11 } } },
                    tooltip: { callbacks: { label: c => ' ' + c.label + ': ' + plural(c.raw, 'uso', 'usos') } },
                },
            },
        };
    }

    function showFallback(doc) {
        doc.querySelectorAll('[data-st-chart]').forEach(c => { c.parentElement.hidden = true; });
        doc.querySelectorAll('details[data-st-data]').forEach(d => { d.open = true; });
    }

    function init(win) {
        const doc = win.document;
        if (!doc.querySelector('[data-st-chart]')) return;
        const holder = doc.getElementById('stats-charts-data');
        let data = null;
        try { data = holder ? JSON.parse(holder.textContent) : null; } catch (e) { data = null; }
        const Chart = win.Chart;
        if (!Chart || !data) { showFallback(doc); return; }

        Chart.defaults.font.family = FONT;
        Chart.defaults.color = TEXT;
        const builders = {
            months: () => monthsConfig(data.months),
            types: () => typesConfig(data.productTypes),
        };
        doc.querySelectorAll('canvas[data-st-chart]').forEach(canvas => {
            const build = builders[canvas.dataset.stChart];
            if (!build) return;
            try {
                new Chart(canvas, build());
            } catch (e) {
                canvas.parentElement.hidden = true;
                const section = canvas.closest('section');
                const d = section && section.querySelector('details[data-st-data]');
                if (d) d.open = true;
            }
        });
    }

    if (typeof window !== 'undefined' && window.document) {
        if (window.document.readyState === 'loading') window.document.addEventListener('DOMContentLoaded', () => init(window));
        else init(window);
    }

    return { DOUGHNUT_PALETTE, ACCENT, LIME, doughnutColors, monthsConfig, typesConfig, init };
}));
