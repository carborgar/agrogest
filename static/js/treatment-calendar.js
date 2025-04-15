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
        eventClick: (info) => loadTaskDetail(info.event),
        eventTimeFormat: { hour: '2-digit', minute: '2-digit', hour12: false }
    });

    calendar.render();

    // Manejo de filtros
    const filterAll = document.getElementById('filter-all');
    const fieldCheckboxes = document.querySelectorAll('.field-checkbox');
    const typeCheckboxes = document.querySelectorAll('.task-type-checkbox');

    function updateFilters() {
        const anyChecked = [...fieldCheckboxes].some(cb => cb.checked);
        filterAll.checked = !anyChecked;
        filterAll.closest('.field-filter').classList.toggle('active', !anyChecked);
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
            types: [...document.querySelectorAll('.task-type-checkbox:checked')].map(cb => cb.value).join(',')
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

    function formatEvent(task) {
        return {
            id: task.id,
            title: task.name,
            start: task.date,
            end: task.date,
            className: getStatusClass(task.status),
            extendedProps: task
        };
    }

    function getStatusClass(status) {
        return {
            completed: 'task-completed',
            delayed: 'task-delayed'
        }[status] || 'task-pending';
    }

    // Carga de detalles bajo demanda
    function loadTaskDetail(event) {
        const taskId = event.id;
        const taskTitle = event.title;
        const taskModal = document.getElementById("task-detail");

        // Mostrar información básica disponible inmediatamente
        document.querySelector('.task-title').textContent = taskTitle;
        document.getElementById('detail-date').textContent = formatDate(event.start);

        // Mostrar indicadores de carga para los datos que vendrán del endpoint
        document.getElementById('detail-field').textContent = 'Cargando...';
        document.getElementById('detail-type').textContent = 'Cargando...';
        document.getElementById('detail-status').textContent = 'Cargando...';
        document.getElementById('detail-machine').textContent = 'Cargando...';
        document.getElementById('detail-water').textContent = 'Cargando...';
        document.getElementById('detail-products').innerHTML = '<tr><td colspan="3" class="text-center">Cargando productos...</td></tr>';
        document.getElementById('view-task').href = `/tratamientos/${taskId}`;

        // Mostrar el modal inmediatamente mientras se cargan los datos
        new bootstrap.Modal(taskModal).show();

        // Cargar detalles completos desde el endpoint separado
        fetch(API_URLS.treatmentDetail(taskId))
            .then(response => {
                if (!response.ok) {
                    throw new Error('Error al cargar los detalles del tratamiento');
                }
                return response.json();
            })
            .then(taskData => {
                // Actualizar el modal con los datos recibidos
                document.getElementById('detail-field').textContent = taskData.field_name;
                document.getElementById('detail-type').textContent = taskData.type_display;
                document.getElementById('detail-status').textContent = taskData.status_display;
                document.getElementById('detail-machine').textContent = taskData.machine_name || 'No asignada';
                document.getElementById('detail-water').textContent = taskData.water_per_ha;
                fillProducts(taskData.products);
                document.getElementById('view-task').style.display = taskData.status === 'completed' ? 'none' : 'block';
            })
            .catch(error => {
                console.error('Error:', error);
                document.getElementById('detail-products').innerHTML =
                    '<tr><td colspan="3" class="text-center">Error al cargar los datos</td></tr>';
            });
    }

    function fillProducts(products) {
        const container = document.getElementById('detail-products');
        container.innerHTML = products?.length ? products.map(p =>
            `<tr>
                <td>${p.name}</td>
                <td>${p.dose} ${p.dose_type_display}</td>
                <td>${p.total_dose} ${p.total_dose_unit}</td>
            </tr>`
        ).join('') : `<tr><td colspan="3" class="text-center">No hay productos asignados</td></tr>`;
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
