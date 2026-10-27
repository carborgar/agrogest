# Plan: nuevo formulario de crear/editar tratamiento

**Para:** Claude Sonnet (implementación) · **Autor:** Claude Opus, 27/10/2026 · **Validado por:** Carlos
**Prototipo interactivo (móvil + escritorio):** https://claude.ai/artifact/FrHR2DeDaEGCLokAWCzQQ9
(ajustes del prototipo: `mode` = nuevo / editar / editar-hecho; `maquinas` = 1 / 2)

El prototipo es la referencia de UX y de comportamiento. Sus datos son inventados: los datos reales salen de la BD.

---

## 0. Reglas de trabajo

1. **El backend es la fuente de verdad de los cálculos.** El JS solo previsualiza y **tiene que dar exactamente lo mismo** que `TreatmentProduct.save()` / `Treatment.calculate_machine_loads()`. No cambies fórmulas del modelo salvo donde este plan lo dice.
2. **Trabaja por fases y no empieces una fase sin la anterior en verde.** Comandos:
   - `DATABASE_URL=sqlite:///test.sqlite3 pytest` (el `.env` apunta a Supabase; no lances tests contra ella).
   - `npm run test:js` (Node `--test` + jsdom, ya configurado).
   - Antes de empezar, anota cuántos tests fallan en `main` (había 16 preexistentes). Al final no puede haber ni uno más.
3. **Primero el test, después el cambio**, en todos los errores de la sección 1: el test tiene que fallar con el código actual.
4. Sin dependencias nuevas ni paso de build. Vanilla JS + Bootstrap 5 + `django-widget-tweaks`, como el resto del proyecto. Todo gratuito.
5. Rama `feature/formulario-tratamiento`. Un commit por fase.
6. Si algo de este plan choca con el código real, **para y pregunta a Carlos**; no improvises.

---

## 1. Errores actuales que este trabajo corrige

Comprobados leyendo el código el 27/10. Cada uno necesita un test que falle antes del arreglo.

| # | Dónde | Problema | Efecto |
|---|---|---|---|
| E1 | `TreatmentProductForm.Meta.fields` | No incluye `total_overridden`. El formulario nunca lo envía. | El «total a mano» no se guarda: el backend recalcula el total desde la dosis redondeada. El icono de «dosis personalizada» del detalle no sale nunca. |
| E2 | `TreatmentProduct.save()` | `if is_new or not self.total_overridden` | En una línea nueva se ignora el total a mano aunque llegue el flag. |
| E3 | JS `calculateTotalDoses` / `calculateDoseFromTotal` | No tienen rama `pct`. | Productos en % salen con total vacío y no suman al coste estimado (el backend sí los calcula). |
| E4 | JS `updateDoseSummary` | El coste usa `product.price`. El backend usa `TreatmentProduct.unit_price` (precio congelado). | Al editar un tratamiento antiguo, el coste estimado no coincide con el guardado. |
| E5 | `TreatmentFormView.get_initial` | Solo lee `?date=`. | El enlace «Nuevo tratamiento» desde el detalle de parcela (`?field=`) no preselecciona la parcela. |
| E6 | `TreatmentForm` / `TreatmentProductForm` | Los querysets de `field`, `machine` y `product` no se filtran por organización. | Con un POST a mano se pueden usar parcelas, máquinas o productos de otra organización. **Seguridad.** |
| E7 | `TreatmentForm.clean` | Que la fecha de finalización no sea futura solo se comprueba en JS. | Se puede saltar. |
| E8 | JS | Ramas `_per_2000l`, que no existen en `Product.*_DOSE_TYPE_CHOICES`. | Código muerto: quítalo. |

---

## 2. Fase 0: red de seguridad (antes de tocar nada)

### 2.1 Fichero de casos compartido (el núcleo de los tests de cálculo)
Crea `farm/tests/fixtures/treatment_calc_cases.json` con una lista de casos `{id, input, expected}`.
- **Python** (`farm/tests/test_treatment_calc_golden.py`): por cada caso crea `Field`, `Machine`, `Product`, `Treatment` y `TreatmentProduct` con las factories o mothers existentes, guarda, y compara con `expected`: `total_dose`, `dose`, `total_dose_unit`, `total_price`, `price_per_ha`, `get_dose_per_load()`, `calculate_machine_loads()` y `calculate_product_for_partial_load()`.
- **JS** (`static/js/tests/treatment-calc.test.js`): lee **el mismo JSON** y comprueba el módulo de la fase 2.

Así las fórmulas de Python y de JS quedan atadas a un único fichero: si alguien cambia un lado, fallan los tests.

**Los valores esperados se calculan a mano, no copiando la salida del código.** Casos mínimos (añade los que veas):

| id | Tipo | Dosis | Parcela | Mojado | Máquina | Esperado |
|---|---|---|---|---|---|---|
| A | pulv. | 0,5 L/1000L | 4,2 ha | 1000 | 2000 L | total 2,1 L · 1 L/cuba · 4200 L = 2 llenas + parcial 200 L · parcial 0,1 L |
| B | pulv. | 3 kg/1000L, precio 9,50 | 4,2 | 1000 | 2000 | 12,6 kg · 119,70 € · 28,50 €/ha · 6 kg/cuba |
| C | pulv. | 3 kg/ha | 4,2 | 800 | 2000 | 12,6 kg · 7,5 kg/cuba |
| D | pulv. | 1 % | 4,2 | 1000 | 2000 | 42 L · 20 L/cuba (**E3**) |
| E | fertirr. | 10 L/ha | 2,8 | — (0) | — | 28 L · sin cubas |
| F | pulv. parcial | 0,5 L/1000L | 4,2 (aplicada 2,0) | 1000 | 2000 | 1,0 L · €/ha sobre 2,0 ha |
| G | pulv. hecho | 3 kg/1000L | 4,2 | prev. 1000, real 1100 | 2000 | 13,86 kg (usa el real) |
| H | total a mano | kg/ha, total 10 | 4,2 | 1000 | 2000 | total 10 exacto · dosis 2,381 (**E1/E2**) |
| I | total a mano | L/1000L, total 5 | 4,2 | 1000 | 2000 | total 5 exacto · dosis 1,1905 |
| J | redondeo | dosis tecleada 0,0754 | — | — | — | `clean_dose` → 0,076 (ROUND_UP a 3 decimales) |
| K | sin precio | precio 0 | 4,2 | 1000 | — | coste 0, se muestra «Sin precio» |
| L | carga parcial pequeña | — | 1,0 ha | 2030 | 2000 | parcial 30 L → `partial_load = False` (umbral 50 L) |

### 2.2 Caracterización de la vista
Amplía `test_treatment_editing.py` con los POST de crear y editar que **tienen que seguir funcionando**:
- Pulverización completa.
- Fertirrigación (máquina a `None`, mojado a 0).
- Área parcial mayor que la parcela → error.
- Producto duplicado → error.
- Sin productos → error.
- Edición que cambia el mojado → recalcula los totales.
- Edición de un completado → conserva `unit_price` aunque haya cambiado el precio del producto.

---

## 3. Fase 1: backend

1. **E1 + E2 (total a mano).**
   - Añade `total_overridden` a `TreatmentProductForm` (oculto).
   - En `TreatmentProduct.save()`: `if self.total_overridden: calculate_dose_from_total() else: calculate_total_dose()`, sin `is_new`. `clone_to_field` ya pone `False`.
   - Validación: si viene `total_overridden=True`, `total_dose` tiene que ser > 0.
   - Tests: crear con total a mano lo conserva exacto; editar también; quitarlo recalcula desde la dosis.
2. **No toques** el bloque `if not is_new and self.treatment.water_per_ha_changed(): calculate_total_dose()` hasta que Carlos decida D1. Deja un test que documente lo que hace hoy.
3. **E6:** filtra los querysets en `__init__` por la organización del usuario. La vista pasa el usuario o la organización al form y al formset (`form_kwargs`). Tests con un id de otra organización → error de validación.
4. **E7** en `TreatmentForm.clean`.
5. **Mojado real en el formulario:** añade `real_water_per_ha` a `TreatmentForm`.
   - Solo cuenta si es pulverización y hay `finish_date`; tiene que ser > 0.
   - Si no hay `finish_date`, el modelo ya lo limpia.
6. **E5:** en `get_initial`, `?field=<id>` solo al crear y solo si la parcela es de la organización.
7. **Varias parcelas al crear** (decidido por Carlos):
   - Nuevo campo `extra_fields` (`ModelMultipleChoiceField`, filtrado por organización, opcional) solo al crear. `field` sigue siendo la primera.
   - Servidor: con `extra_fields`, prohibido `applied_area` / `zone_notes` y cualquier línea con `total_overridden=True` (error de validación).
   - Servicio nuevo en `services.py`: `create_treatments_for_fields(form, formset, extra_fields)`, en una sola transacción. Crea el principal con `save_treatment_with_products` y, por cada parcela extra, un `Treatment` con los mismos datos (nombre, tipo, fecha, máquina, mojado, `finish_date`, `real_water_per_ha`) y las mismas líneas (`product`, `dose`, `position`, `total_overridden=False`). Los totales salen del `save()`.
   - **Una sola notificación** («Nuevo tratamiento en N parcelas»), no N.
   - Redirección: con 1 parcela, al detalle; con varias, al listado con un mensaje «N tratamientos creados».
   - Tests: 3 parcelas → 3 tratamientos con totales según el área de cada una, 1 notificación, todo o nada si falla una.
8. **Datos para el formulario sin fetch:**
   - En la vista, pasa un único JSON al template con `{{ form_data|json_script:"treatment-form-data" }}` (protegido contra XSS).
   - Contenido:
     - `fields`: id, name, crop, area, `last_treatment_date` (con `annotate(Max)`).
     - `machines`: id, name, capacity.
     - `products`: **todos los activos** (`is_active=True`) con id, name, `type_name`, `spraying {dose, dose_type, label} | null`, `fertigation {…} | null`, price, `recent` (usado en algún tratamiento de la organización en los últimos 90 días).
     - En edición, `lines`: product_id, dose, total_dose, `total_overridden`, `unit_price`, position.
   - Motivo: en campo hay mala cobertura. Hoy son 3 peticiones más una por cada cambio de tipo, y con los datos en la página no hay carga. También hacen falta las dos dosis de cada producto para marcar los no válidos al cambiar de tipo.
   - Las APIs `api-fields`, `api-machines` y `api-products` se quedan (están en `API_URLS` de `base.html`). Comprueba con `grep` si alguien más las usa antes de plantearte quitarlas; no las quites en este trabajo.

---

## 4. Fase 2: módulo de cálculo JS puro

`static/js/treatment-calc.js`, sin DOM. Se expone en `window.TreatmentCalc` y en `module.exports` (como `submit-guard.js`, para poder probarlo con Node). Cada función replica una del modelo; cita en un comentario el método Python que replica.

- `effectiveArea(fieldArea, appliedArea)`: `appliedArea` si es > 0; si no, `fieldArea`.
- `totalUnit(doseType)`: `kg` si es `kg_per_*`; si no, `L` (`pct` → L, como `set_dose_units`).
- `totalFromDose(dose, doseType, area, waterPerHa)` y `doseFromTotal(total, …)`. **Devuelven `null` si no se puede calcular** (falta el mojado en `*_per_1000l` / `pct`); nunca `0` ni `NaN` en silencio.
- `dosePerFullLoad(dose, doseType, capacity, waterPerHa)` (= `get_dose_per_load`).
- `machineLoads(area, waterPerHa, capacity)` → `{totalWater, fullLoads, partialWater, partialLoad}`, con umbral de 50 L (= `calculate_machine_loads`).
- `dosePartialLoad(…)` (= `calculate_product_for_partial_load`).
- `lineCost(total, unitPrice)`, `deviation(dose, recommended)` y `DOSE_WARNING_RATIO = 0.25`.
- `roundDoseUp(value)`: igual que `clean_dose` (ROUND_UP, 3 decimales). Ojo con la coma flotante: trabaja con enteros (`Math.ceil(Math.round(v * 1e6) / 1e3) / 1e3`) y pruébalo con 0,0754, 1,0001, 2,1 y 0,3.
- `parseNumber(str)`: acepta coma o punto, ignora espacios y devuelve `null` si está vacío o no es válido.

Tests: el JSON de la fase 0 más casos límite (sin mojado, área 0, `"0,5"`, `"1.000"`: decide y documenta si es mil o uno, recomiendo rechazarlo; negativos → `null`).

---

## 5. Fase 3: estado del formulario (sin DOM)

`static/js/treatment-form-state.js`: estado más una función `derive(state, data)` que devuelve todo lo que se pinta (líneas con total, coste, por cuba y aviso; cubas; resumen; lista «Falta: …»; nombre automático). Es lo que hace `renderVals()` en el prototipo. Acciones puras `(state, payload) → state`.

**Reglas de interacción** (cada una con test en `static/js/tests/treatment-form-state.test.js`):

1. **Cambiar el tipo:**
   - Las dosis pasan a la recomendada del nuevo tipo.
   - Se quitan los totales a mano.
   - Los productos sin dosis para ese tipo quedan marcados «no válidos» y bloquean el guardado.
   - En fertirrigación, máquina `null` y mojado 0.
2. **Cambiar la dosis:** quita el total a mano de esa línea.
3. **Cambiar el total** (solo con 1 parcela):
   - Marca `total_overridden` y la dosis se deriva con `doseFromTotal`.
   - Si después cambia el mojado, el área parcial o la máquina, **se mantiene el total y se rederiva la dosis** (es lo que hace el backend: `recalculate_product_doses` → `calculate_dose_from_total`).
4. **Cambiar de parcela, o pasar a más de 1 parcela:** se quitan los totales a mano. Con más de 1 parcela, el total no se puede editar y desaparece el «tratamiento parcial».
5. **Añadir un producto:** entra con la dosis recomendada del tipo actual; no se puede añadir dos veces. Quitarlo renumera `position`.
6. **Editar:** las líneas mantienen la dosis guardada (no la recomendada), el `total_overridden` guardado y el `unit_price` guardado para el coste. El nombre cuenta como tocado.
7. **«Ya está hecho»:**
   - El mojado real > 0 sustituye al previsto en los cálculos (= `actual_water_per_ha`).
   - Al desactivarlo se borran la fecha de realización y el mojado real.
   - La fecha de realización no puede ser futura.
8. **Pulverización sin mojado:** las líneas `*_per_1000l` y `pct` muestran total «—» y coste «Falta el mojado»; las `*_per_ha` sí se calculan.
9. **Con una sola máquina** queda seleccionada siempre y no se muestran chips. Con ninguna, aviso con enlace para crear una (bloquea en pulverización).
10. ~~**Nombre automático:** se rellena hasta que el usuario lo toca (ver D2).~~ **Anulada (27/10):** el nombre se escribe a mano, vacío al crear y obligatorio.
11. **Área parcial:** entre 0 y el área de la parcela; si no, error en la sección.
12. **Errores:** la lista «Falta: …» y el error de cada sección salen de `derive()`, no del DOM.

---

## 6. Fase 4: plantilla y UI

Sustituye `templates/farm/treatments/treatment_form.html` (hoy 1271 líneas con el JS dentro). Estructura:

- **Servidor:** sigue pintando el `form` y el `management_form` del formset. Los inputs reales del formset (`product`, `dose`, `total_dose`, `total_overridden`, `DELETE`, `id`, y el orden = `position`) van **ocultos**. El controlador JS (`static/js/treatment-form.js`) los escribe justo antes de enviar, con valores normalizados con punto decimal.
- **Inputs visibles:** `type="text" inputmode="decimal"` con `parseNumber`. No uses `type="number"`: con el idioma en español, iOS mete coma y el valor llega vacío, y Django (`localize=False`) no acepta coma.
- **Móvil (< 992 px):** como el artboard «Tratamiento · móvil».
  - Secciones apiladas.
  - Parcelas y productos en `offcanvas-bottom` de Bootstrap, con búsqueda, multi-selección y «Reciente».
  - La barra inferior de navegación se cambia por la barra fija de guardar, según `decision-layout-mobile-first`.
- **Escritorio (≥ 992 px):** como el artboard «Tratamiento · escritorio».
  - Dos columnas, resumen `position: sticky`.
  - Productos en tabla.
  - «Añadir producto» con buscador en línea: flechas, Intro añade el primero válido, Esc cierra.
  - Parcela en desplegable con búsqueda.
- Mismo DOM en las dos versiones siempre que se pueda: las líneas son tarjetas en móvil y filas de rejilla en escritorio solo con CSS.
- **Sin `alert()`.** Los errores del servidor se pintan en su sección (mapea `form.errors` y los errores del formset a sección o línea). Al fallar el envío, el foco va al primer error.
- Sigue cargando `submit-guard.js` (prevención de envíos duplicados).
- **Accesibilidad:** `label` en todos los campos, `aria-expanded` en desplegables y hojas, objetivos táctiles ≥ 44 px en móvil.
- **Sin «Partir de uno anterior»** (descartado: ya existe Clonar) **y sin sugerencias de mojado.**
- Estilos en `scss/custom-bootstrap.scss` con las variables existentes (`--primary` `#2E7D32`, Inter…). Recompila con `npm run build:css`.

---

## 7. Fase 5: verificación

1. `pytest` y `npm run test:js` en verde (sin fallos nuevos respecto a `main`).
2. Prueba de punta a punta con Playwright (ya instalado):
   - Crea desde la UI los casos B, D, H y una de 3 parcelas.
   - Comprueba que el **total y el coste que enseñaba el formulario** coinciden con los de la **página de detalle** tras guardar. Es la comprobación más importante.
3. Capturas a 375 px y 1280 px de: nuevo vacío, pulverización completa, fertirrigación con un producto no válido, editar hecho, error de envío. Revísalas antes de dar la fase por cerrada.
4. Apunta en el documento del proyecto qué se ha hecho, qué no y cualquier diferencia con el prototipo.

---

## 8. Decisiones de Carlos (27/10)

- **D1 — Respetar el total a mano** en tratamientos hechos con mojado real distinto. En `TreatmentProduct.save()`, el bloque `if not is_new and self.treatment.water_per_ha_changed(): calculate_total_dose()` no se aplica si `total_overridden=True` (en ese caso se deriva la dosis del total). Test que lo demuestre (falla antes, pasa después). Sustituye el «test que documente lo que hace hoy» de la fase 1.
- **D2 — ANULADA por Carlos el 27/10** (con muchos productos el nombre automático no tiene sentido; el nombre se escribe a mano, campo vacío con placeholder «Ej. Cobre + Mojante», obligatorio). Texto original: **Nombre automático con nombres completos**: hasta 3 productos válidos unidos con « + »; si pasa de 100 caracteres, cortar a 99 y añadir «…». Se rellena mientras el usuario no toque el nombre; en edición se considera tocado.

---

## 9. Estado de la implementación

Rama `feature/formulario-tratamiento` (sin push). Fases 0 a 5 (primera ronda) y una segunda ronda con los cambios de Carlos y los arreglos de la revisión independiente.

**Resultado de las pruebas (final)**: `pytest` 15 fallidos / 283 pasados (en `main`: 15 / 160). Son exactamente los mismos 15 de `main`; ninguno nuevo. `npm run test:js`: 135 de 135.

### Primera ronda (fases 0 a 5)

- **Fase 0** (`bc8f7a3`): casos golden compartidos Python/JS y tests de caracterización del POST.
- **Fase 1** (`9f7090e`): backend. E1 a E8 y D1 con test escrito antes y visto en rojo; `total_dose` opcional si no hay total a mano; mojado real conservado al editar si el cliente no lo manda; varias parcelas al crear; `build_treatment_form_data` (datos por `json_script`).
- **Fase 2** (`c9a382f`): `static/js/treatment-calc.js` (cálculo puro).
- **Fase 3** (`dbacc67`): `static/js/treatment-form-state.js` (acciones puras, `derive()`, `toFormValues()`).
- **Fase 4** (`75a9af6`): plantilla nueva, controlador `treatment-form.js`, estilos `.tf-*`, campo oculto `position`, errores del servidor por sección y línea.
- **Fase 5** (`74c6f61`): tests de vista formulario a detalle (casos B, D, H y 3 parcelas) en lugar de Playwright.

### Segunda ronda

Cambios de Carlos:
- **A1 `c963d30`**: nombre automático quitado (D2 anulada, ver sección 8). El nombre se escribe a mano, vacío al crear, obligatorio.
- **A3 `2e20a83`**: fuera el enlace «Crear una» máquina y el estado «sin máquinas». Con 0 máquinas se pide elegir máquina y decide el servidor.
- **A2 `6bd48d6`**: el total es un input siempre visible junto a la dosis. Editarlo deriva la dosis en vivo y marca el total a mano; editar la dosis recalcula el total y quita el «a mano»; vaciarlo vuelve a calcular desde la dosis; el campo que se teclea nunca se reescribe (foco y cursor intactos). Con varias parcelas muestra la suma, deshabilitada, con su explicación. «Total puesto a mano» + «Volver a calcularlo» se mantienen. Envío con `total_overridden=true` y total exacto (25 se envía como `25.0000`) y el detalle tras guardar muestra 25 L.

Arreglos de la revisión:
- **B1 `6f76dd5`**: los valores del servidor (inputs del formset, `data.lines`) se leen con punto decimal estricto (`1.500` es uno y medio) y pasan al estado con coma; la regla de miles solo vale para lo que teclea el usuario, con el mensaje «Usa coma para los decimales». Dosis con hasta 4 decimales (B9). Fixtures HTML generados desde la plantilla real por `farm/tests/test_form_page_fixtures.py` (falla si están desactualizados; se regeneran con `AGRO_REGEN_FIXTURES=1`) y test del controlador con el JS real sobre ellos (B11).
- **B2 `6241e7f`**: cálculo decimal exacto (ver decisión abajo).
- **B3, B8, B7 `5d3dad5`**: el servidor rechaza mojado negativo, área parcial <= 0 y dosis <= 0; el formset decide «varias parcelas» con las parcelas extra ya validadas (sin la principal); «hoy» en hora de España (ver decisión abajo).
- **B4, B5, B6, B9, B10 y faltas del prototipo `5d9831b`**: sin Bootstrap se usa el desplegable también en móvil y `<noscript>`; flechas e Intro en el buscador de productos; precio guardado conservado al re-añadir un producto al editar; accesibilidad (sin `role="alert"` repintado, listbox); etiqueta «Reciente» y €/unidad; pie «Listo · N parcelas/productos»; poder quitar de la lista un producto añadido aunque no valga para el tipo.

### Decisiones tomadas (con su motivo)

**B2: redondeo.** La diferencia vista previa/modelo tenía dos causas: el modelo hacía `Decimal(float)` (`Decimal(1.9)` = 1,8999...) y el JS redondeaba mitad arriba sobre float mientras el modelo (y el `DecimalField` de Django al guardar) redondea mitad al par. Decisión: arreglar el backend y alinear el JS, no al revés.
- Backend: `Decimal(str(x))` en `calculate_total_dose`, `calculate_dose_from_total`, `calculate_prices` (área y mojado), `get_dose_per_load` y la cuba parcial (estas dos pasan de float a aritmética decimal; siguen devolviendo float redondeado a 4 decimales). Se **mantiene mitad al par** (el modo que ya usaba): cambiarlo a mitad arriba movería valores guardados en los empates exactos, y el objetivo era quitar solo el ruido de coma flotante. `price_per_ha` parte del `total_price` ya redondeado a 2 decimales (lo que queda guardado y suma el detalle).
- JS: `treatment-calc.js` usa aritmética decimal exacta (BigInt escalado), lee los números por su representación decimal más corta (igual que `str()` de Python) y redondea una sola vez, mitad al par.
- Sin migración ni recálculo masivo: solo cambian los valores de un tratamiento si se vuelve a guardar, y solo en los casos que antes arrastraban el ruido (~1 %).
- Los dos casos de la revisión quedan en el fichero compartido (N y O): 0,5 % · 6,1 ha · 200 L/ha · 8,95 € da 54,60 € y 2,409 L/1000L · 1,9 ha · 500 L/ha da 2,2886. Además hay empates a 4 y 2 decimales (P, Q), un total a mano con división no exacta (R) y un test diferencial con 700 casos aleatorios calculados por el modelo real (`treatment_calc_random.json`) que el JS reproduce al bit. Todas las comparaciones son exactas, sin tolerancia; si se cambia el redondeo del JS a mitad arriba fallan 20 de 700.
- Efecto lateral conocido: un caso con dosis de 4 decimales (P) no se puede teclear en el formulario (la dosis se redondea hacia arriba a 3 decimales, `clean_dose`), así que solo lo cubren el módulo de cálculo y Python.

**B7: «hoy».** `TIME_ZONE` es UTC y el resto de la app usa fechas UTC en el servidor (`date.today()`, `timezone.localdate()`) y la fecha local del navegador en el JS del calendario y del tiempo. Entre las 00:00 y las 02:00 en España el formulario ofrecía «ayer» y rechazaba como futura la realización de «hoy». No se ha cambiado `TIME_ZONE` (afectaría a todo). Se añade `settings.FARM_TIME_ZONE = 'Europe/Madrid'` y `farm/timeutils.local_today()`, usada solo para el «hoy» del formulario de tratamiento: fecha por defecto, `form_data.today` (lo que usa el JS) y validación de `finish_date`. Si falta la base de datos de zonas horarias del sistema, vuelve a la fecha UTC. **Pendiente (no tocado)**: los estados «atrasado/pendiente» del modelo y el dashboard siguen con la fecha UTC; conviene decidir si se alinean.

### Diferencias con el plan y por qué

1. **Sin Playwright ni capturas.** No hay navegador en el entorno y no se instalaron navegadores pesados. La prueba de punta a punta se sustituyó por tests de vista de Django (mismo POST que escribe el controlador, comprobando el detalle) y por tests del controlador con jsdom sobre HTML real de la plantilla. Esto cubre el contrato formulario a detalle y la lógica de la interfaz, no el aspecto.
2. **Campo oculto `position`** en cada línea (no estaba en el plan): el orden de la cuba lo decide el POST y se renumera 0..n-1 al guardar.
3. **Números como `type="text" inputmode="decimal"`** (coma decimal española); el controlador escribe valores normalizados en los inputs reales de Django justo antes de enviar.
4. **`dispatch` llama directo a `S.actions[tipo]`**, no a `S.reduce` (el payload de `setType` usa la clave `type` y chocaba con la del reduce).
5. **Dosis de un total a mano**: al pulsar «Volver a calcularlo» o vaciar el total, la dosis se redondea hacia arriba a 3 decimales como hace el servidor (p. ej. 25 L en 4,2 ha vuelve a 25,0026 L), porque sin total a mano la dosis es la fuente de verdad.

### Pendiente o no verificado

- **Nada se ha visto en un navegador real**: maquetación a 375 px y 1280 px, barra fija, resumen sticky, hojas inferiores (offcanvas), desplegables, foco y teclado móvil, cambio de ancho con `matchMedia`, tamaño de los objetivos táctiles (las reglas CSS están pensadas para >= 44 px en móvil; no medido). jsdom no calcula layout ni foco real del navegador.
- Faltan las capturas de la fase 5 y la comparación visual con el prototipo.
- El reparto de la mitad al par frente a mitad arriba es una decisión de producto no consultada: se mantuvo el comportamiento existente del backend.
- Los 15 tests fallidos de `main` siguen igual y no se han tocado.
- Cuando haya navegador: repetir a mano los casos B, D, H, 3 parcelas, un total redondeado al envase (p. ej. 24 L a 25 L en fertirrigación), producto no válido al cambiar de tipo, editar un tratamiento hecho, un error de envío y el uso sin Bootstrap (bloqueando el CDN).
