// Página «El Tiempo»: una tarjeta por municipio con selector de día, resumen del día y previsión por horas.
// Mismo lenguaje que el resto de pantallas: veredicto y cifras en dt-summary, horas en columnas wx-h y colores de estado --tl-0…3.
// Necesita weather.js (AgroWeather) y en la página: #wov-grid (con data-url), #wov-skeletons,
// #wov-subtitle y el JSON de parcelas en #wov-fields.
(function () {
    // Nivel del servidor → tono de la paleta (3 verde, 1 ámbar, 0 rojo)
    const TREATMENT = {
        ok: { key: 'ok', tone: 3, label: 'Apto para tratar' },
        warn: { key: 'warn', tone: 1, label: 'Precaución' },
        bad: { key: 'bad', tone: 0, label: 'Adverso' },
    };
    const HOUR_LEVEL = { ok: 'buena', warn: 'dudosa', bad: 'mala' };
    // La probabilidad de lluvia ≥ 50 % se pinta en rojo: es solo presentación, la decisión de tratar la trae `level`
    const RAIN_HIGH = 50;
    // ≥ 20 % ya es ámbar, como en la rejilla (la hora deja de ser «buena» con OK_RAIN_PROB = 20)
    const RAIN_WARN = 20;
    // Viento máximo del día (nivel 0-3 del servidor: ≤10, ≤15, <20, ≥20 km/h) → color de texto
    const WIND_CLASS = ['dt-fg-3', 'dt-fg-1', 'dt-fg-1', 'dt-fg-0'];
    let retryBound = false;

    const cards = {};   // cardId → municipio (con sus días)
    let cardCounter = 0;

    // ── Utilidades ─────────────────────────────────────────────────
    function esc(value) {
        return String(value ?? '').replace(/[&<>"']/g, c => `&#${c.codePointAt(0)};`);
    }

    function plural(n, word) {
        return `${n} ${word}${n === 1 ? '' : 's'}`;
    }

    function fmtTemp(t) {
        return t == null ? '—' : `${Math.round(t)}°`;
    }

    function fmtDecimal(n) {
        return String(n).replace('.', ',');
    }

    function fmtLitres(mm) {
        return `${fmtDecimal(mm)} L/m²`;
    }

    function hh(hour) {
        return `${String(hour).padStart(2, '0')}:00`;
    }

    function treatmentOf(level) {
        return TREATMENT[level] || TREATMENT.warn;
    }

    // Icono de cielo: el servidor manda una clase Font Awesome; solo se pintan las conocidas (el resto, nube)
    const SKY = {
        'fa-sun': 'sun', 'fa-cloud-sun': 'sun', 'fa-cloud': 'cloud', 'fa-smog': 'fog',
        'fa-cloud-rain': 'rain', 'fa-cloud-sun-rain': 'rain', 'fa-cloud-showers-heavy': 'rain',
        'fa-bolt': 'storm', 'fa-snowflake': 'snow',
    };
    function skyIcon(icon) {
        const kind = SKY[icon] || (icon === 'fa-cloud-drizzle' ? 'rain' : 'cloud');
        const fa = SKY[icon] ? icon : (kind === 'rain' ? 'fa-cloud-rain' : 'fa-cloud');
        return `<i class="fa ${fa} wx-sky wx-sky--${kind}" aria-hidden="true"></i>`;
    }

    const VERDICT_ICON = { ok: 'fa-circle-check', warn: 'fa-triangle-exclamation', bad: 'fa-circle-xmark' };

    // Hoy, sin las horas pasadas (si no queda ninguna, se muestra el día entero).
    // Si de hoy quedan pocas, se completan con las primeras del día siguiente cuando AEMET las trae.
    const MIN_HOURS = 8;
    function displayHours(day, nextDay) {
        const upcoming = AgroWeather.upcomingHours(day);
        if (!upcoming.length) return day.hours || [];
        const missing = MIN_HOURS - upcoming.length;
        if (missing > 0 && day.date === AgroWeather.localDate() && nextDay?.hours?.length) {
            return upcoming.concat(nextDay.hours.slice(0, missing));
        }
        return upcoming;
    }

    // Color del texto de la lluvia: ámbar desde RAIN_WARN, rojo desde RAIN_HIGH, apagado si no llueve
    function rainTone(prob) {
        if (prob === 0) return 'dt-fg-2';
        if (prob >= RAIN_HIGH) return 'dt-fg-0';
        if (prob >= RAIN_WARN) return 'dt-fg-1';
        return '';
    }

    // ── Resumen del día ────────────────────────────────────────────
    function summaryCell(label, value, sub, { cls = '', valueCls = '', subTitle = '', icon = '' } = {}) {
        const title = subTitle ? ` title="${esc(subTitle)}"` : '';
        const ic = icon ? `<i class="fa ${icon}" aria-hidden="true"></i>` : '';
        return `<div class="dt-cell ${cls}">
            <div class="dt-label">${ic}${label}</div>
            <div class="dt-value ${valueCls}">${value}</div>
            <div class="dt-sub"${title}>${sub}</div>
        </div>`;
    }

    function windowsText(hours) {
        if (!hours.length) return 'Sin detalle por horas';
        const windows = AgroWeather.okWindows(hours);
        return windows.length ? `Mejor franja: ${windows.map(w => `${hh(w.from)}–${hh(w.to)}`).join(' · ')}` : 'Sin horas buenas';
    }

    function tempRange(day, hours) {
        const temps = hours.map(h => h.temperature).filter(t => t != null);
        const max = day.max_temp ?? (temps.length ? Math.max(...temps) : null);
        const min = day.min_temp ?? (temps.length ? Math.min(...temps) : null);
        return min == null ? fmtTemp(max) : `${fmtTemp(min)} – ${fmtTemp(max)}`;
    }

    function rainCell(day) {
        const prob = day.max_precipitation_probability || 0;
        let sub = 'Sin lluvia';
        let subTitle = '';
        if (prob > 0 && day.total_precipitation > 0) {
            sub = fmtLitres(day.total_precipitation);
        } else if (prob > 0) {
            sub = 'Sin dato de litros';
            subTitle = 'AEMET no da los litros para más allá de 48 h';
        }
        return summaryCell('Lluvia', `${prob} <small>%</small>`, sub, { valueCls: rainTone(prob), subTitle, icon: 'fa-droplet' });
    }

    // Primero lo que decide si se puede tratar: veredicto, viento y lluvia; después la temperatura
    function summaryHtml(day, hours) {
        const t = treatmentOf(day.level);
        const windClass = WIND_CLASS[day.wind_level] || WIND_CLASS[0];
        const verdict = `<i class="fa ${VERDICT_ICON[t.key]}" aria-hidden="true"></i> ${esc(t.label)}`;
        const own = hours.filter(h => !h.date || h.date === day.date);   // las horas de mañana que completan hoy no son franja de hoy
        return `<div class="dt-summary wx-summary">
            ${summaryCell('Tratamiento', verdict, esc(windowsText(own)), { cls: `wx-verdict dt-tone-${t.tone}` })}
            ${summaryCell('Viento máx.', `${fmtDecimal(day.max_wind_speed ?? 0)} <small>km/h</small>`, 'Máximo del día', { valueCls: windClass, icon: 'fa-wind' })}
            ${rainCell(day)}
            ${summaryCell('Temperatura', tempRange(day, hours), `${skyIcon(day.icon)} ${esc(day.label_weather)}`, { icon: 'fa-temperature-half' })}
        </div>`;
    }

    // ── Previsión por horas: una columna por hora, repartidas a todo el ancho ──
    // `dayDate`: las horas de otro día (las que completan hoy) se marcan como «mañ.»
    function hourCell(h, dayDate) {
        const hr = AgroWeather.hourOf(h);
        const wind = Math.round(h.wind_speed);
        const rain = h.precipitation_probability || 0;
        const level = HOUR_LEVEL[h.level] ? h.level : 'warn';
        const next = Boolean(dayDate && h.date && h.date !== dayDate);
        const litres = h.precipitation > 0 ? ` · ${fmtLitres(h.precipitation)}` : '';
        const when = next ? 'mañana ' : '';
        const tag = dayDate ? `<small class="wx-row-day">${next ? 'mañ.' : 'hoy'}</small>` : '';
        return `<div class="wx-h wx-h--${level}${next ? ' wx-h--next' : ''}" title="${when}${hh(hr)} · hora ${HOUR_LEVEL[level]} · ${fmtTemp(h.temperature)} · viento ${wind} km/h · lluvia ${rain} %${litres}">
            ${tag}<span class="wx-row-hr">${hr}h</span>${skyIcon(h.icon)}<em class="wx-row-temp">${fmtTemp(h.temperature)}</em><b class="wx-row-wind">${wind}</b><i class="wx-row-rain">${rain}</i>
        </div>`;
    }

    function hourAria(day, hours) {
        return `Hora a hora, ${day.label}: ` + hours.map(h =>
            `${h.date && h.date !== day.date ? 'mañana ' : ''}${hh(AgroWeather.hourOf(h))} ${fmtTemp(h.temperature)}, viento ${Math.round(h.wind_speed)} km/h, lluvia ${h.precipitation_probability || 0} %`).join('; ');
    }

    function sunLine(day) {
        const parts = [];
        if (day.sunrise) parts.push(`<i class="fa fa-sun wx-sky wx-sky--sun" aria-hidden="true"></i> Amanece ${esc(day.sunrise)}`);
        if (day.sunset) parts.push(`<i class="fa fa-moon wx-sky wx-sky--cloud" aria-hidden="true"></i> Anochece ${esc(day.sunset)}`);
        return parts.join(' · ');
    }

    function hoursHtml(day, hours) {
        const head = `<div class="hm-wx-day-head"><b>Hora a hora</b><span class="dt-muted">${sunLine(day)}</span></div>`;
        if (!hours.length) {
            return `<div class="hm-wx-day">${head}<div class="dt-muted">AEMET solo da la previsión por horas de los próximos dos días.</div></div>`;
        }
        const mixed = hours.some(h => h.date && h.date !== day.date);
        const dayLabel = mixed ? '<span class="wx-row-day"><i class="fa fa-calendar-day"></i>Día</span>' : '';
        return `<div class="hm-wx-day">
            ${head}
            <div class="wx-hours" role="region" tabindex="0" aria-label="${esc(hourAria(day, hours))}">
                <div class="wx-h-labels" aria-hidden="true">
                    ${dayLabel}
                    <span class="wx-row-hr"><i class="fa fa-clock"></i>Hora</span>
                    <span class="wx-row-sky"><i class="fa fa-cloud-sun"></i>Cielo</span>
                    <span class="wx-row-temp"><i class="fa fa-temperature-half"></i>Temp.</span>
                    <span class="wx-row-wind"><i class="fa fa-wind"></i>Viento km/h</span>
                    <span class="wx-row-rain"><i class="fa fa-droplet"></i>Lluvia %</span>
                </div>
                ${hours.map(h => hourCell(h, mixed ? day.date : '')).join('')}
            </div>
        </div>`;
    }

    function dayBodyHtml(day, nextDay) {
        if (!day) return '';
        const hours = displayHours(day, nextDay);
        return summaryHtml(day, hours) + hoursHtml(day, hours);
    }

    // ── Selector de día ────────────────────────────────────────────
    function dayName(day, today) {
        return day.date === today ? 'Hoy' : day.label.split(' ')[0];
    }

    function tabsHtml(muni, activeIdx) {
        const today = AgroWeather.localDate();
        const first = muni.startIdx;
        return muni.daily.slice(first, first + 7).map((d, n) => {
            const i = first + n;
            const t = treatmentOf(d.level);
            const prob = d.max_precipitation_probability || 0;
            const active = i === activeIdx;
            const aria = `${d.label}: máxima ${fmtTemp(d.max_temp)}, lluvia ${prob} %, ${t.label}`;
            return `<button type="button" class="wx-tab wx-tab--${t.key}${active ? ' active' : ''}" data-day-idx="${i}" aria-label="${esc(aria)}" aria-pressed="${active}">
                <span class="wx-tab-name">${esc(dayName(d, today))}</span>
                ${skyIcon(d.icon)}
                <b>${fmtTemp(d.max_temp)}</b>
                <small>${fmtTemp(d.min_temp)}</small>
                <em class="${rainTone(prob)}"><i class="fa fa-droplet" aria-hidden="true"></i>${prob}%</em>
            </button>`;
        }).join('');
    }

    // ── Tarjeta del municipio ──────────────────────────────────────
    function updatedHtml(muni) {
        const note = AgroWeather.updatedNote(muni);
        if (!note) return '';
        return muni.stale
            ? `<div class="mt-1"><span class="dt-status dt-tone-1"><i class="fa fa-triangle-exclamation me-1" aria-hidden="true"></i>${esc(note)}</span></div>`
            : ` · ${esc(note)}`;
    }

    function chipsHtml(fields) {
        return fields.map(f => `<a class="pl-chip" href="/parcelas/${esc(f.id)}/" title="${esc(f.crop)} · ${esc(f.area)} ha">
                <i class="fa fa-seedling" aria-hidden="true"></i>${esc(f.name)}
            </a>`).join('');
    }

    const LEGEND_HTML = `<div class="hm-legend" aria-hidden="true">
        <span><i class="hm-sw hm-sw--ok"></i>Buena: viento ≤ 20 km/h y lluvia &lt; 20 %</span>
        <span><i class="hm-sw hm-sw--warn"></i>Dudosa</span>
        <span><i class="hm-sw hm-sw--bad"></i>Mala: viento &gt; 25 km/h o lluvia ≥ 50 %</span>
        <span class="ms-md-auto">Fuente: AEMET</span>
    </div>`;

    // Todos los días guardados son pasados (datos antiguos): no se presenta ninguno como hoy
    const PAST_HTML = `<div class="hm-empty" role="status">
        <span class="hm-empty-icon hm-empty-icon--warn"><i aria-hidden="true" class="fa fa-clock-rotate-left"></i></span>
        <b>Previsión caducada</b>
        <span>Los datos guardados son de días ya pasados. Se actualizarán cuando AEMET vuelva a responder.</span>
    </div>`;

    function buildCard(muni) {
        const cardId = ++cardCounter;
        cards[cardId] = muni;
        const stale = muni.stale ? updatedHtml(muni) : '';
        const fresh = muni.stale ? '' : updatedHtml(muni);
        return `<section class="card card-flat" data-card-id="${cardId}" aria-label="Tiempo en ${esc(muni.name)}">
            <div class="dt-card-head">
                <div>
                    <h2 class="dt-card-title">${esc(muni.name)}</h2>
                    <div class="dt-muted">${plural(muni.fields.length, 'parcela')}${fresh}</div>
                    ${stale}
                </div>
            </div>
            ${muni.allPast ? PAST_HTML : `<div class="wx-days-wrap">
                <div class="wx-days" role="group" aria-label="Día de la previsión">${tabsHtml(muni, muni.startIdx)}</div>
            </div>
            <div data-wx-body aria-live="polite">${dayBodyHtml(muni.daily[muni.startIdx], muni.daily[muni.startIdx + 1])}</div>`}
            ${LEGEND_HTML}
            <div class="wx-parcels">${chipsHtml(muni.fields)}</div>
        </section>`;
    }

    // Al elegir un día: pestaña activa y resumen + horas de ese día
    function selectDay(card, dayEl) {
        const muni = cards[card.dataset.cardId];
        const idx = Number.parseInt(dayEl.dataset.dayIdx, 10);
        const day = muni?.daily[idx];
        if (!day) return;
        card.querySelectorAll('[data-day-idx]').forEach(tab => {
            const active = tab === dayEl;
            tab.classList.toggle('active', active);
            tab.setAttribute('aria-pressed', String(active));
        });
        card.querySelector('[data-wx-body]').innerHTML = dayBodyHtml(day, muni.daily[idx + 1]);
    }

    function onGridClick(event) {
        const dayEl = event.target.closest('[data-day-idx]');
        const card = dayEl?.closest('[data-card-id]');
        if (card) selectDay(card, dayEl);
    }

    // ── Carga y errores ────────────────────────────────────────────
    function friendlyError(status, msg) {
        if (msg && msg.length < 120) return msg;   // el servidor ya lo explica
        if (status === 401) return 'Tu sesión ha caducado. Vuelve a entrar.';
        return 'No se ha podido cargar la previsión. Inténtalo en unos minutos.';
    }

    function errorItemsHtml(errors) {
        const grouped = {};
        errors.forEach(({ name, reason }) => {
            if (!grouped[reason]) grouped[reason] = [];
            grouped[reason].push(name);
        });
        return Object.entries(grouped)
            .map(([reason, names]) => `<li><strong>${esc(names.join(', '))}</strong> — ${esc(reason)}</li>`)
            .join('');
    }

    // Mismo patrón que Inicio cuando no hay previsión: aviso con icono ámbar dentro de la tarjeta
    function emptyCardHtml(title, text, extra = '') {
        return `<section class="card card-flat" aria-label="El tiempo" role="status">
            <div class="hm-empty">
                <span class="hm-empty-icon hm-empty-icon--warn"><i aria-hidden="true" class="fa fa-cloud-sun"></i></span>
                <b>${title}</b>
                <span>${text}</span>
                ${extra}
            </div>
        </section>`;
    }

    function failedCardHtml(errors) {
        const retry = '<button type="button" class="btn btn-outline-secondary mt-2 wov-retry"><i class="fa fa-rotate-right me-1" aria-hidden="true"></i>Reintentar</button>';
        return emptyCardHtml('Sin previsión por ahora', 'No se pudo obtener la previsión del tiempo en este momento.',
            `<ul class="mb-0 ps-3 small text-start">${errorItemsHtml(errors)}</ul>${retry}`);
    }

    function partialErrorsHtml(errors) {
        const which = errors.length === 1 ? 'esta parcela' : 'algunas parcelas';
        return `<div class="dt-tone-1 rounded-3 px-3 py-2 small" role="status">
            <div class="fw-semibold"><i class="fa fa-triangle-exclamation me-1" aria-hidden="true"></i>No se pudo cargar la previsión de ${which}:</div>
            <ul class="mb-0 ps-3">${errorItemsHtml(errors)}</ul>
        </div>`;
    }

    const EMPTY_HTML = emptyCardHtml('Sin datos de tus parcelas',
        'No se obtuvieron datos de ninguna parcela. Comprueba que las parcelas tienen contorno definido en el mapa.');

    const RENDER_ERROR_HTML = `<div class="dt-tone-0 rounded-3 px-3 py-2" role="alert">
        <i class="fa fa-bug me-1" aria-hidden="true"></i>No se ha podido mostrar la previsión. Recarga la página y, si sigue, avisa al administrador.
    </div>`;

    function render(grid, munis, errors) {
        hideSkeleton();
        if (!munis.length && !errors.length) {
            grid.innerHTML = EMPTY_HTML;
        } else if (!munis.length) {
            grid.innerHTML = failedCardHtml(errors);
        } else {
            grid.innerHTML = munis.map(buildCard).join('') + (errors.length ? partialErrorsHtml(errors) : '');
        }
        document.getElementById('wov-subtitle').textContent = munis.length
            ? `${plural(munis.length, 'municipio')} · AEMET`
            : 'Sin datos disponibles';
    }

    function hideSkeleton() {
        const skeleton = document.getElementById('wov-skeletons');
        skeleton.classList.add('d-none');
        skeleton.setAttribute('aria-busy', 'false');
    }

    // El servidor agrupa las parcelas por municipio y guarda la previsión en caché: una sola llamada.
    // `startIdx`: el día que se enseña al abrir (hoy; si no hay, el primero que traiga)
    function toMunicipalities(data, fields) {
        const fieldById = Object.fromEntries(fields.map(f => [f.id, f]));
        const today = AgroWeather.localDate();
        return (data.municipalities || [])
            .map(m => {
                const idx = m.daily.findIndex(d => d.date >= today);
                return {
                    ...m,
                    fields: m.fields.map(f => fieldById[f.id] || f),
                    startIdx: Math.max(idx, 0),
                    allPast: idx < 0,
                };
            })
            .sort((a, b) => a.name.localeCompare(b.name));
    }

    // [{name, reason}] a partir de los errores del servidor ({reason, fields: [nombres]})
    function errorsFrom(data) {
        return (data.errors || []).flatMap(e => e.fields.map(name => ({ name, reason: e.reason })));
    }

    function start() {
        const grid = document.getElementById('wov-grid');
        const fieldsEl = document.getElementById('wov-fields');
        if (!grid || !fieldsEl) return Promise.resolve();
        const fields = JSON.parse(fieldsEl.textContent);
        if (!grid.dataset.wovBound) {   // start() puede llamarse más de una vez: un solo listener
            grid.dataset.wovBound = '1';
            grid.addEventListener('click', onGridClick);
        }
        if (!retryBound) {
            retryBound = true;
            document.addEventListener('click', e => { if (e.target.closest('.wov-retry')) globalThis.location.reload(); });
        }
        // then(ok, fallo) y no catch: un error al pintar no debe disfrazarse de fallo de AEMET
        return AgroWeather.load(grid.dataset.url).then(
            data => render(grid, toMunicipalities(data, fields), errorsFrom(data)),
            e => {
                const reason = friendlyError(e.status, e.msg);
                render(grid, [], fields.map(f => ({ name: f.name, reason })));
            })
            .catch(err => {   // fallo nuestro al pintar: se ve en consola y el usuario no se queda con la carga
                console.error(err);
                hideSkeleton();
                grid.innerHTML = RENDER_ERROR_HTML;
            });
    }

    globalThis.AgroWeatherOverview = { start, hourCell, displayHours };
    start();
})();
