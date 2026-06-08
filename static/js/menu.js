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

    // ── 2. Cerrar offcanvas al navegar (mobile) ────────────────────────────

    document.querySelectorAll('#sidebarOffcanvas .nav-link').forEach(function (link) {
        link.addEventListener('click', function () {
            if (!this.hasAttribute('data-bs-toggle')) {
                const offcanvasEl = document.getElementById('sidebarOffcanvas');
                const offcanvas = bootstrap.Offcanvas.getInstance(offcanvasEl);
                if (offcanvas) offcanvas.hide();
            }
        });
    });

    // ── 3. Swipe desde el borde izquierdo para abrir el offcanvas ──────────

    const SWIPE_EDGE    = 30;   // px desde el borde izquierdo para iniciar
    const SWIPE_MIN_X   = 60;   // distancia horizontal mínima
    let touchStartX = null;
    let touchStartY = null;

    document.addEventListener('touchstart', function (e) {
        if (e.touches.length !== 1) return;
        touchStartX = e.touches[0].clientX;
        touchStartY = e.touches[0].clientY;
    }, { passive: true });

    document.addEventListener('touchend', function (e) {
        if (touchStartX === null) return;
        const dx = e.changedTouches[0].clientX - touchStartX;
        const dy = Math.abs(e.changedTouches[0].clientY - touchStartY);

        // Solo swipe horizontal desde el borde izquierdo
        if (touchStartX <= SWIPE_EDGE && dx >= SWIPE_MIN_X && dy < dx * 1.2) {
            const offcanvasEl = document.getElementById('sidebarOffcanvas');
            if (offcanvasEl) {
                bootstrap.Offcanvas.getOrCreateInstance(offcanvasEl).show();
            }
        }
        touchStartX = null;
        touchStartY = null;
    }, { passive: true });

});
