document.addEventListener('DOMContentLoaded', function () {
    // ── Utilidades ────────────────────────────────────────────────────────
    const esc = (v) => String(v ?? '').replace(/[&<>"']/g, c => (
        { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const isMobile = () => window.innerWidth < 768;
    // YYYY-MM-DD en hora local (toISOString usa UTC y puede desplazar el día)
    const toDateStr = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;

    const STATUS_STYLE = {
        pending: { bg: '#ffc107', fg: '#212529', cls: 'treatment-pending' },
        delayed: { bg: '#dc3545', fg: '#ffffff', cls: 'treatment-delayed' },
        completed: { bg: '#198754', fg: '#ffffff', cls: 'treatment-completed' },
    };
    const TYPE_ICON = { spraying: 'spray-can-sparkles', fertigation: 'droplet' };

    // Preferencias por dispositivo (filtros y vista); si el almacenamiento falla, se ignora.
    const STORE_KEY = 'agrogest.calendar.v1';
    const store = {
        get() { try { return JSON.parse(localStorage.getItem(STORE_KEY)) || {}; } catch (e) { return {}; } },
        set(patch) { try { localStorage.setItem(STORE_KEY, JSON.stringify({ ...this.get(), ...patch })); } catch (e) { /* sin almacenamiento */ } },
    };
    const saved = store.get();

    // ── Filtros ───────────────────────────────────────────────────────────
    const filterAll = document.getElementById('filter-all');
    const fieldCheckboxes = [...document.querySelectorAll('.field-checkbox')];
    const typeCheckboxes = [...document.querySelectorAll('.treatment-type-checkbox')];
    const statusCheckboxes = [...document.querySelectorAll('.status-checkbox')];
    const fieldLabel = document.getElementById('field-filter-label');

    function restoreFilters() {
        if (Array.isArray(saved.fields)) fieldCheckboxes.forEach(cb => { cb.checked = saved.fields.includes(cb.value); });
        if (Array.isArray(saved.types)) typeCheckboxes.forEach(cb => { cb.checked = saved.types.includes(cb.value); });
        if (Array.isArray(saved.statuses)) statusCheckboxes.forEach(cb => { cb.checked = saved.statuses.includes(cb.value); });
    }

    function refreshFieldFilterUi() {
        const selected = fieldCheckboxes.filter(cb => cb.checked);
        filterAll.checked = selected.length === 0;
        filterAll.closest('.field-filter-item')?.classList.toggle('active', selected.length === 0);
        fieldLabel.textContent = selected.length === 0 ? 'Todas las parcelas'
            : selected.length === 1 ? selected[0].dataset.name
                : `${selected.length} parcelas`;
    }

    const checkedValues = (list) => list.filter(cb => cb.checked).map(cb => cb.value);

    // Nº de filtros distintos del valor por defecto (se muestra en el botón "Filtros" de móvil)
    function updateFilterBadge() {
        const badge = document.getElementById('cm-filter-badge');
        if (!badge) return;
        const n = checkedValues(fieldCheckboxes).length
            + [...typeCheckboxes, ...statusCheckboxes].filter(cb => !cb.checked).length;
        badge.textContent = n;
        badge.classList.toggle('d-none', n === 0);
    }

    function persistFilters() {
        updateFilterBadge();
        store.set({
            fields: checkedValues(fieldCheckboxes),
            types: checkedValues(typeCheckboxes),
            statuses: checkedValues(statusCheckboxes),
        });
    }

    restoreFilters();
    refreshFieldFilterUi();
    updateFilterBadge();

    // ── Calendario ────────────────────────────────────────────────────────
    // FullCalendar solo se crea en escritorio (≥768 px); en móvil se usa el componente propio de más abajo.
    let calendar = null;
    function initDesktop() {
        const calendarEl = document.getElementById('calendar');
        calendar = new FullCalendar.Calendar(calendarEl, {
            themeSystem: 'bootstrap5',
            initialView: saved.view || 'dayGridMonth',
            locale: 'es',
            height: 'auto',
            headerToolbar: {
                left: 'prev,next',
                center: 'title',
                right: 'today dayGridMonth,listWeek',
            },
            buttonText: { today: 'Hoy' },
            views: {
                dayGridMonth: { buttonText: 'Mes' },
                listWeek: { buttonText: 'Semana', noEventsContent: 'No hay tratamientos esta semana' },
            },
            events: fetchEvents,
            displayEventTime: false,
            dayMaxEvents: 3,
            moreLinkText: n => `+${n} más`,
            // Arrastrar para reprogramar (solo pendientes y atrasados; en táctil, con pulsación larga)
            editable: true,
            eventDurationEditable: false,
            longPressDelay: 350,
            eventLongPressDelay: 350,
            eventContent: renderEventContent,
            eventClick: (info) => loadTreatmentDetail(info.event),
            dateClick: (info) => openDay(info.dateStr),
            // Un modal propio en vez del popover de la librería: devolver true evita que se abra también
            moreLinkClick: (info) => { openDay(toDateStr(info.date)); return true; },
            eventDrop: onEventDrop,
            datesSet: (info) => store.set({ view: info.view.type }),
        });
        calendar.render();
    }


    filterAll.addEventListener('change', () => {
        fieldCheckboxes.forEach(cb => { cb.checked = false; });
        refreshFieldFilterUi();
        persistFilters();
        refetchAll();
    });
    fieldCheckboxes.forEach(cb => cb.addEventListener('change', () => {
        refreshFieldFilterUi(); persistFilters(); refetchAll();
    }));
    [...typeCheckboxes, ...statusCheckboxes].forEach(cb => cb.addEventListener('change', () => {
        persistFilters(); refetchAll();
    }));

    // ── Eventos ───────────────────────────────────────────────────────────
    // Carga tratamientos de un rango [start, end) con los filtros actuales (statusOverride fuerza el estado).
    function loadTreatments(start, end, statusOverride = null) {
        // Sin ninguna opción marcada se envía 'none' (la API trata la lista vacía como "sin filtro").
        const types = checkedValues(typeCheckboxes);
        const statuses = statusOverride ? [statusOverride] : checkedValues(statusCheckboxes);
        const params = new URLSearchParams({
            start, end,
            fields: checkedValues(fieldCheckboxes).join(','),
            types: types.length ? types.join(',') : 'none',
            statuses: statuses.length ? statuses.join(',') : 'none',
        });
        return fetch(`${API_URLS.treatments}?${params.toString()}`).then(response => {
            if (response.status === 401) { window.location.reload(); throw new Error('Sesión caducada'); }
            if (!response.ok) throw new Error('Error cargando eventos');
            return response.json();
        });
    }

    function fetchEvents(info, successCallback, failureCallback) {
        loadTreatments(info.startStr.split('T')[0], info.endStr.split('T')[0])
            .then(data => successCallback(data.map(formatEvent)))
            .catch(error => {
                console.error('Error cargando eventos:', error);
                failureCallback(error);
            });
    }

    // Recarga la vista activa (escritorio o móvil)
    function refetchAll() {
        if (calendar && !isMobile()) calendar.refetchEvents();
        if (mobileReady && isMobile()) mLoad();
    }

    function formatEvent(treatment) {
        const style = STATUS_STYLE[treatment.status] || STATUS_STYLE.pending;
        return {
            id: treatment.id,
            title: treatment.name,
            start: treatment.date,
            allDay: true,
            backgroundColor: style.bg,
            borderColor: style.bg,
            textColor: style.fg,
            classNames: [style.cls],
            editable: treatment.editable,
            extendedProps: treatment,
        };
    }

    // Mes: icono + nombre + parcela, en una línea. Semana (agenda): nombre · parcela · tipo.
    function renderEventContent(arg) {
        const t = arg.event.extendedProps;
        if (arg.view.type.startsWith('list')) {
            return {
                html: `<span class="fw-semibold">${esc(arg.event.title)}</span>
                       <span class="text-muted small"> · ${esc(t.field_name)} · ${esc(t.type_display)}</span>`,
            };
        }
        return {
            html: `<div class="fc-ev-line"><i class="fa fa-${TYPE_ICON[t.type] || 'flask'} fc-ev-icon"></i>
                   <span class="fc-ev-title">${esc(arg.event.title)}</span>
                   <span class="fc-ev-field">${esc(t.field_name)}</span></div>`,
        };
    }

    // ── Reprogramar arrastrando ───────────────────────────────────────────
    function csrfHeaders() { return { 'X-CSRFToken': API_URLS.csrfToken }; }

    function moveTreatment(id, dateStr) {
        return fetch(API_URLS.treatmentMove(id), {
            method: 'POST',
            headers: csrfHeaders(),
            body: new URLSearchParams({ date: dateStr }),
        }).then(r => { if (!r.ok) throw new Error('No se pudo mover'); return r.json(); });
    }

    // Aviso de "movido" con opción de deshacer (común a arrastrar y a cambiar la fecha desde el detalle)
    function announceMove(id, oldDate, newDate, status) {
        refetchAll(); // el estado (pendiente/atrasado) puede cambiar al mover
        Swal.fire({
            toast: true, position: 'bottom', icon: 'success',
            title: `${status === 'completed' ? 'Finalización movida al' : 'Movido al'} ${formatDate(new Date(`${newDate}T00:00:00`))}`,
            showConfirmButton: true, confirmButtonText: 'Deshacer',
            timer: 6000, timerProgressBar: true, heightAuto: false,
        }).then(result => {
            if (result.isConfirmed) moveTreatment(id, oldDate).then(refetchAll).catch(() => refetchAll());
        });
    }

    function moveError() {
        Swal.fire({ toast: true, position: 'bottom', icon: 'error', title: 'No se pudo mover el tratamiento', showConfirmButton: false, timer: 3500, heightAuto: false });
    }

    function onEventDrop(info) {
        const id = info.event.id;
        const newDate = info.event.startStr.slice(0, 10);
        const oldDate = info.oldEvent.startStr.slice(0, 10);
        moveTreatment(id, newDate)
            .then(() => announceMove(id, oldDate, newDate, info.event.extendedProps.status))
            .catch(() => { info.revert(); moveError(); });
    }

    // ── Modal único con dos paneles ───────────────────────────────────────
    const modalEl = document.getElementById('treatment-detail');
    const paneDay = document.getElementById('pane-day');
    const paneDetail = document.getElementById('pane-detail');

    // Muestra un panel con una pequeña transición (forward: entra por la derecha; back: por la izquierda)
    function showPane(pane, direction) {
        [paneDay, paneDetail].forEach(p => {
            p.classList.toggle('d-none', p !== pane);
            p.classList.remove('cal-in-forward', 'cal-in-back');
        });
        if (direction) {
            void pane.offsetWidth; // reinicia la animación
            pane.classList.add(direction === 'back' ? 'cal-in-back' : 'cal-in-forward');
        }
        const body = pane.querySelector('.modal-body');
        if (body) body.scrollTop = 0;
    }

    function ensureModalOpen() {
        const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
        if (!modalEl.classList.contains('show')) modal.show();
        return modal;
    }

    // ── Panel de día ──────────────────────────────────────────────────────
    function openDay(dateStr, fromDetail = false) {
        const date = new Date(`${dateStr}T00:00:00`);
        const title = new Intl.DateTimeFormat('es-ES', { weekday: 'long', day: 'numeric', month: 'long' }).format(date);
        document.getElementById('day-title').textContent = title.charAt(0).toUpperCase() + title.slice(1);
        document.getElementById('day-new').href = `${API_URLS.treatmentCreate}?date=${dateStr}`;

        const events = (calendar ? calendar.getEvents() : []).filter(e => e.startStr.slice(0, 10) === dateStr);
        const list = document.getElementById('day-list');
        list.innerHTML = events.length ? '' : '<div class="text-center text-muted small py-3">No hay tratamientos este día</div>';
        events.forEach(ev => {
            const t = ev.extendedProps;
            const style = STATUS_STYLE[t.status] || STATUS_STYLE.pending;
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'btn btn-light text-start d-flex align-items-center gap-2 py-2';
            btn.innerHTML = `<span class="calendar-legend-dot" style="background:${style.bg}"></span>
                <span class="flex-grow-1 min-w-0">
                    <span class="d-block fw-semibold small text-truncate">${esc(ev.title)}</span>
                    <span class="d-block small text-muted text-truncate">${esc(t.field_name)} · ${esc(t.type_display)}</span>
                </span>
                <i class="fa fa-chevron-right text-muted small"></i>`;
            btn.addEventListener('click', () => loadTreatmentDetail(ev, dateStr));
            list.appendChild(btn);
        });
        showPane(paneDay, fromDetail ? 'back' : null);
        ensureModalOpen();
    }

    // ── Detalle bajo demanda ──────────────────────────────────────────────
    // fromDay: fecha (YYYY-MM-DD) del modal de día desde el que se abre, para poder volver a él
    function loadTreatmentDetail(event, fromDay = null) {
        const treatmentId = event.id;
        const treatmentModal = modalEl;
        const waterWrap = document.getElementById('water-wrap');
        const machineWrap = document.getElementById('machine-wrap');
        const finishBtn = document.getElementById('detail-finish');

        // Información básica inmediata
        document.querySelector('.treatment-title').textContent = event.title;
        document.getElementById('detail-meta').textContent = formatDate(event.start);
        document.getElementById('view-treatment').href = `/tratamientos/${treatmentId}`;
        document.getElementById('detail-clone').href = API_URLS.treatmentClone(treatmentId);
        finishBtn.classList.add('d-none');

        // Cambio de fecha (en móvil no hay arrastrar): planificada, o de finalización si está completado
        const dateInput = document.getElementById('detail-date');
        const oldDate = toDateStr(event.start);
        const evStatus = event.extendedProps?.status;
        document.getElementById('detail-date-label').textContent =
            evStatus === 'completed' ? 'Fecha de finalización' : 'Fecha planificada';
        dateInput.value = oldDate;
        dateInput.onchange = () => {
            const newDate = dateInput.value;
            if (!newDate || newDate === oldDate) return;
            moveTreatment(treatmentId, newDate)
                .then(() => {
                    treatmentModal.addEventListener('hidden.bs.modal', () => announceMove(treatmentId, oldDate, newDate, evStatus), { once: true });
                    bootstrap.Modal.getOrCreateInstance(treatmentModal).hide();
                })
                .catch(() => { dateInput.value = oldDate; moveError(); });
        };

        const backBtn = document.getElementById('detail-back');
        backBtn.classList.toggle('d-none', !fromDay);
        backBtn.onclick = () => openDay(fromDay, true);

        // Resetear estado del modal
        const statusContainer = document.getElementById('status-container');
        statusContainer.className = 'bg-light rounded p-2 h-100';
        document.getElementById('detail-status').textContent = '—';
        document.getElementById('detail-type').textContent = '—';
        document.getElementById('detail-field').textContent = '—';
        document.getElementById('detail-field-info').textContent = '';
        document.getElementById('detail-machine').textContent = '—';
        document.getElementById('detail-machine-info').textContent = '';
        document.getElementById('detail-water').textContent = '—';
        waterWrap?.classList.remove('d-none');
        machineWrap?.classList.remove('d-none');
        document.getElementById('detail-products-list').innerHTML =
            '<div class="text-center text-muted small py-3"><i class="fa fa-spinner fa-spin me-1"></i>Cargando...</div>';

        showPane(paneDetail, fromDay ? 'forward' : null);
        const modal = ensureModalOpen();

        fetch(API_URLS.treatmentDetail(treatmentId))
            .then(response => {
                if (response.status === 401) { window.location.reload(); throw new Error('Sesión caducada'); }
                if (!response.ok) throw new Error('Error al cargar los detalles');
                return response.json();
            })
            .then(data => {
                document.getElementById('detail-meta').textContent = `${formatDate(event.start)} · ${data.field_name}`;

                document.getElementById('detail-status').textContent = data.status_display;
                const statusColors = { pending: 'warning', delayed: 'danger', completed: 'success' };
                statusContainer.className = `bg-${statusColors[data.status] || 'secondary'} bg-opacity-10 rounded p-2 h-100`;

                document.getElementById('detail-type').textContent = data.type_display;
                const isFertigation = data.type === 'fertigation';

                document.getElementById('detail-field').textContent = data.field_name;
                const fieldParts = [];
                if (data.field_crop) fieldParts.push(data.field_crop);
                if (data.field_area) fieldParts.push(`${formatNumber(data.field_area, 2)} ha`);
                document.getElementById('detail-field-info').textContent = fieldParts.join(' · ');

                document.getElementById('detail-machine').textContent = data.machine_name || 'No asignada';
                const machineParts = [];
                if (data.machine_capacity) machineParts.push(`${formatNumber(data.machine_capacity, 0)} litros`);
                if (data.loads) {
                    const l = data.loads;
                    machineParts.push(`${l.full_loads} cuba${l.full_loads === 1 ? '' : 's'}${l.partial_load ? ` + ${formatNumber(l.partial_water, 0)} L` : ''}`);
                }
                document.getElementById('detail-machine-info').textContent = machineParts.join(' · ');

                if (isFertigation) {
                    waterWrap?.classList.add('d-none');
                    machineWrap?.classList.add('d-none');
                } else {
                    updateWaterDisplay(data.water_per_ha, data.real_water_per_ha);
                }

                fillProducts(data.products, data.loads);

                if (data.can_finish) {
                    finishBtn.classList.remove('d-none');
                    finishBtn.onclick = () => {
                        treatmentModal.addEventListener('hidden.bs.modal', () => finishTreatment(data), { once: true });
                        modal.hide();
                    };
                }
            })
            .catch(error => {
                console.error('Error:', error);
                document.getElementById('detail-products-list').innerHTML =
                    '<div class="text-center text-danger small py-3"><i class="fa fa-circle-exclamation me-1"></i>Error al cargar los datos</div>';
            });
    }

    // ── Finalizar desde el calendario ─────────────────────────────────────
    function finishTreatment(data) {
        const isFertigation = data.type === 'fertigation';
        const area = Number(data.field_area) || 0;
        const waterPerHa = Math.round(Number(data.real_water_per_ha || data.water_per_ha) || 0);
        const today = toDateStr(new Date());

        Swal.fire({
            title: 'Finalizar tratamiento',
            heightAuto: false,
            html: `
              <form class="text-start" onsubmit="return false">
                <div class="mb-3">
                  <label class="form-label" for="cal-finish-date">Fecha de finalización</label>
                  <input type="date" class="form-control" id="cal-finish-date" value="${today}" required>
                </div>
                ${isFertigation ? '' : `
                <div class="mb-1">
                  <label class="form-label" for="cal-finish-water">Mojado final (litros/ha)</label>
                  <input type="number" class="form-control" id="cal-finish-water" value="${waterPerHa}" min="1" step="1" required>
                  <div class="form-text" id="cal-finish-total">Total: ${formatNumber(waterPerHa * area, 0)} L</div>
                </div>`}
              </form>`,
            showCancelButton: true,
            confirmButtonText: 'Finalizar',
            cancelButtonText: 'Cancelar',
            confirmButtonColor: '#198754',
            didOpen: () => {
                document.getElementById('cal-finish-water')?.addEventListener('input', (e) => {
                    document.getElementById('cal-finish-total').textContent = `Total: ${formatNumber(Math.round(e.target.value) * area, 0)} L`;
                });
            },
            preConfirm: () => {
                const finishDate = document.getElementById('cal-finish-date').value;
                if (!finishDate) { Swal.showValidationMessage('Indica la fecha de finalización'); return false; }
                if (isFertigation) return { finishDate, water: null };
                const water = Number(document.getElementById('cal-finish-water').value);
                if (!Number.isInteger(water) || water < 1) {
                    Swal.showValidationMessage('El mojado final debe ser un número entero mayor que 0');
                    return false;
                }
                return { finishDate, water };
            },
        }).then(result => {
            if (!result.isConfirmed) return;
            const body = new URLSearchParams({ finish_date: result.value.finishDate });
            if (result.value.water) body.append('real_water_used', result.value.water);
            fetch(API_URLS.treatmentFinish(data.id), { method: 'POST', headers: csrfHeaders(), body })
                .then(r => { if (!r.ok) throw new Error(); return r.json(); })
                .then(() => {
                    refetchAll();
                    Swal.fire({ toast: true, position: 'bottom', icon: 'success', title: 'Tratamiento finalizado', showConfirmButton: false, timer: 3000, heightAuto: false });
                })
                .catch(() => Swal.fire({ icon: 'error', title: 'Error', text: 'Hubo un problema. Verifica los datos e inténtalo de nuevo.', heightAuto: false }));
        });
    }

    // ── Formato ───────────────────────────────────────────────────────────
    function formatNumber(value, decimals = 2) {
        const parsed = Number(value);
        const safe = Number.isFinite(parsed) ? parsed : 0;
        return safe.toLocaleString('es-ES', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
    }

    function formatDose(value) {
        const parsed = Number(value);
        if (!Number.isFinite(parsed)) return value ?? '0,00';
        return formatNumber(parsed, 2);
    }

    function updateWaterDisplay(estimatedWater, realWater) {
        const waterElement = document.getElementById('detail-water');
        const estimated = Number(estimatedWater);
        const real = Number(realWater);
        const hasEstimated = Number.isFinite(estimated);
        const hasReal = Number.isFinite(real);

        if (hasReal && hasEstimated && real !== estimated) {
            waterElement.innerHTML = `<del class="info-subvalue">${formatNumber(estimated, 0)} L/ha</del><br>${formatNumber(real, 0)} L/ha`;
        } else {
            const selectedValue = hasEstimated ? estimated : (hasReal ? real : 0);
            waterElement.textContent = `${formatNumber(selectedValue, 0)} L/ha`;
        }
    }

    // Productos con dosis, total y, en pulverización, cantidad por cuba llena y por la última
    function fillProducts(products, loads) {
        const container = document.getElementById('detail-products-list');
        if (!products?.length) {
            container.innerHTML = '<div class="text-center text-muted small py-2">Sin productos asignados</div>';
            return;
        }
        container.innerHTML = products.map(p => {
            const perLoad = p.dose_per_load != null
                ? `<div class="small text-muted">Por cuba: <b>${formatDose(p.dose_per_load)} ${esc(p.total_dose_unit)}</b>${
                    loads?.partial_load && p.dose_partial_load != null
                        ? ` · última (${formatNumber(loads.partial_water, 0)} L): <b>${formatDose(p.dose_partial_load)} ${esc(p.total_dose_unit)}</b>` : ''}</div>`
                : '';
            return `
            <div class="d-flex align-items-center gap-2 px-2 py-2 bg-light rounded">
                <div class="flex-grow-1 min-w-0">
                    <div class="fw-semibold small text-truncate">${esc(p.name)}</div>
                    ${perLoad}
                </div>
                <div class="text-end flex-shrink-0">
                    <div class="small fw-semibold">${formatDose(p.dose)} <span class="fw-normal text-muted">${esc(p.dose_type_display)}</span></div>
                    <div class="small text-muted">${formatDose(p.total_dose)} ${esc(p.total_dose_unit)} total</div>
                </div>
            </div>`;
        }).join('');
    }

    function formatDate(date) {
        return new Intl.DateTimeFormat('es-ES', { day: '2-digit', month: '2-digit', year: 'numeric' }).format(date);
    }

    // ── Móvil (<768 px): tira semanal / mes en puntos + agenda del día ─────
    let mobileReady = false;
    let mSeq = 0;
    const M = {
        view: ['week', 'month'].includes(saved.mview) ? saved.mview : 'month',
        cursor: new Date(), selected: toDateStr(new Date()),
        events: [], overdue: [], showOverdue: false,
    };
    const $ = (id) => document.getElementById(id);
    const addDays = (d, n) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
    const startOfWeek = (d) => addDays(d, -((d.getDay() + 6) % 7)); // semana de lunes a domingo
    const fromStr = (str) => new Date(`${str}T00:00:00`);
    const mapEvent = (t) => ({ id: t.id, title: t.name, start: fromStr(t.date), startStr: t.date, extendedProps: t });
    const fmt = (opts, d) => new Intl.DateTimeFormat('es-ES', opts).format(d);
    const cap = (str) => str.charAt(0).toUpperCase() + str.slice(1);
    const mToast = (icon, title) => Swal.fire({ toast: true, position: 'bottom', icon, title, showConfirmButton: false, timer: 3000, heightAuto: false });

    // Rango visible [inicio, fin): una semana, o las semanas completas que cubren el mes
    function mRange() {
        if (M.view === 'week') { const s = startOfWeek(M.cursor); return [s, addDays(s, 7)]; }
        const first = new Date(M.cursor.getFullYear(), M.cursor.getMonth(), 1);
        const last = new Date(M.cursor.getFullYear(), M.cursor.getMonth() + 1, 0);
        return [startOfWeek(first), addDays(startOfWeek(last), 7)];
    }
    const rangeKey = () => mRange().map(toDateStr).join();

    function mLoad() {
        const [s, e] = mRange();
        const seq = ++mSeq; // descarta respuestas antiguas si el usuario navega rápido
        loadTreatments(toDateStr(s), toDateStr(e))
            .then(data => { if (seq === mSeq) { M.events = data.map(mapEvent); mRender(); } })
            .catch(err => console.error('Error cargando eventos:', err));

        // Atrasados: de todo el último año, sea cual sea el rango visible (respeta parcelas y tipos)
        const delayedOn = statusCheckboxes.find(cb => cb.value === 'delayed')?.checked;
        if (!delayedOn) { M.overdue = []; mRender(); return; }
        loadTreatments(toDateStr(addDays(new Date(), -365)), toDateStr(new Date()), 'delayed')
            .then(data => { M.overdue = data.map(mapEvent).sort((a, b) => a.startStr.localeCompare(b.startStr)); mRender(); })
            .catch(err => console.error('Error cargando atrasados:', err));
    }

    // Ir a una fecha: recarga solo si cambia el rango visible
    function mGo(date) {
        const before = rangeKey();
        M.cursor = date;
        M.selected = toDateStr(date);
        M.showOverdue = false;
        if (rangeKey() !== before) mLoad(); else mRender();
    }

    function mRender() {
        const [s, e] = mRange();
        const todayStr = toDateStr(new Date());
        const byDay = {};
        M.events.forEach(ev => (byDay[ev.startStr] = byDay[ev.startStr] || []).push(ev));

        $('cm-title').textContent = M.view === 'week'
            ? `${fmt({ day: 'numeric', month: 'short' }, s)} – ${fmt({ day: 'numeric', month: 'short' }, addDays(e, -1))}`
            : cap(fmt({ month: 'long', year: 'numeric' }, M.cursor));
        document.querySelectorAll('[data-cm-view]').forEach(b => b.classList.toggle('active', b.dataset.cmView === M.view));

        let html = ['L', 'M', 'X', 'J', 'V', 'S', 'D'].map(d => `<div class="cm-wd">${d}</div>`).join('');
        for (let d = s; d < e; d = addDays(d, 1)) {
            const str = toDateStr(d);
            const evs = byDay[str] || [];
            const dots = evs.slice(0, 3).map(ev =>
                `<i class="cm-dot" style="background:${(STATUS_STYLE[ev.extendedProps.status] || STATUS_STYLE.pending).bg}"></i>`).join('');
            const out = M.view === 'month' && d.getMonth() !== M.cursor.getMonth();
            html += `<button type="button" class="cm-day${out ? ' cm-out' : ''}${str === M.selected && !M.showOverdue ? ' cm-sel' : ''}${str === todayStr ? ' cm-today' : ''}" data-date="${str}"
                        aria-label="${esc(fmt({ weekday: 'long', day: 'numeric', month: 'long' }, d))}, ${evs.length} tratamientos">
                        <span class="cm-num">${d.getDate()}</span><span class="cm-dots">${dots}</span>${evs.length > 3 ? `<small class="cm-more">+${evs.length - 3}</small>` : ''}</button>`;
        }
        const grid = $('cm-grid');
        grid.className = `cm-grid cm-${M.view}`;
        grid.innerHTML = html;

        // Banner de atrasados
        const banner = $('cm-overdue');
        banner.classList.toggle('d-none', M.overdue.length === 0);
        banner.innerHTML = `<i class="fa fa-triangle-exclamation me-1"></i><b>${M.overdue.length}</b> atrasado${M.overdue.length === 1 ? '' : 's'}
            <span class="float-end small">${M.showOverdue ? 'Ocultar' : 'Ver'}</span>`;

        mRenderAgenda();
    }

    function mRenderAgenda() {
        const list = M.showOverdue ? M.overdue : M.events.filter(ev => ev.startStr === M.selected);
        $('cm-agenda-title').textContent = M.showOverdue ? `Atrasados (${list.length})`
            : cap(fmt({ weekday: 'long', day: 'numeric', month: 'long' }, fromStr(M.selected)));
        $('cm-new').href = `${API_URLS.treatmentCreate}?date=${M.selected}`;
        $('cm-agenda').innerHTML = list.length ? list.map(ev => {
            const t = ev.extendedProps;
            const style = STATUS_STYLE[t.status] || STATUS_STYLE.pending;
            return `<div class="d-flex align-items-center gap-2 bg-white rounded shadow-sm p-2">
                <span class="cm-bar" style="background:${style.bg}"></span>
                <button type="button" class="btn p-0 border-0 text-start flex-grow-1 min-w-0" data-open="${ev.id}">
                    <span class="d-block fw-semibold small text-truncate"><i class="fa fa-${TYPE_ICON[t.type] || 'flask'} me-1 text-muted"></i>${esc(ev.title)}</span>
                    <span class="d-block small text-muted text-truncate">${M.showOverdue ? `${esc(formatDate(ev.start))} · ` : ''}${esc(t.field_name)} · ${esc(t.type_display)}</span>
                </button>
                ${t.status === 'completed' ? '<i class="fa fa-circle-check text-success px-2"></i>'
                    : `<button type="button" class="btn btn-outline-success btn-sm" data-finish="${ev.id}" aria-label="Finalizar"><i class="fa fa-check"></i></button>`}
            </div>`;
        }).join('') : '<div class="text-center text-muted small py-4">No hay tratamientos este día</div>';
    }

    // ✓ rápido: carga el detalle (dosis, mojado por defecto…) y abre el formulario de finalizar
    function quickFinish(id) {
        fetch(API_URLS.treatmentDetail(id))
            .then(r => {
                if (r.status === 401) { window.location.reload(); throw new Error('Sesión caducada'); }
                if (!r.ok) throw new Error();
                return r.json();
            })
            .then(data => data.can_finish ? finishTreatment(data) : mToast('info', 'Este tratamiento ya está finalizado'))
            .catch(() => mToast('error', 'No se pudo cargar el tratamiento'));
    }

    function initMobile() {
        mobileReady = true;
        $('cm-prev').onclick = () => mGo(M.view === 'week' ? addDays(M.cursor, -7) : new Date(M.cursor.getFullYear(), M.cursor.getMonth() - 1, 1));
        $('cm-next').onclick = () => mGo(M.view === 'week' ? addDays(M.cursor, 7) : new Date(M.cursor.getFullYear(), M.cursor.getMonth() + 1, 1));
        $('cm-today').onclick = () => mGo(new Date());
        document.querySelectorAll('[data-cm-view]').forEach(b => b.onclick = () => {
            M.view = b.dataset.cmView;
            store.set({ mview: M.view });
            M.cursor = fromStr(M.selected); // el mes/semana mostrados son los del día seleccionado
            mLoad(); mRender();
        });
        $('cm-overdue').onclick = () => { M.showOverdue = !M.showOverdue; mRender(); };
        $('cm-grid').onclick = (e) => {
            const day = e.target.closest('[data-date]');
            if (day) mGo(fromStr(day.dataset.date));
        };
        $('cm-agenda').onclick = (e) => {
            const fin = e.target.closest('[data-finish]');
            if (fin) return quickFinish(fin.dataset.finish);
            const open = e.target.closest('[data-open]');
            if (open) {
                const ev = [...M.events, ...M.overdue].find(x => String(x.id) === open.dataset.open);
                if (ev) loadTreatmentDetail(ev);
            }
        };
        // Deslizar a izquierda/derecha sobre la tira cambia de semana/mes
        let touchX = null;
        $('cm-grid').addEventListener('touchstart', (e) => { touchX = e.touches[0].clientX; }, { passive: true });
        $('cm-grid').addEventListener('touchend', (e) => {
            if (touchX === null) return;
            const dx = e.changedTouches[0].clientX - touchX;
            touchX = null;
            if (Math.abs(dx) > 60) $(dx < 0 ? 'cm-next' : 'cm-prev').click();
        }, { passive: true });
        mLoad();
    }

    // ── Modo según el ancho ───────────────────────────────────────────────
    let lastMobile = null;
    function applyMode() {
        const mobile = isMobile();
        if (mobile === lastMobile) return;
        lastMobile = mobile;
        if (mobile) {
            if (!mobileReady) initMobile(); else mLoad();
        } else if (!calendar) {
            initDesktop();
        } else {
            calendar.updateSize();
            calendar.refetchEvents();
        }
    }
    applyMode();

    let resizeTimer;
    window.addEventListener('resize', () => {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(applyMode, 150);
    });

    document.addEventListener('sidebar-toggled', () => {
        setTimeout(() => calendar?.updateSize(), 300);
    });
});
