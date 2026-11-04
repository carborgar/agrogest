document.addEventListener('DOMContentLoaded', function () {

    // ── 1. Sidebar collapse toggle ─────────────────────────────────────────

    const sidebarCollapseBtn = document.getElementById('sidebarCollapseBtn');
    const htmlEl = document.documentElement;
    const sidebar = document.getElementById('sidebarDesktop');
    const COOKIE_KEY = 'sidebar_collapsed';
    const COOKIE_EXPIRES = 365 * 24 * 60 * 60 * 1000; // 1 año

    function setCookie(name, value) {
        const expires = new Date(Date.now() + COOKIE_EXPIRES).toUTCString();
        document.cookie = `${name}=${value}; expires=${expires}; path=/; SameSite=Lax`;
    }

    // ── Tooltips del sidebar colapsado ────────────────────────────────────
    // Usamos Bootstrap Tooltip (se renderiza en <body>, sin clipping del nav)

    function initSidebarTooltips() {
        if (!sidebar) return;
        sidebar.querySelectorAll('.nav-link[data-label]').forEach(function (link) {
            if (link._sidebarTooltip) return;
            link._sidebarTooltip = new bootstrap.Tooltip(link, {
                title: link.dataset.label,
                placement: 'right',
                trigger: 'hover',
                container: 'body',
            });
        });
    }

    function syncTooltips(isCollapsed) {
        if (!sidebar) return;
        sidebar.querySelectorAll('.nav-link[data-label]').forEach(function (link) {
            const tt = link._sidebarTooltip;
            if (!tt) return;
            if (isCollapsed) {
                tt.enable();
            } else {
                tt.disable();
                tt.hide();
            }
        });
    }

    initSidebarTooltips();
    syncTooltips(htmlEl.classList.contains('sidebar-collapsed'));

    // ── 2. Plegado automático por debajo de xl ────────────────────────────
    // Por debajo del breakpoint xl de Bootstrap el lateral va siempre plegado
    // (el script de <head> lo aplica antes de pintar). Desde xl manda la
    // preferencia guardada en la cookie. El botón solo se ve desde xl.
    const xl = getComputedStyle(htmlEl).getPropertyValue('--bs-breakpoint-xl').trim() || '1200px';
    const wide = window.matchMedia('(min-width: ' + xl + ')');

    function savedCollapsed() {
        return document.cookie.split('; ').includes(COOKIE_KEY + '=true');
    }

    function applyWidth() {
        const collapsed = !wide.matches || savedCollapsed();
        htmlEl.classList.toggle('sidebar-collapsed', collapsed);
        syncTooltips(collapsed);
    }

    wide.addEventListener('change', applyWidth);

    if (sidebarCollapseBtn) {
        sidebarCollapseBtn.addEventListener('click', function () {
            const isNowCollapsed = htmlEl.classList.toggle('sidebar-collapsed');
            setCookie(COOKIE_KEY, isNowCollapsed);
            syncTooltips(isNowCollapsed);
        });
    }

});
