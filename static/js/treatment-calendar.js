document.addEventListener('DOMContentLoaded', function () {
    // Inicializar calendario
    const calendarEl = document.getElementById('calendar');
    const calendar = new FullCalendar.Calendar(calendarEl, {
        themeSystem: 'bootstrap5',
        initialView: 'dayGridMonth',
        locale: 'es',
        headerToolbar: {
            left: 'prevYear,prev,next,nextYear today',
            center: 'title',
            right: 'dayGridMonth,listMonth'
        },
        buttonText: { today: 'Hoy', month: 'Mes', list: 'Lista' },
        events: fetchEvents,
        eventClick: (info) => loadTreatmentDetail(info.event),
        displayEventTime: false
    });

    calendar.render();

    // Manejo de filtros
    const filterAll = document.getElementById('filter-all');
    const fieldCheckboxes = document.querySelectorAll('.field-checkbox');
    const typeCheckboxes = document.querySelectorAll('.treatment-type-checkbox');

    function updateFilters() {
        const anyChecked = [...fieldCheckboxes].some(cb => cb.checked);
        filterAll.checked = !anyChecked;
        filterAll.closest('.field-filter-item')?.classList.toggle('active', !anyChecked);
        calendar.refetchEvents();
    }

    filterAll.addEventListener('change', () => {
        fieldCheckboxes.forEach(cb => cb.checked = false);
        updateFilters();
    });

    fieldCheckboxes.forEach(cb => cb.addEventListener('change', updateFilters));
    typeCheckboxes.forEach(cb => cb.addEventListener('change', () => calendar.refetchEvents()));

    // Obtener eventos AJAX (solo datos básicos sin productos)
    function fetchEvents(info, successCallback, failureCallback) {
        const params = new URLSearchParams({
            start: info.startStr.split('T')[0],
            end: info.endStr.split('T')[0],
            fields: [...document.querySelectorAll('.field-checkbox:checked')].map(cb => cb.value).join(','),
            types: [...document.querySelectorAll('.treatment-type-checkbox:checked')].map(cb => cb.value).join(',')
        });

        fetch(`${API_URLS.treatments}?${params.toString()}`)
            .then(response => response.json())
            .then(data => {
                successCallback(data.map(formatEvent));
            })
            .catch(error => {
                console.error('Error cargando eventos:', error);
                failureCallback(error);
            });
    }

    function formatEvent(treatment) {
        return {
            id: treatment.id,
            title: treatment.name,
            start: treatment.date,
            end: treatment.date,
            className: getStatusClass(treatment.status),
            extendedProps: treatment
        };
    }

    function getStatusClass(status) {
        return {
            completed: 'treatment-completed',
            delayed: 'treatment-delayed'
        }[status] || 'treatment-pending';
    }

    // Carga de detalles bajo demanda
    function loadTreatmentDetail(event) {
        const treatmentId = event.id;
        const treatmentModal = document.getElementById("treatment-detail");

        // Mostrar información básica inmediatamente
        document.querySelector('.treatment-title').textContent = event.title;
        document.getElementById('detail-meta').textContent = formatDate(event.start);
        document.getElementById('view-treatment').href = `/tratamientos/${treatmentId}`;

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
        document.getElementById('detail-products-list').innerHTML =
            '<div class="text-center text-muted small py-3"><i class="fa fa-spinner fa-spin me-1"></i>Cargando...</div>';

        new bootstrap.Modal(treatmentModal).show();

        fetch(API_URLS.treatmentDetail(treatmentId))
            .then(response => {
                if (!response.ok) throw new Error('Error al cargar los detalles');
                return response.json();
            })
            .then(data => {
                // Meta: fecha + parcela
                document.getElementById('detail-meta').textContent =
                    `${formatDate(event.start)} · ${data.field_name}`;

                // Estado con color
                document.getElementById('detail-status').textContent = data.status_display;
                const statusColors = { pending: 'warning', delayed: 'danger', completed: 'success' };
                const color = statusColors[data.status] || 'secondary';
                statusContainer.className = `bg-${color} bg-opacity-10 rounded p-2 h-100`;

                // Tipo
                document.getElementById('detail-type').textContent = data.type_display;

                // Parcela
                document.getElementById('detail-field').textContent = data.field_name;
                const fieldParts = [];
                if (data.field_crop) fieldParts.push(data.field_crop);
                if (data.field_area) fieldParts.push(`${data.field_area} ha`);
                document.getElementById('detail-field-info').textContent = fieldParts.join(' · ');

                // Maquinaria
                document.getElementById('detail-machine').textContent = data.machine_name || 'No asignada';
                if (data.machine_capacity) {
                    document.getElementById('detail-machine-info').textContent = `${data.machine_capacity} litros`;
                }

                // Mojado
                updateWaterDisplay(data.water_per_ha, data.real_water_per_ha);

                // Productos
                fillProducts(data.products);
            })
            .catch(error => {
                console.error('Error:', error);
                document.getElementById('detail-products-list').innerHTML =
                    '<div class="text-center text-danger small py-3"><i class="fa fa-circle-exclamation me-1"></i>Error al cargar los datos</div>';
            });
    }

    // Nueva función para actualizar la visualización del mojado
    function updateWaterDisplay(estimatedWater, realWater) {
        const waterElement = document.getElementById('detail-water');

        // Verificar si hay valores reales diferentes del estimado
        if (realWater && realWater !== estimatedWater) {
            // Mostrar el estimado tachado y el real abajo
            waterElement.innerHTML = `<del class="info-subvalue">${estimatedWater} L/ha</del><br>${realWater} L/ha`;
        } else {
            // Solo mostrar el valor estimado (o real si son iguales)
            waterElement.textContent = `${estimatedWater || realWater || '0'} L/ha`;
        }
    }

    function fillProducts(products) {
        const container = document.getElementById('detail-products-list');
        if (!products?.length) {
            container.innerHTML = '<div class="text-center text-muted small py-2">Sin productos asignados</div>';
            return;
        }
        container.innerHTML = products.map(p => `
            <div class="d-flex align-items-center gap-2 px-2 py-2 bg-light rounded">
                <div class="flex-grow-1 min-w-0">
                    <div class="fw-semibold small text-truncate">${p.name}</div>
                </div>
                <div class="text-end flex-shrink-0">
                    <div class="small fw-semibold">${p.dose} <span class="fw-normal text-muted">${p.dose_type_display}</span></div>
                    <div class="small text-muted">${p.total_dose} ${p.total_dose_unit} total</div>
                </div>
            </div>
        `).join('');
    }

    function formatDate(date) {
        return new Intl.DateTimeFormat('es-ES', { day: '2-digit', month: '2-digit', year: 'numeric' }).format(date);
    }

    // Manejo del collapse de filtros
    const filterCollapse = document.getElementById('filterCollapse');
    window.addEventListener('resize', () => {
        if (window.innerWidth >= 768) filterCollapse.classList.add('show');
    });

    document.addEventListener('sidebar-toggled', () => {
        setTimeout(() => {
            calendar.updateSize();
        }, 300);
    });
});
