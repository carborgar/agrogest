document.addEventListener('DOMContentLoaded', function() {
    // Desktop Sidebar Toggle
    const desktopSidebar = document.querySelector('.desktop-sidebar');
    const mainContent = document.querySelector('.main-content');
    const sidebarToggleBtn = document.querySelector('.toggle-sidebar-btn');

    // Toggle sidebar on button click
    sidebarToggleBtn.addEventListener('click', function(e) {
        desktopSidebar.classList.toggle('compact');

        // Update content area width
        if (desktopSidebar.classList.contains('compact')) {
            mainContent.style.marginLeft = '70px';
            mainContent.style.width = 'calc(100% - 70px)';
        } else {
            mainContent.style.marginLeft = '240px';
            mainContent.style.width = 'calc(100% - 240px)';
        }

        // Disparar evento personalizado
        document.dispatchEvent(new Event('sidebar-toggled'));

    });

    // Set initial content width based on sidebar state
    if (window.innerWidth >= 992) {
        if (desktopSidebar.classList.contains('compact')) {
            mainContent.style.marginLeft = '70px';
            mainContent.style.width = 'calc(100% - 70px)';
        } else {
            mainContent.style.marginLeft = '240px';
            mainContent.style.width = 'calc(100% - 240px)';
        }
    }

    // Handle window resize
    window.addEventListener('resize', function() {
        if (window.innerWidth >= 992) {
            if (desktopSidebar.classList.contains('compact')) {
                mainContent.style.marginLeft = '70px';
                mainContent.style.width = 'calc(100% - 70px)';
            } else {
                mainContent.style.marginLeft = '240px';
                mainContent.style.width = 'calc(100% - 240px)';
            }
        } else {
            mainContent.style.marginLeft = '0';
            mainContent.style.width = '100%';
        }
    });

});

document.addEventListener('DOMContentLoaded', function() {
    const fullMenuToggle = document.getElementById('fullMenuToggle');
    const fullMenu = document.getElementById('fullMenu');
    const fullMenuClose = document.getElementById('fullMenuClose');

    // Mostrar menú completo
    fullMenuToggle.addEventListener('click', function() {
        fullMenu.classList.add('show');
    });

    // Cerrar menú completo
    fullMenuClose.addEventListener('click', function() {
        fullMenu.classList.remove('show');
    });

});
