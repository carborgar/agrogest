document.addEventListener('DOMContentLoaded', function() {
    // Close offcanvas when clicking on nav links (mobile)
    document.querySelectorAll('#sidebarOffcanvas .nav-link').forEach(link => {
        link.addEventListener('click', function(e) {
            if (!this.hasAttribute('data-bs-toggle')) {
                const offcanvas = bootstrap.Offcanvas.getInstance(document.getElementById('sidebarOffcanvas'));
                if (offcanvas) {
                    offcanvas.hide();
                }
            }
        });
    });
});
