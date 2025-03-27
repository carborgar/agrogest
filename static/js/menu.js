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

    // Mobile Bottom Dock Interaction
    const dockItems = document.querySelectorAll('.dock-item');
    dockItems.forEach(item => {
        item.addEventListener('click', function() {
            dockItems.forEach(i => i.classList.remove('active'));
            this.classList.add('active');
        });
    });

    // Mobile Offcanvas with Page Slide Effect
    const mobileMenuTrigger = document.createElement('button');
    mobileMenuTrigger.innerHTML = '<i class="bi bi-list"></i>';
    mobileMenuTrigger.classList.add('mobile-menu-trigger');
    document.body.insertBefore(mobileMenuTrigger, document.body.firstChild);

    const mobileMenu = document.getElementById('mobileMenu');

    mobileMenuTrigger.addEventListener('click', function() {
        mobileMenu.classList.add('show');
        mainContent.classList.add('slide-right');
    });

    mobileMenu.querySelector('.btn-close').addEventListener('click', function() {
        mobileMenu.classList.remove('show');
        mainContent.classList.remove('slide-right');
    });

    // Close mobile menu when clicking outside
    document.addEventListener('click', function(e) {
        if (mobileMenu.classList.contains('show') &&
            !mobileMenu.contains(e.target) &&
            e.target !== mobileMenuTrigger) {
            mobileMenu.classList.remove('show');
            mainContent.classList.remove('slide-right');
        }
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