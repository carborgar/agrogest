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

    if (sidebarCollapseBtn) {
        sidebarCollapseBtn.addEventListener('click', function () {
            const isNowCollapsed = htmlEl.classList.toggle('sidebar-collapsed');
            setCookie(COOKIE_KEY, isNowCollapsed);
            syncTooltips(isNowCollapsed);
        });

        // Cuando el sidebar está colapsado y el usuario hace clic en un ítem
        // con submenú: expandir el sidebar primero, luego abrir el submenú.
        if (sidebar) {
            sidebar.querySelectorAll('[data-bs-toggle="collapse"]').forEach(function (link) {
                link.addEventListener('click', function (e) {
                    if (htmlEl.classList.contains('sidebar-collapsed')) {
                        e.preventDefault();
                        e.stopPropagation();
                        // Expandir sidebar
                        htmlEl.classList.remove('sidebar-collapsed');
                        setCookie(COOKIE_KEY, false);
                        syncTooltips(false);
                        // Abrir el submenú tras la transición
                        const targetId = this.getAttribute('data-bs-target');
                        setTimeout(function () {
                            const target = document.querySelector(targetId);
                            if (target) {
                                bootstrap.Collapse.getOrCreateInstance(target, { toggle: false }).show();
                            }
                        }, 280);
                    }
                }, true); // capture phase — se ejecuta antes que Bootstrap
            });
        }
    }

});
