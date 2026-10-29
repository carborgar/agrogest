// Página «El Tiempo»: una tarjeta por municipio con la semana, el detalle por horas y sus parcelas.
// Necesita weather.js (AgroWeather) y en la página: #wov-grid (con data-url), #wov-skeletons,
// #wov-subtitle y el JSON de parcelas en #wov-fields.
(function () {
    const SUN_ICON = '<i class="fa fa-sun" style="color:#ffc107"></i>';
    const MOON_ICON = '<i class="fa fa-moon" style="color:#7c9bcc"></i>';
    const SUN_MARKS = [['sunrise', SUN_ICON], ['sunset', MOON_ICON]];
    const WIND_COLORS = ['#43a047', '#f9a825', '#fd7e14', '#dc3545'];
    const TREATMENT = {
        ok: { cls: 'muni-treatment-ok', icon: 'fa-check', label: 'Apto tratar', color: '#198754' },
        bad: { cls: 'muni-treatment-bad', icon: 'fa-xmark', label: 'Adverso', color: '#dc3545' },
        warn: { cls: 'muni-treatment-warn', icon: 'fa-exclamation', label: 'Precaución', color: '#cc8800' },
    };
    // Color de la probabilidad de lluvia en el resumen: sin lluvia, posible, probable (≥ 50 %)
    const SUMMARY_RAIN_STYLE = { none: 'opacity:.35;font-weight:400', low: 'color:#0d6efd;font-weight:600', high: 'color:#dc3545;font-weight:600' };
    const HOURLY_LEGEND = `<div class="muni-hourly-legend">
        <span><i class="fa fa-wind" style="color:#43a047"></i> ≤10</span>
        <span><i class="fa fa-wind" style="color:#f9a825"></i> 11–15</span>
        <span><i class="fa fa-wind" style="color:#fd7e14"></i> 16–20</span>
        <span><i class="fa fa-wind" style="color:#dc3545"></i> &gt;20 km/h</span>
        <span class="leg-sep">│</span>
        <span><i class="fa fa-cloud-rain" style="color:#0d6efd;opacity:.7"></i> % · L/m²</span>
        <span style="margin-left:auto;opacity:.6"><i class="fa fa-satellite-dish me-1"></i>Fuente: AEMET</span>
    </div>`;

    const cards = {};   // cardId → municipio (con sus días)
    let cardCounter = 0;

    // ── Utilidades ─────────────────────────────────────────────────
    function esc(value) {
        return String(value ?? '').replace(/[&<>"']/g, c => `&#${c.codePointAt(0)};`);
    }

    function plural(n, word) {
        return `${n} ${word}${n === 1 ? '' : 's'}`;
    }

    function fmtTemp(t, fallback = '—') {
        return t == null ? fallback : `${Math.round(t)}°`;
    }

    function rainTone(prob) {
        if (prob === 0) return 'none';
        return prob >= 50 ? 'high' : 'low';
    }

    function treatmentOf(level) {
        return TREATMENT[level] || TREATMENT.warn;
    }

    function timeToMinutes(t) {
        if (!t) return 0;
        const [hours, minutes] = t.split(':');
        return Number.parseInt(hours, 10) * 60 + (Number.parseInt(minutes, 10) || 0);
    }

    function skyClass(icon) {
        if (!icon) return 'sky-default';
        if (icon.includes('bolt') || icon.includes('storm')) return 'sky-storm';
        if (icon.includes('snow')) return 'sky-snow';
        if (icon.includes('rain') || icon.includes('drizzle') || icon.includes('showers')) return 'sky-rain';
        if (icon.includes('smog') || icon.includes('fog')) return 'sky-fog';
        if (icon === 'fa-cloud-sun') return 'sky-clear';
        if (icon.includes('cloud')) return 'sky-cloudy';
        if (icon.includes('sun')) return 'sky-clear';
        return 'sky-default';
    }

    // «<icono> 08:12 <icono> 18:41» con lo que traiga el día
    function sunTimes(day, separator = '') {
        return SUN_MARKS.filter(([key]) => day[key])
            .map(([key, icon]) => '<span>' + icon + separator + esc(day[key]) + '</span>')
            .join('');
    }

    // ── Cabecera de la tarjeta (cambia con el día elegido) ─────────
    function treatmentBadge(day) {
        if (!day) return '';
        const t = treatmentOf(day.level);
        return `<span class="muni-treatment-badge ${t.cls}"><i class="fa ${t.icon} me-1"></i>${t.label}</span>`;
    }

    function updatedLine(muni) {
        const note = AgroWeather.updatedNote(muni);
        if (!note) return '';
        const content = muni.stale
            ? '<span class="badge text-bg-warning text-wrap text-start"><i class="fa fa-triangle-exclamation me-1"></i>' + esc(note) + '</span>'
            : esc(note);
        return `<div class="muni-fields-label">${content}</div>`;
    }

    function dayPills(day) {
        if (!day) return '';
        return `<span class="muni-pill"><i class="fa fa-wind"></i>${day.max_wind_speed ?? '—'} km/h</span>`
            + `<span class="muni-pill"><i class="fa fa-droplet"></i>${day.max_precipitation_probability ?? 0}%</span>`;
    }

    function heroHtml(muni, day) {
        const icon = day ? day.icon : '';
        const minT = day ? fmtTemp(day.min_temp, '') : '';
        const minHtml = minT ? `<span class="muni-temp-min">${minT}</span>` : '';
        return `<div class="muni-hero ${skyClass(icon)}">
            <div class="muni-hero-bg-icon"><i class="fa ${icon || 'fa-cloud'}"></i></div>
            <div class="muni-name"><i class="fa fa-location-dot me-1" style="opacity:.7"></i>${esc(muni.name)}</div>
            <div class="muni-fields-label">${plural(muni.fields.length, 'parcela')}</div>
            ${updatedLine(muni)}
            <div class="muni-temp-row">
                <span class="muni-temp-max">${day ? fmtTemp(day.max_temp) : '—'}</span>
                ${minHtml}
            </div>
            <div class="muni-condition">${esc(day ? day.label_weather : '')}</div>
            <div class="muni-badge-row">${dayPills(day)}</div>
            ${treatmentBadge(day)}
        </div>`;
    }

    // ── Semana ─────────────────────────────────────────────────────
    function weekDayTemp(d) {
        // Sin mínima, AEMET no ha dado temperaturas fiables para ese día
        if (d.min_temp == null) return '<div class="muni-week-day-temp">—</div>';
        return `<div class="muni-week-day-temp">${fmtTemp(d.max_temp)} <span style="opacity:.6">${fmtTemp(d.min_temp)}</span></div>`;
    }

    function weekDayRain(d) {
        const prob = d.max_precipitation_probability || 0;
        const probHtml = `<div class="muni-week-day-prob rain-${rainTone(prob)}">`
            + `<i class="fa fa-droplet" style="font-size:.58rem;margin-right:.1rem"></i>${prob}%</div>`;
        if (prob === 0) return probHtml;
        // Los L/m² solo vienen en la previsión horaria (~48 h); para días lejanos, «—»
        const mmHtml = d.total_precipitation > 0
            ? `<div class="muni-week-day-mm">${d.total_precipitation} L/m²</div>`
            : '<div class="muni-week-day-mm unknown">— L/m²</div>';
        return probHtml + mmHtml;
    }

    function weekHtml(daily, cardId) {
        if (!daily.length) return '';
        const days = daily.slice(0, 7).map((d, i) => `
            <div class="muni-week-day${i === 0 ? ' active' : ''}" data-day-idx="${i}" data-card-id="${cardId}">
                <div class="muni-week-day-name">${esc(d.label.split(' ')[0])}</div>
                <div class="muni-week-day-icon"><i class="fa ${d.icon}"></i></div>
                ${weekDayTemp(d)}
                ${weekDayRain(d)}
            </div>`);
        return `<div class="muni-week">${days.join('')}</div>`;
    }

    // ── Detalle por horas ──────────────────────────────────────────
    function summaryTemps(day, hours) {
        const temps = hours.map(h => h.temperature).filter(t => t != null);
        const maxT = day.max_temp ?? (temps.length ? Math.max(...temps) : null);
        const minT = day.min_temp ?? (temps.length ? Math.min(...temps) : null);
        return `<span><i class="fa fa-thermometer-half" style="opacity:.5"></i> ${fmtTemp(maxT)} / <span style="opacity:.6">${fmtTemp(minT)}</span></span>`;
    }

    function summaryRain(day) {
        const prob = day.max_precipitation_probability || 0;
        let mmHtml = '';
        if (prob > 0 && day.total_precipitation > 0) {
            mmHtml = ` <span style="opacity:.55">·</span> <span style="color:#0d6efd;font-size:.68rem">${day.total_precipitation} L/m²</span>`;
        } else if (prob > 0) {
            mmHtml = ' <span style="opacity:.55">·</span> <span style="opacity:.35;font-size:.68rem" title="AEMET no da los litros para más allá de 48 h">— L/m²</span>';
        }
        return `<span title="Probabilidad de lluvia · Litros esperados"><i class="fa fa-droplet" style="color:#0d6efd;opacity:.8"></i> `
            + `<span style="${SUMMARY_RAIN_STYLE[rainTone(prob)]}">${prob}%</span>${mmHtml}</span>`;
    }

    function summaryHtml(day, hours) {
        const t = treatmentOf(day.level);
        const sun = day.sunrise || day.sunset
            ? `<span style="margin-left:auto;opacity:.7">${sunTimes(day, ' ')}</span>`
            : '';
        return `<div class="muni-hourly-summary">
            ${summaryTemps(day, hours)}
            <span><i class="fa fa-wind" style="color:${WIND_COLORS[day.wind_level ?? 0]}"></i> ${day.max_wind_speed ?? 0} <small style="opacity:.6">km/h</small></span>
            ${summaryRain(day)}
            <span style="color:${t.color};font-weight:700"><i class="fa ${t.icon}-circle me-1"></i>${t.label}</span>
            ${sun}
        </div>`;
    }

    function sunCard(icon, time) {
        return `<div class="hr-card hr-card-sun"><span class="hr-sun-icon">${icon}</span><span class="hr-sun-lbl">${esc(time)}</span></div>`;
    }

    function hourCard(h) {
        const prob = h.precipitation_probability || 0;
        const probCls = prob >= 50 ? ' high' : '';
        const probEmpty = prob === 0 ? ' empty' : '';
        const tempCls = h.temperature == null ? ' no-data' : '';
        return `<div class="hr-card">
            <div class="hr-treat-dot ${h.level}"></div>
            <div class="hr-card-time">${h.hour}</div>
            <div class="hr-card-icon"><i class="fa ${h.icon}"></i></div>
            <div class="hr-card-temp${tempCls}">${fmtTemp(h.temperature)}</div>
            <div class="hr-rain-wrap">
                <div class="hr-rain-prob${probCls}${probEmpty}">${prob}%</div>
                <div class="hr-rain-bar-bg"><div class="hr-rain-bar-fill${probCls}" style="width:${Math.min(100, prob)}%"></div></div>
                <div class="hr-rain-mm">${h.precipitation > 0 ? h.precipitation + 'L' : ''}</div>
            </div>
            <div class="hr-card-wind">
                <i class="fa fa-wind hr-wind-icon lvl${h.wind_level ?? 0}"></i>
                <span>${h.wind_speed}<span class="hr-wind-kmh">km/h</span></span>
            </div>
        </div>`;
    }

    // Tarjetas de cada hora con el amanecer y el atardecer intercalados en su sitio
    function hourCards(day, hours) {
        const marks = SUN_MARKS.filter(([key]) => day[key])
            .map(([key, icon]) => ({ icon, time: day[key], minutes: timeToMinutes(day[key]), done: false }));
        const html = [];
        for (const h of hours) {
            const minutes = timeToMinutes(h.hour);
            marks.filter(m => !m.done && minutes >= m.minutes).forEach(m => {
                html.push(sunCard(m.icon, m.time));
                m.done = true;
            });
            html.push(hourCard(h));
        }
        marks.filter(m => !m.done).forEach(m => html.push(sunCard(m.icon, m.time)));
        return html.join('');
    }

    function hourlyBodyHtml(day) {
        const all = day.hours || [];
        if (!all.length) return '<p class="text-center text-muted small py-3">Sin datos horarios para este día.</p>';
        // Hoy, sin las horas pasadas (si no queda ninguna, se muestra el día entero)
        const upcoming = AgroWeather.upcomingHours(day);
        const hours = upcoming.length ? upcoming : all;
        return `${summaryHtml(day, hours)}
            <div class="muni-hourly-carousel">${hourCards(day, hours)}</div>
            ${HOURLY_LEGEND}`;
    }

    function hourlyPanelHtml(day) {
        if (!day) return '';
        return `<div class="muni-hourly-header">
                <span><i class="fa fa-clock me-1"></i>Previsión horaria — <span class="muni-hourly-day-label">${esc(day.label)}</span></span>
                <div class="muni-sun-info">${sunTimes(day)}</div>
            </div>
            <div class="muni-hourly-body">${hourlyBodyHtml(day)}</div>`;
    }

    // ── Tarjeta del municipio ──────────────────────────────────────
    function chipsHtml(fields) {
        return fields.map(f => `<a class="muni-field-chip" href="/parcelas/${f.id}/" title="${esc(f.crop)} · ${esc(f.area)} ha">
                <i class="fa fa-seedling me-1"></i>${esc(f.name)}
            </a>`).join('');
    }

    function buildCard(muni) {
        const cardId = ++cardCounter;
        cards[cardId] = muni;
        return `<div class="muni-card" data-card-id="${cardId}">
            ${heroHtml(muni, muni.today)}
            ${weekHtml(muni.daily, cardId)}
            <div class="muni-hourly-toggle-bar">
                <button type="button" class="muni-hourly-toggle" data-card-id="${cardId}">
                    <i class="fa fa-clock"></i> Ver previsión por horas <i class="fa fa-chevron-down ms-1 toggle-arrow"></i>
                </button>
            </div>
            <div class="muni-hourly-panel">${hourlyPanelHtml(muni.daily[0])}</div>
            <div class="muni-fields">${chipsHtml(muni.fields)}</div>
        </div>`;
    }

    function setHourlyOpen(card, open) {
        card.querySelector('.muni-hourly-panel').classList.toggle('open', open);
        const arrow = card.querySelector('.toggle-arrow');
        arrow.classList.toggle('fa-chevron-down', !open);
        arrow.classList.toggle('fa-chevron-up', open);
    }

    function toggleHourly(card) {
        setHourlyOpen(card, !card.querySelector('.muni-hourly-panel').classList.contains('open'));
    }

    // Al elegir un día: cabecera y detalle por horas de ese día, con el detalle abierto
    function selectDay(card, dayEl) {
        card.querySelectorAll('.muni-week-day').forEach(d => d.classList.toggle('active', d === dayEl));
        const muni = cards[card.dataset.cardId];
        const day = muni?.daily[Number.parseInt(dayEl.dataset.dayIdx, 10)];
        if (!day) return;
        card.querySelector('.muni-hero').outerHTML = heroHtml(muni, day);
        card.querySelector('.muni-hourly-panel').innerHTML = hourlyPanelHtml(day);
        setHourlyOpen(card, true);
    }

    function onGridClick(event) {
        const card = event.target.closest('.muni-card');
        if (!card) return;
        const dayEl = event.target.closest('.muni-week-day');
        if (dayEl) selectDay(card, dayEl);
        else if (event.target.closest('.muni-hourly-toggle')) toggleHourly(card);
    }

    // ── Carga y errores ────────────────────────────────────────────
    function friendlyError(status, msg) {
        if (msg && msg.length < 120) return msg;   // el servidor ya lo explica
        if (status === 401) return 'Tu sesión ha caducado. Vuelve a entrar.';
        return 'No se ha podido cargar la previsión. Inténtalo en unos minutos.';
    }

    function errorsAlertHtml(errors, allFailed) {
        const grouped = {};
        errors.forEach(({ name, reason }) => {
            if (!grouped[reason]) grouped[reason] = [];
            grouped[reason].push(name);
        });
        const items = Object.entries(grouped)
            .map(([reason, names]) => `<li><strong>${esc(names.join(', '))}</strong> — ${esc(reason)}</li>`)
            .join('');
        const which = errors.length === 1 ? 'esta parcela' : 'algunas parcelas';
        const title = allFailed
            ? 'No se pudo obtener la previsión del tiempo en este momento.'
            : `No se pudo cargar la previsión de ${which}:`;
        const retry = allFailed
            ? `<div class="mt-2 text-center">
                   <button type="button" class="btn btn-sm btn-outline-warning wov-retry"><i class="fa fa-rotate-right me-1"></i>Reintentar</button>
               </div>`
            : '';
        return `<div class="col-12">
            <div class="alert alert-warning d-flex gap-3 align-items-start mb-0">
                <i class="fa fa-cloud-slash fa-lg flex-shrink-0 mt-1 text-warning"></i>
                <div class="w-100">
                    <div class="fw-semibold mb-1">${title}</div>
                    <ul class="mb-1 ps-3 small">${items}</ul>
                    ${retry}
                </div>
            </div>
        </div>`;
    }

    const EMPTY_HTML = `<div class="col-12">
        <div class="alert alert-secondary mb-0">
            <i class="fa fa-triangle-exclamation me-2"></i>
            No se obtuvieron datos de ninguna parcela. Comprueba que las parcelas tienen contorno definido en el mapa.
        </div>
    </div>`;

    const RENDER_ERROR_HTML = `<div class="col-12">
        <div class="alert alert-danger mb-0">
            <i class="fa fa-bug me-2"></i>No se ha podido mostrar la previsión. Recarga la página y, si sigue, avisa al administrador.
        </div>
    </div>`;

    function render(grid, munis, errors) {
        document.getElementById('wov-skeletons').classList.add('d-none');
        if (!munis.length && !errors.length) {
            grid.innerHTML = EMPTY_HTML;
        } else {
            grid.innerHTML = munis.map(m => `<div class="col-12 col-sm-6 col-xl-4">${buildCard(m)}</div>`).join('')
                + (errors.length ? errorsAlertHtml(errors, !munis.length) : '');
        }
        document.getElementById('wov-subtitle').textContent = munis.length
            ? `${plural(munis.length, 'municipio')} · AEMET`
            : 'Sin datos disponibles';
    }

    // El servidor agrupa las parcelas por municipio y guarda la previsión en caché: una sola llamada
    function toMunicipalities(data, fields) {
        const fieldById = Object.fromEntries(fields.map(f => [f.id, f]));
        const today = AgroWeather.localDate();
        return (data.municipalities || [])
            .map(m => ({
                ...m,
                fields: m.fields.map(f => fieldById[f.id] || f),
                today: m.daily.find(d => d.date >= today) || m.daily[0] || null,
            }))
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
        grid.addEventListener('click', onGridClick);
        document.addEventListener('click', e => { if (e.target.closest('.wov-retry')) globalThis.location.reload(); });
        // then(ok, fallo) y no catch: un error al pintar no debe disfrazarse de fallo de AEMET
        return AgroWeather.load(grid.dataset.url).then(
            data => render(grid, toMunicipalities(data, fields), errorsFrom(data)),
            e => {
                const reason = friendlyError(e.status, e.msg);
                render(grid, [], fields.map(f => ({ name: f.name, reason })));
            })
            .catch(err => {   // fallo nuestro al pintar: se ve en consola y el usuario no se queda con la carga
                console.error(err);
                document.getElementById('wov-skeletons').classList.add('d-none');
                grid.innerHTML = RENDER_ERROR_HTML;
            });
    }

    globalThis.AgroWeatherOverview = { start, skyClass, timeToMinutes, hourCards };
    start();
})();
