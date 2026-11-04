// Resumen de gastos por parcela: pestañas de periodo + filtros, y los datos de la API api-field-costs-data
// pintados en gráficos (Chart.js) y en listas desplegables (<details>, sin depender de Bootstrap JS).
document.addEventListener('DOMContentLoaded', function () {
    const $ = (id) => document.getElementById(id);
    const dateFromInput = $('dateFrom');
    const dateToInput = $('dateTo');
    const applyFilterBtn = $('applyDateFilter');
    const fieldsContainer = $('fieldsContainer');
    const fieldsInput = $('fieldSelectorDropdown');
    const viewModeSelector = $('viewMode');

    // Salir si no estamos en la página de resumen de gastos
    if (!dateFromInput || !dateToInput || !applyFilterBtn || !fieldsContainer || !fieldsInput || !viewModeSelector) {
        return;
    }

    const currentYear = new Date().getFullYear();
    const tabs = Array.from(document.querySelectorAll('#periodTabs .tl-tab'));
    const states = { loading: $('costsLoading'), empty: $('costsEmpty'), error: $('costsError'), body: $('costsBody') };

    // Colores de las series: variables --cs-* de treatment-styles.css (la paleta de la app)
    const css = getComputedStyle(document.documentElement);
    const SERIES = [1, 2, 3, 4, 5, 6].map(i => css.getPropertyValue('--cs-' + i).trim() || '#2E7D32');
    const OTHER = css.getPropertyValue('--cs-other').trim() || '#7A8577';
    const GRID = css.getPropertyValue('--tl-line').trim() || '#EEF0EC';
    const MUTED = css.getPropertyValue('--tl-muted').trim() || '#5F665C';
    // Más de 6 tipos: los pequeños se agrupan en «Otros» en el gráfico (una serie nunca repite color)
    const MAX_SLICES = SERIES.length;

    const nf = (min, max) => new Intl.NumberFormat('es-ES', { minimumFractionDigits: min, maximumFractionDigits: max });
    const eur = (n) => nf(2, 2).format(n) + ' €';
    const num = (n) => nf(0, 2).format(n);
    const pct = (n) => nf(1, 1).format(n) + ' %';
    const esc = (v) => String(v ?? '').replace(/[&<>"']/g, c => (
        { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

    let viewMode = 'cost';
    try { viewMode = localStorage.getItem('fieldCostsViewMode') || 'cost'; } catch (e) { /* sin almacenamiento */ }
    viewModeSelector.value = viewMode === 'quantity' ? 'quantity' : 'cost';
    viewMode = viewModeSelector.value;

    let currentData = null;
    let typeChart = null;
    let fieldChart = null;

    // ── Periodo ────────────────────────────────────────────────────────────────
    function setPeriod(value) {
        if (value === 'all') {
            dateFromInput.value = '';
            dateToInput.value = '';
        } else {
            dateFromInput.value = `${value}-01-01`;
            dateToInput.value = `${value}-12-31`;
        }
    }

    // Pestaña activa = la que coincide con las fechas; con fechas a medida no hay ninguna
    function activePeriod() {
        const from = dateFromInput.value, to = dateToInput.value;
        if (!from && !to) return 'all';
        const m = /^(\d{4})-01-01$/.exec(from);
        return m && to === `${m[1]}-12-31` ? m[1] : null;
    }

    function syncUi() {
        const active = activePeriod();
        tabs.forEach(t => {
            const on = t.dataset.period === active;
            t.classList.toggle('active', on);
            if (on) t.setAttribute('aria-current', 'true'); else t.removeAttribute('aria-current');
        });
        // Contador del botón de filtros (móvil): parcelas elegidas, fechas a medida y modo cantidades
        const selected = selectedFieldIds().length;
        const count = (selected ? 1 : 0) + (active === null ? 1 : 0) + (viewMode === 'quantity' ? 1 : 0);
        const badge = $('filtersBadge'), btn = $('filtersBtn');
        if (badge) { badge.hidden = !count; badge.textContent = count; }
        if (btn) btn.setAttribute('aria-label', count ? `Filtros (${count} activos)` : 'Filtros');
    }

    function selectedFieldIds() {
        return Array.from(fieldsInput.querySelectorAll('input[type="checkbox"]:checked')).map(cb => cb.value);
    }

    function closePanel() {
        const panel = $('filtersPanel');
        if (panel && window.bootstrap && bootstrap.Offcanvas) {
            const oc = bootstrap.Offcanvas.getInstance(panel);
            if (oc) oc.hide();
        }
    }

    function show(name) {
        Object.entries(states).forEach(([k, el]) => { if (el) el.hidden = k !== name; });
        // Las cifras clave solo acompañan a los datos: así nunca quedan las de una carga anterior
        const key = $('costKey');
        if (key) key.hidden = name !== 'body';
        if (name === 'loading') $('costSummary').textContent = 'Cargando…';
    }

    // ── Carga ──────────────────────────────────────────────────────────────────
    let requestSeq = 0;  // solo vale la respuesta de la última petición (filtros cambiados deprisa)
    function showError(expired) {
        $('costsErrorTitle').textContent = expired ? 'Tu sesión ha caducado' : 'No se han podido cargar los datos';
        $('costsErrorText').textContent = expired ? 'Inicia sesión de nuevo para ver los gastos.' : 'Comprueba la conexión e inténtalo de nuevo.';
        const login = $('costsLogin');
        if (login) { login.hidden = !expired; login.href = states.error.dataset.loginUrl || '#'; }
        $('costsRetry').hidden = expired;
        show('error');
        $('costSummary').textContent = $('costsErrorTitle').textContent;
    }

    function loadFieldCostsData() {
        const seq = ++requestSeq;
        const params = new URLSearchParams();
        const from = dateFromInput.value, to = dateToInput.value;
        if (!from && !to) {
            params.append('all', '1');
        } else {
            if (from) params.append('date_from', from);
            if (to) params.append('date_to', to);
        }
        selectedFieldIds().forEach(id => params.append('field_ids', id));
        syncUi();
        show('loading');

        fetch(`${API_URLS.fieldCosts}?${params.toString()}`)
            .then(response => {
                if (!response.ok) throw new Error(response.status);
                return response.json();
            })
            .then(data => {
                if (seq !== requestSeq) return;
                currentData = data;
                renderNoPriceWarning(data.no_price_products || []);
                renderAll();
            })
            .catch(error => {
                if (seq !== requestSeq) return;
                console.error('Error cargando datos:', error);
                showError(String(error && error.message) === '401');
            });
    }

    function renderAll() {
        const data = currentData;
        if (!data) return;
        // En cantidades, lo que cuenta es que haya producto (un producto sin precio tiene cantidad y coste 0)
        const hasData = viewMode === 'quantity'
            ? data.product_breakdown.some(t => (t.products || []).some(p => p.quantity > 0))
            : data.fields.some(f => f.total_cost > 0);
        if (!hasData) {
            const all = activePeriod() === 'all' && !selectedFieldIds().length;
            $('costsEmptyTitle').textContent = all ? 'Todavía no hay costes' : 'No hay costes con estos filtros';
            $('costsEmptyText').textContent = all
                ? 'Los costes salen de los productos de los tratamientos con precio.'
                : 'Prueba con otro periodo u otras parcelas.';
            $('costsEmptyAll').hidden = all;
            show('empty');
            $('costSummary').textContent = $('costsEmptyTitle').textContent;
            return;
        }
        show('body');
        renderSummary(data);
        renderTypes(data.product_breakdown);
        renderFields(data.fields);
        updateCharts(data);
    }

    // ── Cifras clave ───────────────────────────────────────────────────────────
    // Siempre en euros, también en modo cantidades: litros y kilos no se pueden sumar en una cifra, y el gasto
    // total y por hectárea es lo que se consulta primero (igual que los gráficos, que también van en euros).
    const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;
    function setText(id, text) { const el = $(id); if (el) el.textContent = text; }

    function renderSummary(data) {
        const n = data.fields.length;
        const area = nf(0, 2).format(data.total_area);
        setText('costKeyTotal', eur(data.total_cost));
        setText('costKeyTotalSub', plural(n, 'parcela', 'parcelas'));
        setText('costKeyPerHa', `${eur(data.cost_per_ha)}/ha`);
        setText('costKeyPerHaSub', `sobre ${area} ha`);

        // Tipo y parcela que más pesan: los mismos datos de las listas, sin cálculos nuevos
        const topType = (data.product_breakdown || []).filter(t => t.total > 0)
            .reduce((best, t) => (!best || t.total > best.total ? t : best), null);
        setText('costKeyType', topType ? topType.type_name : '—');
        setText('costKeyTypeSub', topType ? `${eur(topType.total)} · ${pct(topType.percentage)}` : 'sin precio');
        const topField = data.fields.filter(f => f.total_cost > 0)
            .reduce((best, f) => (!best || f.cost_per_ha > best.cost_per_ha ? f : best), null);
        setText('costKeyField', topField ? topField.name : '—');
        setText('costKeyFieldSub', topField ? `${eur(topField.cost_per_ha)}/ha` : 'sin precio');

        setText('costSummary', `Gasto total ${eur(data.total_cost)} en ${plural(n, 'parcela', 'parcelas')}; ` +
            `${eur(data.cost_per_ha)} por hectárea sobre ${area} ha.`);
    }

    // ── Cantidades: cada unidad por separado (no se suman litros con kilos) ────
    function qtyLabel(products) {
        const byUnit = {};
        (products || []).forEach(p => { byUnit[p.unit || ''] = (byUnit[p.unit || ''] || 0) + p.quantity; });
        return Object.entries(byUnit).map(([unit, q]) => `${num(q)} ${esc(unit)}`.trim()).join(' + ') || '—';
    }
    const typeValue = (t) => viewMode === 'cost' ? eur(t.total) : qtyLabel(t.products);
    const productValue = (p) => viewMode === 'cost' ? eur(p.total) : `${num(p.quantity)} ${esc(p.unit || '')}`.trim();
    // El % es del coste: en modo cantidades no tiene sentido
    const pctText = (v) => viewMode === 'cost' ? `<span class="cs-pct">${pct(v)}</span>` : '';

    function productLines(products) {
        return (products || []).map(p => `
            <div class="cs-prod"><span class="cs-prod-name">${esc(p.name)}</span>
                <span class="cs-val">${productValue(p)}</span>${pctText(p.percentage)}</div>`).join('');
    }

    function colorOf(index) { return index < MAX_SLICES - (currentTypeCount() > MAX_SLICES ? 1 : 0) ? SERIES[index] : OTHER; }
    function currentTypeCount() { return currentData ? currentData.product_breakdown.length : 0; }

    // ── Por tipo de producto ───────────────────────────────────────────────────
    function renderTypes(breakdown) {
        const box = $('productTypeDetails');
        if (!breakdown || !breakdown.length) { box.innerHTML = '<div class="hm-group-empty">Sin datos en este periodo.</div>'; return; }
        const head = `<div class="tl-head cs-head d-none d-md-grid" aria-hidden="true">
            <span>Tipo</span><span class="text-end">${viewMode === 'cost' ? 'Gasto' : 'Cantidad'}</span><span class="text-end">${viewMode === 'cost' ? '% del gasto' : ''}</span><span></span></div>`;
        box.innerHTML = head + breakdown.map((t, i) => `
            <details class="cs-item cs-item--type">
                <summary class="cs-row">
                    <span class="cs-name"><i class="cs-dot" style="background:${colorOf(i)}" aria-hidden="true"></i>${esc(t.type_name)}
                        <small>${t.products.length} producto${t.products.length === 1 ? '' : 's'}</small></span>
                    <span class="cs-val">${typeValue(t)}</span>
                    <span class="cs-pct">${viewMode === 'cost' ? pct(t.percentage) : ''}</span>
                    <i class="fa fa-chevron-down cs-chev" aria-hidden="true"></i>
                </summary>
                <div class="cs-more">${productLines(t.products)}</div>
            </details>`).join('');
    }

    // ── Por parcela (de más a menos €/ha) ──────────────────────────────────────
    function renderFields(fields) {
        const sorted = [...fields].sort((a, b) => b.cost_per_ha - a.cost_per_ha || a.name.localeCompare(b.name, 'es'));
        const cost = viewMode === 'cost';
        const head = `<div class="tl-head cs-head cs-head--fields d-none d-md-grid" aria-hidden="true">
            <span>Parcela</span><span class="text-end">Superficie</span><span class="text-end">${cost ? 'Gasto' : 'Cantidad'}</span><span class="text-end">${cost ? '€/ha' : ''}</span><span></span></div>`;
        fieldsContainer.innerHTML = head + sorted.map(f => {
            const has = f.product_breakdown && f.product_breakdown.length;
            const all = (f.product_breakdown || []).flatMap(t => t.products);
            const body = has
                ? f.product_breakdown.map(t => `
                    <div class="cs-type-line"><b>${esc(t.type_name)}</b><span class="cs-val">${typeValue(t)}</span>${pctText(t.percentage)}</div>
                    ${productLines(t.products)}`).join('')
                : '<div class="cs-prod text-muted">Sin tratamientos con productos en este periodo.</div>';
            return `
            <details class="cs-item cs-item--field">
                <summary class="cs-row">
                    <span class="cs-name">${esc(f.name)}<small class="d-md-none">${num(f.area)} ha</small></span>
                    <span class="cs-area d-none d-md-block">${num(f.area)} ha</span>
                    <span class="cs-val">${cost ? eur(f.total_cost) : qtyLabel(all)}</span>
                    <span class="cs-pct">${cost ? eur(f.cost_per_ha) + '<small>/ha</small>' : ''}</span>
                    <i class="fa fa-chevron-down cs-chev" aria-hidden="true"></i>
                </summary>
                <div class="cs-more">${body}</div>
            </details>`;
        }).join('');
    }

    // ── Gráficos: siempre en euros (litros y kilos no se pueden sumar en un mismo gráfico) ──
    function updateCharts(data) {
        if (typeof Chart === 'undefined') return;  // sin la librería, las listas dan los mismos datos

        const types = data.product_breakdown.filter(t => t.total > 0);
        let labels = types.map(t => t.type_name), values = types.map(t => t.total);
        if (types.length > MAX_SLICES) {
            const rest = types.slice(MAX_SLICES - 1).reduce((s, t) => s + t.total, 0);
            labels = labels.slice(0, MAX_SLICES - 1).concat('Otros');
            values = values.slice(0, MAX_SLICES - 1).concat(rest);
        }
        const colors = labels.map((_, i) => (types.length > MAX_SLICES && i === labels.length - 1) ? OTHER : SERIES[i]);
        const typeData = { labels, datasets: [{ data: values, backgroundColor: colors, borderColor: '#fff', borderWidth: 2 }] };

        const top = [...data.fields].filter(f => f.total_cost > 0).sort((a, b) => b.cost_per_ha - a.cost_per_ha).slice(0, 8);
        const fieldData = {
            labels: top.map(f => f.name),
            datasets: [{ label: '€/ha', data: top.map(f => f.cost_per_ha), backgroundColor: SERIES[0], borderRadius: 4, maxBarThickness: 22 }]
        };

        if (typeChart) {
            typeChart.data = typeData; typeChart.update();
        } else {
            typeChart = new Chart($('productTypeChart').getContext('2d'), {
                type: 'doughnut',
                data: typeData,
                options: {
                    responsive: true, maintainAspectRatio: false, cutout: '58%',
                    plugins: {
                        legend: { position: 'bottom', labels: { boxWidth: 12, color: MUTED } },
                        tooltip: { callbacks: { label: (c) => `${c.label}: ${eur(c.raw)}` } }
                    }
                }
            });
        }
        if (fieldChart) {
            fieldChart.data = fieldData; fieldChart.update();
        } else {
            fieldChart = new Chart($('fieldCostChart').getContext('2d'), {
                type: 'bar',
                data: fieldData,
                options: {
                    responsive: true, maintainAspectRatio: false, indexAxis: 'y',
                    plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => `${eur(c.raw)}/ha` } } },
                    scales: {
                        x: { grid: { color: GRID }, border: { display: false }, ticks: { color: MUTED } },
                        y: { grid: { display: false }, ticks: { color: MUTED } }
                    }
                }
            });
        }
    }

    // ── Aviso de productos sin precio ──────────────────────────────────────────
    function renderNoPriceWarning(products) {
        const container = $('noPriceWarning');
        if (!products || !products.length) { container.innerHTML = ''; return; }
        const totalTreatments = products.reduce((sum, p) => sum + p.treatment_count, 0);
        const rows = products.map(p => `
            <li><b>${esc(p.name)}</b> <span class="text-muted">· ${p.treatment_count} ${p.treatment_count === 1 ? 'tratamiento' : 'tratamientos'} en ${esc(p.fields.join(', '))}</span></li>`).join('');
        container.innerHTML = `
            <details class="cs-warn">
                <summary>
                    <i class="fa fa-triangle-exclamation" aria-hidden="true"></i>
                    <span><b>${products.length} producto${products.length > 1 ? 's' : ''} sin precio</b>
                        · ${totalTreatments} tratamiento${totalTreatments !== 1 ? 's' : ''} afectado${totalTreatments !== 1 ? 's' : ''}.
                        El coste mostrado puede estar subestimado.</span>
                    <i class="fa fa-chevron-down cs-chev" aria-hidden="true"></i>
                </summary>
                <div class="cs-warn-body">
                    <ul>${rows}</ul>
                    <a class="fw-semibold" href="/productos/">Actualizar precios <i class="fa fa-arrow-right fa-xs" aria-hidden="true"></i></a>
                </div>
            </details>`;
    }

    // ── Eventos ────────────────────────────────────────────────────────────────
    tabs.forEach(t => t.addEventListener('click', () => { setPeriod(t.dataset.period); loadFieldCostsData(); }));

    applyFilterBtn.addEventListener('click', () => { closePanel(); loadFieldCostsData(); });

    fieldsInput.querySelectorAll('input[type="checkbox"]').forEach(cb => cb.addEventListener('change', loadFieldCostsData));

    // Cambiar el modo no recarga: se repintan los datos que ya hay
    viewModeSelector.addEventListener('change', function () {
        viewMode = this.value;
        try { localStorage.setItem('fieldCostsViewMode', viewMode); } catch (e) { /* sin almacenamiento */ }
        syncUi();
        renderAll();
    });

    // Limpiar: año en curso, todas las parcelas y euros
    $('resetFiltersBtn').addEventListener('click', () => {
        setPeriod(String(currentYear));
        viewModeSelector.value = 'cost';
        viewMode = 'cost';
        try { localStorage.setItem('fieldCostsViewMode', viewMode); } catch (e) { /* sin almacenamiento */ }
        fieldsInput.querySelectorAll('input[type="checkbox"]').forEach(cb => { cb.checked = false; });
        const search = fieldsInput.querySelector('.filter-dd-search');
        if (search) { search.value = ''; search.dispatchEvent(new Event('input')); }
        // base.html repinta la etiqueta del desplegable al oír «change»; sin recargar por cada casilla
        const first = fieldsInput.querySelector('input[type="checkbox"]');
        if (first) first.dispatchEvent(new Event('change'));
        else loadFieldCostsData();
    });

    $('costsRetry').addEventListener('click', loadFieldCostsData);
    $('costsEmptyAll').addEventListener('click', () => { setPeriod('all'); loadFieldCostsData(); });

    // Inicio: año en curso
    setPeriod(String(currentYear));
    loadFieldCostsData();
});
