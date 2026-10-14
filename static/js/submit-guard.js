/**
 * Submit guard global: evita envíos duplicados de formularios POST.
 * - Cubre envío nativo (evento submit) y form.submit() programático.
 * - Respeta validaciones de página (e.defaultPrevented).
 * - Opt-out: añadir el atributo data-no-guard al <form>.
 */
(function () {
    'use strict';

    const SUBMIT_SELECTOR = 'button[type="submit"], button:not([type]), input[type="submit"]';

    function isGuarded(form) {
        return form instanceof HTMLFormElement
            && (form.getAttribute('method') || 'get').toLowerCase() === 'post'
            && !form.hasAttribute('data-no-guard');
    }

    function submitButtons(form) {
        // form.elements incluye también botones fuera del form con atributo form="id"
        return Array.from(form.elements).filter(el => el.matches(SUBMIT_SELECTOR));
    }

    function lock(form, submitter) {
        form.dataset.submitting = '1';

        // Feedback visual en el botón pulsado
        if (submitter && submitter.tagName === 'BUTTON') {
            submitter.dataset.originalHtml = submitter.innerHTML;
            submitter.style.minWidth = submitter.offsetWidth + 'px';
            submitter.innerHTML =
                '<span class="spinner-border spinner-border-sm me-1" aria-hidden="true"></span>' +
                (submitter.textContent.trim() || '');
        }

        // Deshabilitar en el siguiente tick: si se hace síncrono, el navegador
        // no enviaría el name/value del botón pulsado.
        setTimeout(() => submitButtons(form).forEach(btn => { btn.disabled = true; }), 0);
    }

    function unlock(form) {
        delete form.dataset.submitting;
        submitButtons(form).forEach(btn => {
            btn.disabled = false;
            if (btn.dataset.originalHtml !== undefined) {
                btn.innerHTML = btn.dataset.originalHtml;
                btn.style.minWidth = '';
                delete btn.dataset.originalHtml;
            }
        });
    }

    // 1) Envío nativo
    document.addEventListener('submit', function (e) {
        const form = e.target;
        if (!isGuarded(form) || e.defaultPrevented) return;
        if (form.dataset.submitting) {
            e.preventDefault();
            return;
        }
        lock(form, e.submitter);
    });

    // 2) form.submit() programático (no dispara el evento submit)
    const nativeSubmit = HTMLFormElement.prototype.submit;
    HTMLFormElement.prototype.submit = function () {
        if (isGuarded(this)) {
            if (this.dataset.submitting) return;
            lock(this, null);
            if (typeof window.showLoading === 'function'
                && !(window.Swal && window.Swal.isVisible())) {
                window.showLoading('Procesando...');
            }
        }
        return nativeSubmit.call(this);
    };

    // 3) Volver con el botón "atrás" (bfcache): restaurar estado
    window.addEventListener('pageshow', function (e) {
        if (!e.persisted) return;
        document.querySelectorAll('form[data-submitting]').forEach(unlock);
        if (window.Swal && window.Swal.isVisible()) window.Swal.close();
    });
})();
