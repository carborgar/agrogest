// Previsión del tiempo: carga y utilidades comunes a Inicio y El Tiempo.
// Los umbrales viven en el servidor (weather/treatment_rules.py): cada día y cada hora traen
// ya su `level` ('ok' | 'warn' | 'bad') y su `wind_level` (0-3). Aquí no se repiten.
window.AgroWeather = (function () {
    const pad = (n) => String(n).padStart(2, '0');

    // Fecha local YYYY-MM-DD (toISOString usa UTC: entre las 00:00 y las 02:00 daría el día anterior)
    function localDate(d = new Date()) {
        return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
    }

    function hourOf(h) {
        return parseInt(h.hour, 10);
    }

    // Horas que aún sirven: las de hoy a partir de la actual; las de otros días, todas
    function upcomingHours(day, now = new Date()) {
        const hours = day.hours || [];
        if (day.date !== localDate(now)) return hours;
        return hours.filter(h => hourOf(h) >= now.getHours());
    }

    // Tramos de horas seguidas aptas para tratar: [{from: 15, to: 19}] = de 15:00 a 19:00
    function okWindows(hours) {
        const windows = [];
        let current = null;
        hours.forEach(h => {
            const hr = hourOf(h);
            if (h.level === 'ok' && current && hr === current.to) {
                current.to = hr + 1;
            } else if (h.level === 'ok') {
                current = { from: hr, to: hr + 1 };
                windows.push(current);
            } else {
                current = null;
            }
        });
        return windows;
    }

    // GET al resumen por municipio. Si falla, lanza {status, msg} para que cada pantalla lo explique.
    async function load(url) {
        const res = await fetch(url, { headers: { 'Accept': 'application/json' } });
        let data = {};
        try { data = await res.json(); } catch (e) { /* respuesta sin JSON */ }
        if (!res.ok) throw { status: res.status, msg: data.error };
        return data;
    }

    // De cuándo es la previsión: «Actualizado a las 10:42» (hoy) o «Actualizado el 28 oct, 18:05».
    // Si AEMET ha fallado, el servidor manda la última buena con `stale: true` y se avisa.
    function updatedNote(muni, now = new Date()) {
        if (!muni.updated_at) return '';
        const d = new Date(muni.updated_at);
        const time = `${pad(d.getHours())}:${pad(d.getMinutes())}`;
        const when = localDate(d) === localDate(now)
            ? `a las ${time}`
            : `el ${d.getDate()} ${d.toLocaleString('es-ES', { month: 'short' }).replace('.', '')}, ${time}`;
        return muni.stale ? `Sin datos nuevos de AEMET · actualizado ${when}` : `Actualizado ${when}`;
    }

    return { localDate, hourOf, upcomingHours, okWindows, load, updatedNote };
})();
