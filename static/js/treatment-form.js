document.addEventListener('DOMContentLoaded', async () => {
    // Variables globales
    let fields = {}, machines = {}, products = {};
    const formContainer = document.getElementById('treatmentForm');
    let formCount = parseInt(formContainer.dataset.formCount);
    let lastModifiedField = new Map(); // Para trackear el último campo modificado por fila
    const maxForms = parseInt('{{ products_formset.max_num }}');

    // Elementos del formulario
    const elements = {
        fieldSelect: document.getElementById('{{ form.field.id_for_label }}'),
        treatmentTypeSelect: document.getElementById('{{ form.type.id_for_label }}'),
        machineSelect: document.getElementById('{{ form.machine.id_for_label }}'),
        waterPerHaInput: document.getElementById('{{ form.water_per_ha.id_for_label }}'),
        completedDateInput: document.getElementById('{{ form.finish_date.id_for_label }}'),
        fieldInfo: document.getElementById('fieldAreaInfo'),
        machineInfo: document.getElementById('machineCapacityInfo'),
        completedDateInfo: document.getElementById('completedDateInfo'),
        addProductBtn: document.getElementById('addProduct'),
        productsTable: document.getElementById('productsTable').querySelector('tbody'),
        totalFormsInput: document.getElementById('id_treatmentproduct_set-TOTAL_FORMS'),
        conditionalFields: document.getElementById('conditionalFields'),
        machineFieldGroup: document.getElementById('machineFieldGroup'),
        waterFieldGroup: document.getElementById('waterFieldGroup'),
        nameInput: document.getElementById('{{ form.name.id_for_label }}'),
        dateInput: document.getElementById('{{ form.date.id_for_label }}'),
        // Step elements
        step1: document.getElementById('step1'),
        step2: document.getElementById('step2'),
        nextToProducts: document.getElementById('nextToProducts'),
        backToInfo: document.getElementById('backToInfo'),
        progressBar: document.getElementById('progressBar')
    };

    // Funciones para cargar datos
    async function fetchData(url) {
        const response = await fetch(url);
        return response.json();
    }

    async function loadFieldsData() {
        fields = Object.fromEntries((await fetchData(API_URLS.fields)).map(field => [field.id, field]));
        updateFieldInfo();
    }

    async function loadMachinesData() {
        machines = Object.fromEntries((await fetchData(API_URLS.machines)).map(machine => [machine.id, machine]));
        updateMachineInfo();
    }

    async function loadProductsData(treatmentType = null) {
        if (!treatmentType) {
            products = {};
            return;
        }

        products = Object.fromEntries((await fetchData(API_URLS.productsByTreatmentType(treatmentType))).map(product => [product.id, product]));

        updateProductsTableOptions();
    }

    function populateProductSelects() {
        document.querySelectorAll('.product-select').forEach(productSelect => {
            const currentValue = productSelect.value;
            productSelect.innerHTML = '<option value="">Seleccione un producto</option>';
            Object.values(products).forEach(product => {
                const option = document.createElement('option');
                option.value = product.id;
                option.textContent = product.name;
                if (product.id.toString() === currentValue) option.selected = true;
                productSelect.appendChild(option);
            });
        });
    }

    function resetProductsTable() {
        document.querySelectorAll('.product-form:not(:first-child)').forEach(row => row.remove());
        const firstRow = document.querySelector('.product-form');
        if (firstRow) {
            firstRow.querySelector('.product-dose').value = '';
            firstRow.querySelector('.estimated-dose-input').value = '';
            firstRow.querySelector('.estimated-dose-unit').textContent = '-';
            firstRow.querySelector('#product-default-dose').value = '';
        }
        formCount = 1;
        elements.totalFormsInput.value = formCount;
        populateProductSelects();
    }

    function updateProductsTableOptions() {
        // Actualizar todos los selects de productos en la tabla
        document.querySelectorAll('.product-select').forEach(productSelect => {
            const currentValue = productSelect.value;

            // Guardar la opción seleccionada actualmente
            const selectedOption = productSelect.options[productSelect.selectedIndex];
            const selectedText = selectedOption ? selectedOption.text : '';

            // Limpiar y reconstruir las opciones
            productSelect.innerHTML = '<option value="">Seleccione un producto</option>';

            // Añadir las opciones según los productos filtrados
            Object.values(products).forEach(product => {
                const option = document.createElement('option');
                option.value = product.id;
                option.textContent = product.name;

                // Si este era el producto seleccionado anteriormente, mantenerlo seleccionado
                if (product.id.toString() === currentValue) {
                    option.selected = true;
                }

                productSelect.appendChild(option);
            });

            // Si el valor anterior ya no existe en las nuevas opciones, limpiar los campos relacionados
            if (productSelect.value !== currentValue) {
                const row = productSelect.closest('.product-form');
                if (row) {
                    row.querySelector('.product-dose').value = '';
                    row.querySelector('#product-default-dose').value = '';
                    row.querySelector('.estimated-dose').textContent = '-';
                }
            }
        });
    }

    // Funciones para actualizar información
    function updateFieldInfo() {
        const field = fields[elements.fieldSelect.value];
        elements.fieldInfo.textContent = field ? `Área: ${field.area} ha - Cultivo: ${field.crop}` : '';
        calculateTotalDoses();
        checkStep1Completion();
    }

    function updateMachineInfo() {
        const machine = machines[elements.machineSelect.value];
        elements.machineInfo.textContent = machine ? `Capacidad: ${machine.capacity} litros` : '';
        calculateTotalDoses();
        checkStep1Completion();
    }

    function updateProductInfo(event) {
        const row = event.target.closest('.product-form');
        const product = products[event.target.value];

        const doseInputs = row.querySelectorAll('.product-dose');
        const defaultDoseLabel = row.querySelector('#product-default-dose');
        const estimatedDoseInput = row.querySelector('.estimated-dose-input');
        const estimatedDoseUnit = row.querySelector('.estimated-dose-unit');

        if (product) {
            doseInputs.forEach(doseInput => {
                doseInput.value = product.dose;
                doseInput.dataset.defaultDose = product.dose;
            });

            defaultDoseLabel.value = product.dose + ' ' + product.dose_type_display;

            // Limpiar dosis total estimada
            estimatedDoseInput.value = '';
            estimatedDoseUnit.textContent = product.dose_type.includes('kg') ? 'kg' : 'L';
        } else {
            doseInputs.forEach(doseInput => {
                doseInput.value = '';
            });
            defaultDoseLabel.value = '';
            estimatedDoseInput.value = '';
            estimatedDoseUnit.textContent = '-';
        }

        calculateTotalDoses();
    }

    // Función para validar la fecha de finalización
    function validateCompletedDate() {
        const completedDate = elements.completedDateInput.value;
        if (!completedDate) {
            elements.completedDateInfo.textContent = 'Opcional. Si se establece, el tratamiento se marcará como completado.';
            elements.completedDateInfo.classList.remove('text-danger');
            return true;
        }

        const today = new Date();
        today.setHours(0, 0, 0, 0);
        const selected = new Date(completedDate);
        selected.setHours(0, 0, 0, 0);

        if (selected > today) {
            elements.completedDateInfo.textContent = 'La fecha de finalización no puede ser en el futuro.';
            elements.completedDateInfo.classList.add('text-danger');
            return false;
        } else {
            elements.completedDateInfo.textContent = 'El tratamiento se registrará como completado en esta fecha.';
            elements.completedDateInfo.classList.add('text-success');
            elements.completedDateInfo.classList.remove('text-danger');
            return true;
        }
    }

    // Función para calcular dosis totales
    function calculateTotalDoses() {
        const field = fields[elements.fieldSelect.value];
        const waterPerHa = parseFloat(elements.waterPerHaInput.value) || 0;

        if (!field) return;

        document.querySelectorAll('.product-form').forEach((row, index) => {
            const doseInput = row.querySelector('.product-dose');
            const estimatedDoseInput = row.querySelector('.estimated-dose-input');
            const estimatedDoseUnit = row.querySelector('.estimated-dose-unit');
            const productInput = row.querySelector('.product-select');

            const productId = productInput.value;
            if (!productId || !products[productId]) {
                estimatedDoseInput.value = '';
                return;
            }

            const dose = parseFloat(doseInput.value) || 0;

            // Si el campo "total" fue el último modificado, no recalcular
            if (lastModifiedField.get(index) === 'total' && estimatedDoseInput.value) {
                return;
            }

            if (!dose) {
                estimatedDoseInput.value = '';
                return;
            }

            const doseType = products[productId].dose_type;
            const totalWater = field.area * waterPerHa;
            const unit = doseType.includes('kg') ? 'kg' : 'L';
            let totalDose = 0;

            if (doseType.includes('_per_ha')) {
                totalDose = dose * field.area;
            } else if (doseType.includes('_per_1000l')) {
                totalDose = (dose / 1000) * totalWater;
            } else if (doseType.includes('_per_2000l')) {
                totalDose = (dose / 2000) * totalWater;
            }

            estimatedDoseInput.value = totalDose.toFixed(2);
            estimatedDoseUnit.textContent = unit;
        });
    }

    function calculateDoseFromTotal(event) {
        const row = event.target.closest('.product-form');
        const rowIndex = Array.from(document.querySelectorAll('.product-form')).indexOf(row);

        // Marcar que el campo "total" fue el último modificado
        lastModifiedField.set(rowIndex, 'total');

        const doseInput = row.querySelector('.product-dose');
        const estimatedDoseInput = row.querySelector('.estimated-dose-input');
        const productInput = row.querySelector('.product-select');
        const field = fields[elements.fieldSelect.value];
        const waterPerHa = parseFloat(elements.waterPerHaInput.value) || 0;

        const productId = productInput.value;
        if (!productId || !products[productId] || !field) return;

        const totalDose = parseFloat(estimatedDoseInput.value) || 0;
        if (!totalDose) {
            doseInput.value = '';
            return;
        }

        const doseType = products[productId].dose_type;
        const totalWater = field.area * waterPerHa;
        let dosePerHa = 0;

        if (doseType.includes('_per_ha')) {
            dosePerHa = totalDose / field.area;
        } else if (doseType.includes('_per_1000l')) {
            dosePerHa = (totalDose * 1000) / totalWater;
        } else if (doseType.includes('_per_2000l')) {
            dosePerHa = (totalDose * 2000) / totalWater;
        }

        doseInput.value = dosePerHa.toFixed(2);
    }

    function handleDoseChange(event) {
        const row = event.target.closest('.product-form');
        const rowIndex = Array.from(document.querySelectorAll('.product-form')).indexOf(row);

        // Marcar que el campo "dosis" fue el último modificado
        lastModifiedField.set(rowIndex, 'dose');

        calculateTotalDoses();
    }

    function limitDecimalPlaces(event) {
        const input = event.target;
        const value = input.value;

        // Si contiene un punto decimal
        if (value.includes('.')) {
            const parts = value.split('.');
            // Si hay más de dos decimales después del punto
            if (parts[1] && parts[1].length > 2) {
                // Truncar a dos decimales
                input.value = `${parts[0]}.${parts[1].substring(0, 2)}`;
            }
        }
    }

    // Aplicar la restricción a los campos de dosis existentes
    document.querySelectorAll('.product-dose').forEach(input => {
        input.addEventListener('input', limitDecimalPlaces);
    });

    // Manejo de productos
    function addProductRow() {
        if (formCount >= maxForms) return alert('No se pueden añadir más productos');

        // Clonar la fila sin eventos previos
        const newRow = elements.productsTable.querySelector('.product-form').cloneNode(true);
        const newRowIndex = formCount;

        // Actualizar atributos name e id de los elementos internos
        newRow.querySelectorAll('[name]').forEach((input) => {
            const oldName = input.getAttribute('name');
            const newName = oldName.replace(/treatmentproduct_set-\d+-/, `treatmentproduct_set-${formCount}-`);
            input.setAttribute('name', newName);

            const oldId = input.getAttribute('id');
            if (oldId) {
                const newId = oldId.replace(/id_treatmentproduct_set-\d+-/, `id_treatmentproduct_set-${formCount}-`);
                input.setAttribute('id', newId);
            }
        });

        // Resetear valores en los nuevos inputs
        newRow.querySelector('.product-dose').value = '';
        newRow.querySelector('.estimated-dose-input').value = '';
        newRow.querySelector('.estimated-dose-unit').textContent = '-';
        newRow.querySelector('#product-default-dose').value = '';

        // Resetear el tracking para esta nueva fila
        lastModifiedField.set(newRowIndex, null);

        // Actualizar el select con los productos filtrados disponibles
        const productSelect = newRow.querySelector('.product-select');
        productSelect.innerHTML = '<option value="">Seleccione un producto</option>';

        // Añadir las opciones según los productos filtrados
        Object.values(products).forEach(product => {
            const option = document.createElement('option');
            option.value = product.id;
            option.textContent = product.name;
            productSelect.appendChild(option);
        });

        productSelect.addEventListener('change', updateProductInfo);

        // Añadir evento de eliminación
        newRow.querySelector('.remove-row').addEventListener('click', () => {
            newRow.remove();
            updateFormIndexes();
        });

        // Eventos modificados para usar las nuevas funciones
        newRow.querySelector('.product-dose').addEventListener('input', handleDoseChange);
        newRow.querySelector('.product-dose').addEventListener('input', limitDecimalPlaces);

        newRow.querySelector('.estimated-dose-input').addEventListener('input', calculateDoseFromTotal);
        newRow.querySelector('.estimated-dose-input').addEventListener('input', limitDecimalPlaces);

        // Agregar la nueva fila a la tabla
        elements.productsTable.appendChild(newRow);

        // Incrementar el contador de formularios
        elements.totalFormsInput.value = ++formCount;

        // Agregar evento para limitar decimales
        const doseInput = newRow.querySelector('.product-dose');
        doseInput.addEventListener('input', limitDecimalPlaces);
        doseInput.addEventListener('input', calculateTotalDoses);

    }

    function updateFormIndexes() {
        document.querySelectorAll('.product-form').forEach((row, index) => {
            row.querySelectorAll('input, select').forEach(el => {
                ['name', 'id'].forEach(attr => {
                    if (el.hasAttribute(attr)) {
                        el.setAttribute(attr, el.getAttribute(attr).replace(/treatmentproduct_set-\d+-/, `treatmentproduct_set-${index}-`));
                    }
                });
            });
        });
        elements.totalFormsInput.value = formCount = document.querySelectorAll('.product-form').length;
    }

    // Funcionalidad Step Form
    function showStep(stepNumber) {
        if (stepNumber === 1) {
            elements.step1.classList.remove('d-none');
            elements.step2.classList.add('d-none');
            elements.progressBar.style.width = '50%';
        } else {
            elements.step1.classList.add('d-none');
            elements.step2.classList.remove('d-none');
            elements.progressBar.style.width = '100%';
        }
    }

    function checkStep1Completion() {
        const treatmentType = elements.treatmentTypeSelect.value;
        const fieldSelected = elements.fieldSelect.value;
        const machineSelected = elements.machineSelect.value;
        const waterPerHaValue = elements.waterPerHaInput.value;
        const completedDateValid = validateCompletedDate();
        const nameValue = elements.nameInput.value;
        const dateValue = elements.dateInput.value;

        const requiredFieldsFilled =
            fieldSelected !== '' &&
            treatmentType !== '' &&
            nameValue !== '' &&
            dateValue !== '';

        let conditionalFieldsValid = true;

        if (treatmentType === 'spraying') {
            conditionalFieldsValid = machineSelected !== '' && waterPerHaValue !== '';
        }

        elements.nextToProducts.disabled = !(requiredFieldsFilled && conditionalFieldsValid && completedDateValid);
    }

    // Manejo de cambio en tipo de tratamiento
    function handleTreatmentTypeChange() {
        const selectedType = elements.treatmentTypeSelect.value;

        // Mostrar/ocultar los campos condicionales
        if (!selectedType) {
            elements.conditionalFields.classList.add('d-none');
            elements.machineSelect.disabled = true;
            elements.waterPerHaInput.disabled = true;
            return;
        } else {
            elements.conditionalFields.classList.remove('d-none');
        }

        if (selectedType === 'spraying') {
            // Para pulverización: habilitar máquina y mojado
            elements.machineFieldGroup.classList.remove('d-none');
            elements.waterFieldGroup.classList.remove('d-none');
            elements.machineSelect.disabled = false;
            elements.machineSelect.required = true;
            elements.waterPerHaInput.disabled = false;
            elements.waterPerHaInput.required = true;

            // Establecer valor por defecto de mojado a 850 cuando se selecciona una máquina
            if (!elements.waterPerHaInput.value || elements.waterPerHaInput.value === '0') {
                elements.waterPerHaInput.value = '850';
            }

        }
        else if (selectedType === 'fertigation') {
            // Para fertirrigación: ocultar máquina y mojado
            elements.machineFieldGroup.classList.add('d-none');
            elements.waterFieldGroup.classList.add('d-none');
            elements.machineSelect.disabled = true;
            elements.machineSelect.required = false;
            elements.machineSelect.value = '';
            elements.waterPerHaInput.value = '0';
            elements.waterPerHaInput.required = false;
        }

        checkStep1Completion();
    }

    // Validación de formulario
    function validateForm(event) {
        const selectedType = elements.treatmentTypeSelect.value;
        const nameValue = elements.nameInput.value;
        const dateValue = elements.dateInput.value;

        // Check name field
        if (!nameValue) {
            event.preventDefault();
            alert('Debe ingresar un nombre para el tratamiento');
            showStep(1);
            return false;
        }

        // Check date field
        if (!dateValue) {
            event.preventDefault();
            alert('Debe seleccionar una fecha para el tratamiento');
            showStep(1);
            return false;
        }

        if (!selectedType) {
            event.preventDefault();
            alert('Debe seleccionar un tipo de tratamiento');
            showStep(1);
            return false;
        }

        if (selectedType === 'spraying') {
            // Validar máquina seleccionada
            if (!elements.machineSelect.value) {
                event.preventDefault();
                alert('Para tratamientos de pulverización, debe seleccionar una máquina');
                showStep(1);
                return false;
            }

            // Validar mojado
            if (!elements.waterPerHaInput.value) {
                event.preventDefault();
                alert('Para tratamientos de pulverización, debe indicar el volumen de caldo (L/ha)');
                showStep(1);
                return false;
            }
        }

        // Validar que al menos hay un producto
        const validProducts = Array.from(document.querySelectorAll('.product-form')).filter(row => {
            const productSelect = row.querySelector('.product-select');
            const dose = row.querySelector('.product-dose');
            return productSelect.value && dose.value;
        });

        if (validProducts.length === 0) {
            event.preventDefault();
            alert('Debe agregar al menos un producto al tratamiento');
            showStep(2);
            return false;
        }

        // Validar fecha de finalización
        if (elements.completedDateInput.value) {
            if (!validateCompletedDate()) {
                event.preventDefault();
                alert('La fecha de finalización no puede ser en el futuro');
                showStep(1);
                return false;
            }
        }

        return true;
    }

    // Añadir event listeners
    elements.fieldSelect.addEventListener('change', updateFieldInfo);
    elements.treatmentTypeSelect.addEventListener('change', handleTreatmentTypeChange);
    elements.machineSelect.addEventListener('change', updateMachineInfo);
    elements.waterPerHaInput.addEventListener('input', calculateTotalDoses);
    elements.waterPerHaInput.addEventListener('input', checkStep1Completion);
    elements.machineSelect.addEventListener('change', checkStep1Completion);
    elements.fieldSelect.addEventListener('change', checkStep1Completion);
    elements.treatmentTypeSelect.addEventListener('change', checkStep1Completion);
    elements.completedDateInput.addEventListener('change', validateCompletedDate);
    elements.completedDateInput.addEventListener('change', checkStep1Completion);
    elements.addProductBtn.addEventListener('click', addProductRow);
    elements.nameInput.addEventListener('input', checkStep1Completion);
    elements.dateInput.addEventListener('change', checkStep1Completion);

    // Event listeners para cambio de paso
    elements.nextToProducts.addEventListener('click', async () => {
        const selectedType = elements.treatmentTypeSelect.value;

        // Cargar los productos específicos para este tipo antes de mostrar el paso 2
        await loadProductsData(selectedType);

        // Reiniciar la tabla de productos
        resetProductsTable();

        // Avanzar al paso 2
        showStep(2);
    });

    elements.backToInfo.addEventListener('click', () => showStep(1));

    // Eventos para eliminar productos
    document.querySelectorAll('.remove-row').forEach(button => button.addEventListener('click', function() {
        this.closest('.product-form').remove();
        updateFormIndexes();
    }));

    // Eventos para calcular dosis
    document.querySelectorAll('.product-dose').forEach((el, index) => {
        el.addEventListener('input', handleDoseChange);
        // Inicializar el tracking para las filas existentes
        lastModifiedField.set(index, null);
    });

    document.querySelectorAll('.product-select').forEach(select => select.addEventListener('change', updateProductInfo));
    document.querySelectorAll('.estimated-dose-input').forEach(input => {
        input.addEventListener('input', calculateDoseFromTotal);
        input.addEventListener('input', limitDecimalPlaces);
    });

    // Validación en envío del formulario
    document.getElementById('treatmentForm').addEventListener('submit', validateForm);

    // Inicialización
    await loadFieldsData();
    await loadMachinesData();
    handleTreatmentTypeChange();
    checkStep1Completion();

});
