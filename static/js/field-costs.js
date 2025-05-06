document.addEventListener('DOMContentLoaded', function() {
    // Referencias a elementos del DOM
    const dateFromInput = document.getElementById('dateFrom');
    const dateToInput = document.getElementById('dateTo');
    const applyFilterBtn = document.getElementById('applyDateFilter');
    const fieldsContainer = document.getElementById('fieldsContainer');
    const fieldsInput = document.getElementById('fieldSelector');
    const viewModeSelector = document.getElementById('viewMode');

    // Inicializar fechas (último año por defecto)
    const today = new Date();
    const lastYear = new Date();
    lastYear.setFullYear(today.getFullYear() - 1);

    dateToInput.valueAsDate = today;
    dateFromInput.valueAsDate = lastYear;

    // Inicializar modo de vista desde localStorage
    let currentViewMode = localStorage.getItem('fieldCostsViewMode') || 'cost';
    viewModeSelector.value = currentViewMode;

    // Charts
    let productTypeChart = null;
    let fieldCostChart = null;

    // Variable para almacenar los datos cargados
    let currentData = null;

    // Cargar datos al inicio
    loadFieldCostsData();

    // Event listeners
    applyFilterBtn.addEventListener('click', loadFieldCostsData);

    // Cambiar modo de visualización sin recargar datos
    viewModeSelector.addEventListener('change', function() {
        currentViewMode = this.value;
        localStorage.setItem('fieldCostsViewMode', currentViewMode);

        // Actualizar la visualización con los datos existentes
        if (currentData) {
            renderFieldCards(currentData.fields);
            updateCharts(currentData);
        }
    });

    // Función para cargar datos vía AJAX
    function loadFieldCostsData() {
        const dateFrom = dateFromInput.value;
        const dateTo = dateToInput.value;
        const fieldsList = Array.from(fieldsInput.selectedOptions).map(opt => opt.value);

        // Construir parámetros
        const params = new URLSearchParams();
        if (dateFrom) params.append('date_from', dateFrom);
        if (dateTo) params.append('date_to', dateTo);
        fieldsList.forEach(id => params.append('field_ids', id));

        // Mostrar spinner
        fieldsContainer.innerHTML = `
            <div class="text-center py-5">
                <div class="spinner-border text-primary" role="status">
                    <span class="visually-hidden">Cargando...</span>
                </div>
                <p class="mt-2">Cargando datos de parcelas...</p>
            </div>
        `;

        // Hacer petición AJAX
        fetch(`${API_URLS.fieldCosts}?${params.toString()}`)
            .then(response => response.json())
            .then(data => {
                // Guardar datos para uso posterior
                currentData = data;

                updateDashboard(data);
                renderFieldCards(data.fields);
                updateCharts(data);
            })
            .catch(error => {
                console.error('Error cargando datos:', error);
                fieldsContainer.innerHTML = `
                    <div class="col-12">
                        <div class="alert alert-danger">
                            Error al cargar los datos. Por favor, inténtalo de nuevo.
                        </div>
                    </div>
                `;
            });
    }

    // Actualizar indicadores del dashboard
    function updateDashboard(data) {
        document.getElementById('totalCost').textContent = data.total_cost.toLocaleString('es-ES', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        }) + ' €';

        document.getElementById('costPerHa').textContent = data.cost_per_ha.toLocaleString('es-ES', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        }) + ' €/ha';

        document.getElementById('totalArea').textContent = data.total_area.toLocaleString('es-ES', {
            minimumFractionDigits: 1,
            maximumFractionDigits: 1
        }) + ' ha';

        document.getElementById('fieldCount').textContent = data.fields.length;
    }

    // Renderizar tarjetas de parcelas
    function renderFieldCards(fields) {
        fieldsContainer.innerHTML = '';

        // Ordenar campos por coste por hectárea
        fields.sort((a, b) => b.cost_per_ha - a.cost_per_ha);

        fields.forEach(field => {
            // Generar un color para la barra de progreso
            const progressColor = getProgressColor(field.cost_per_ha, fields);

            const card = document.createElement('div');
            card.className = 'col-lg-4 col-md-6 mb-4';
            card.innerHTML = `
                <div class="card h-100">
                    <div class="card-body">
                        <div class="d-flex justify-content-between align-items-center mb-3">
                            <h5 class="card-title mb-0">${field.name}</h5>
                            <span class="badge bg-${progressColor}">${field.cost_per_ha.toLocaleString('es-ES', {
                                minimumFractionDigits: 2,
                                maximumFractionDigits: 2
                            })} €/ha</span>
                        </div>
                        <div class="card-text mb-3">
                            <div class="row g-2 mb-2">
                                <div class="col-6">
                                    <div class="d-flex align-items-center">
                                        <i class="fa fa-ruler-combined me-2 text-muted"></i>
                                        <span>${field.area} ha</span>
                                    </div>
                                </div>
                                <div class="col-6">
                                    <div class="d-flex align-items-center">
                                        <i class="fa fa-euro-sign me-2 text-muted"></i>
                                        <span>${field.total_cost.toLocaleString('es-ES', {
                                            minimumFractionDigits: 2,
                                            maximumFractionDigits: 2
                                        })} €</span>
                                    </div>
                                </div>
                            </div>

                            <!-- Visualización gráfica de costes -->
                            <div class="mt-3">
                                <h6 class="text-muted mb-2">Desglose por tipo de producto:</h6>
                                <div class="product-type-breakdown">
                                    ${renderFieldProductBreakdown(field.product_breakdown)}
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            `;

            fieldsContainer.appendChild(card);
        });
    }

    function renderFieldProductBreakdown(productBreakdown) {
        if (!productBreakdown || productBreakdown.length === 0) {
            return '<div class="text-muted small">No hay datos disponibles</div>';
        }

        const colors = [
            'primary', 'success', 'danger', 'warning',
            'info', 'secondary', 'dark'
        ];

        let html = '<div class="product-type-bars">';

        productBreakdown.forEach((type, index) => {
            const color = colors[index % colors.length];
            const uniqueId = `products-${type.type_name.replace(/\s+/g, '-')}-${index}-${Math.random().toString(36).substr(2, 5)}`;

            let valueDisplay = '';
            if (currentViewMode === 'cost') {
                valueDisplay = type.total.toLocaleString('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' €';
            } else {
                const totalQuantity = type.products.reduce((sum, p) => sum + p.quantity, 0);
                const unit = type.products[0]?.unit || '';
                valueDisplay = `${totalQuantity.toLocaleString('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${unit}`;
            }

            html += `
                <div class="product-type-item mb-2">
                    <div class="d-flex justify-content-between mb-1 small">
                        <span>${type.type_name}</span>
                        <span>${valueDisplay} (${type.percentage.toFixed(1)}%)</span>
                    </div>
                    <div class="progress" style="height: 8px;">
                        <div class="progress-bar bg-${color}" role="progressbar"
                             style="width: ${type.percentage}%" aria-valuenow="${type.percentage}"
                             aria-valuemin="0" aria-valuemax="100"></div>
                    </div>
                    <div class="mt-1">
                        <button class="btn btn-link btn-sm p-0 text-${color} product-details-toggle"
                                data-bs-toggle="collapse"
                                data-bs-target="#${uniqueId}">
                            Ver productos <i class="fas fa-chevron-down fa-xs"></i>
                        </button>
                        <div class="collapse mt-2" id="${uniqueId}">
                            <div class="card card-body p-2 bg-light">
                                ${renderProductList(type.products, currentViewMode)}
                            </div>
                        </div>
                    </div>
                </div>
            `;
        });

        html += '</div>';
        return html;
    }

    function renderProductList(products, viewMode = 'cost') {
        if (!products || products.length === 0) {
            return '<div class="text-muted small">No hay productos disponibles</div>';
        }

        let html = '<ul class="list-unstyled mb-0 small">';

        products.forEach(product => {
            // Determinar qué valor mostrar según el modo
            let valueDisplay;
            if (viewMode === 'cost') {
                valueDisplay = `${product.total.toLocaleString('es-ES', {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2
                })} €`;
            } else {
                valueDisplay = `${product.quantity.toLocaleString('es-ES', {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2
                })} ${product.unit || ''}`;
            }

            html += `
                <li class="d-flex justify-content-between align-items-center mb-1">
                    <span>${product.name}</span>
                    <span>${valueDisplay} (${product.percentage.toFixed(1)}%)</span>
                </li>
            `;
        });

        html += '</ul>';
        return html;
    }

    // Obtener color según el coste
    function getProgressColor(cost, fields) {
        // Encontrar máximo y mínimo para normalizar
        if (fields.length <= 1) return 'primary';

        const costs = fields.map(f => f.cost_per_ha);
        const max = Math.max(...costs);
        const min = Math.min(...costs);
        const range = max - min;

        // Normalizar coste actual (0-1)
        const normalized = range === 0 ? 0.5 : (cost - min) / range;

        // Asignar color según valor normalizado
        if (normalized > 0.8) return 'danger';
        if (normalized > 0.6) return 'warning';
        if (normalized > 0.4) return 'primary';
        if (normalized > 0.2) return 'info';
        return 'success';
    }

    // Actualizar gráficos
    function updateCharts(data) {
        // Preparar datos para gráficos
        const productTypeData = prepareProductTypeChartData(data.product_breakdown);
        const fieldCostData = prepareFieldCostChartData(data.fields);

        // Actualizar/crear gráfico de tipos de producto
        if (productTypeChart) {
            productTypeChart.data = productTypeData;
            productTypeChart.update();
        } else {
            const ctx = document.getElementById('productTypeChart').getContext('2d');
            productTypeChart = new Chart(ctx, {
                type: 'doughnut',
                data: productTypeData,
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            position: 'right',
                            labels: {
                                boxWidth: 12
                            }
                        },
                        tooltip: {
                            callbacks: {
                                label: function(context) {
                                    const label = context.label;
                                    const value = context.raw;
                                    const unit = context.dataset.units?.[context.dataIndex] || '';
                                    const formattedValue = value.toLocaleString('es-ES', {
                                        minimumFractionDigits: 2,
                                        maximumFractionDigits: 2
                                    });

                                    return currentViewMode === 'cost'
                                        ? `${label}: ${formattedValue} €`
                                        : `${label}: ${formattedValue} ${unit}`;
                                }
                            }
                        }
                    }
                }
            });
        }

        // Actualizar/crear gráfico de costes por parcela
        if (fieldCostChart) {
            fieldCostChart.data = fieldCostData;
            fieldCostChart.update();
        } else {
            const ctx = document.getElementById('fieldCostChart').getContext('2d');
            fieldCostChart = new Chart(ctx, {
                type: 'bar',
                data: fieldCostData,
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    indexAxis: 'y',
                    plugins: {
                        legend: {
                            position: 'top'
                        }
                    },
                    scales: {
                        x: {
                            grid: {
                                display: false
                            }
                        }
                    }
                }
            });
        }

        // Actualizar la sección de detalles de productos
        updateProductTypeDetails(data.product_breakdown);
    }

    // Función para actualizar el desglose detallado de productos
    function updateProductTypeDetails(productBreakdown) {
        const container = document.getElementById('productTypeDetails');
        if (!container) return;

        if (!productBreakdown || productBreakdown.length === 0) {
            container.innerHTML = '<div class="alert alert-info">No hay datos disponibles para el período seleccionado.</div>';
            return;
        }

        const colors = [
            'primary', 'success', 'danger', 'warning',
            'info', 'secondary', 'dark'
        ];

        let html = '';

        productBreakdown.forEach((type, index) => {
            const color = colors[index % colors.length];
            const uniqueId = `details-${type.type_name.replace(/\s+/g, '-')}-${index}`;

            // Determinar qué valor mostrar según el modo
            let valueDisplay = type.total.toLocaleString('es-ES', {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2
            }) + ' €';

            html += `
                <div class="product-type-section mb-4 col-12 col-md-4">
                    <div class="product-type-header d-flex justify-content-between align-items-center">
                        <h6 class="mb-0 text-${color}">
                            <i class="fas fa-box me-2"></i> ${type.type_name}
                        </h6>
                        <div>
                            <span class="badge bg-${color} me-2">${valueDisplay}</span>
                            <span class="badge bg-light text-dark">${type.percentage.toFixed(1)}%</span>
                        </div>
                    </div>

                    <div class="progress mt-2 mb-3" style="height: 10px;">
                        <div class="progress-bar bg-${color}" role="progressbar"
                             style="width: ${type.percentage}%" aria-valuenow="${type.percentage}"
                             aria-valuemin="0" aria-valuemax="100"></div>
                    </div>

                    <div class="product-items px-2">
                        ${type.products.map(product => {
                            // Determinar qué valor mostrar según el modo
                            let productValueDisplay;
                            if (currentViewMode === 'cost') {
                                productValueDisplay = `${product.total.toLocaleString('es-ES', {
                                    minimumFractionDigits: 2,
                                    maximumFractionDigits: 2
                                })} €`;
                            } else {
                                productValueDisplay = `${product.quantity.toLocaleString('es-ES', {
                                    minimumFractionDigits: 2,
                                    maximumFractionDigits: 2
                                })} ${product.unit || ''}`;
                            }

                            return `
                                <div class="product-item d-flex justify-content-between align-items-center">
                                    <span>${product.name}</span>
                                    <div>
                                        <span class="me-2">${productValueDisplay}</span>
                                        <span class="text-muted small">(${product.percentage.toFixed(1)}%)</span>
                                    </div>
                                </div>
                            `;
                        }).join('')}
                    </div>
                </div>
            `;
        });

        container.innerHTML = html;
    }

    // Preparar datos para gráfico de tipos de producto
    function prepareProductTypeChartData(productBreakdown) {
        const labels = productBreakdown.map(item => item.type_name);
        let values, units;

        if (currentViewMode === 'cost') {
            values = productBreakdown.map(item => item.total);
            units = productBreakdown.map(() => '€');
        } else {
            values = productBreakdown.map(item => {
                // Si estamos en modo cantidad, sumamos las cantidades de los productos
                return item.products.reduce((sum, product) => sum + product.quantity, 0);
            });
            units = productBreakdown.map(p => {
                const firstProduct = p.products && p.products[0];
                return firstProduct ? firstProduct.unit : '';
            });
        }

        // Generar colores para cada tipo
        const backgroundColors = [
            '#4e73df', '#1cc88a', '#36b9cc', '#f6c23e',
            '#e74a3b', '#858796', '#5a5c69', '#6610f2',
            '#fd7e14', '#20c997', '#e83e8c', '#17a2b8'
        ];

        return {
            labels: labels,
            datasets: [{
                data: values,
                backgroundColor: backgroundColors.slice(0, labels.length),
                hoverBackgroundColor: backgroundColors.slice(0, labels.length).map(c => lightenDarkenColor(c, -20)),
                borderWidth: 1,
                units
            }]
        };
    }

    // Preparar datos para gráfico de costes por parcela
    function prepareFieldCostChartData(fields) {
        // Tomar sólo las 8 parcelas con mayor coste por hectárea
        const sortedFields = [...fields].sort((a, b) => b.cost_per_ha - a.cost_per_ha).slice(0, 8);

        const labels = sortedFields.map(f => f.name);
        const totalCosts = sortedFields.map(f => parseFloat(f.total_cost));
        const costsPerHa = sortedFields.map(f => parseFloat(f.cost_per_ha));

        return {
            labels: labels,
            datasets: [
                {
                    label: 'Coste total (€)',
                    data: totalCosts,
                    backgroundColor: '#4e73df',
                    borderColor: '#4e73df',
                    borderWidth: 1
                },
                {
                    label: 'Coste por ha (€/ha)',
                    data: costsPerHa,
                    backgroundColor: '#1cc88a',
                    borderColor: '#1cc88a',
                    borderWidth: 1
                }
            ]
        };
    }

    // Utilidad para aclarar/oscurecer colores
    function lightenDarkenColor(col, amt) {
        let usePound = false;
        if (col[0] == "#") {
            col = col.slice(1);
            usePound = true;
        }

        let num = parseInt(col, 16);
        let r = (num >> 16) & 255;
        let g = (num >> 8) & 255;
        let b = num & 255;

        r = clamp(r + amt);
        g = clamp(g + amt);
        b = clamp(b + amt);

        return (usePound ? "#" : "") + ((r << 16) | (g << 8) | b).toString(16).padStart(6, '0');
    }

    function clamp(num) {
        return Math.min(Math.max(num, 0), 255);
    }
});
