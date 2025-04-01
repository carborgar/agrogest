document.addEventListener('DOMContentLoaded', function() {
    const desktopSidebar = document.querySelector('.desktop-sidebar');
    const mainContent = document.querySelector('.main-content');
    const sidebarToggleBtn = document.querySelector('.toggle-sidebar-btn');
    const fullMenuToggle = document.getElementById('fullMenuToggle');
    const fullMenu = document.getElementById('fullMenu');
    const fullMenuClose = document.getElementById('fullMenuClose');

    function updateContentWidth() {
        if (window.innerWidth >= 992) {
            const isCompact = desktopSidebar.classList.contains('compact');
            const marginLeft = isCompact ? '70px' : '240px';
            mainContent.style.marginLeft = marginLeft;
            mainContent.style.width = `calc(100% - ${marginLeft})`;

            // Si es compacto, añadimos la clase al <html>, si no, la quitamos
            if (isCompact) {
                document.documentElement.classList.add('sidebar-collapsed');
            } else {
                document.documentElement.classList.remove('sidebar-collapsed');
            }

        } else {
            mainContent.style.marginLeft = '0';
            mainContent.style.width = '100%';
        }
    }

    sidebarToggleBtn.addEventListener('click', function() {
        const isCollapsed = desktopSidebar.classList.toggle('compact');
        document.cookie = `sidebar_collapsed=${isCollapsed}; path=/; SameSite=Lax; max-age=2147483647`;
        updateContentWidth();
        document.dispatchEvent(new Event('sidebar-toggled'));
    });

    window.addEventListener('resize', updateContentWidth);
    updateContentWidth(); // Aplicar el estado inicial correctamente

    fullMenuToggle.addEventListener('click', function() {
        fullMenu.classList.add('show');
    });

    fullMenuClose.addEventListener('click', function() {
        fullMenu.classList.remove('show');
    });
});
