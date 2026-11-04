/**
 * Render seguro del Markdown del asistente.
 * Las respuestas se guardan y se repintan con innerHTML, así que no se confía en ellas:
 * - El HTML crudo (bloques e inline) se escapa, nunca se interpreta.
 * - Los enlaces solo admiten http:, https:, mailto: y # (el resto se queda como texto).
 * - Las imágenes no se cargan: se muestra su texto alternativo.
 * Sin dependencias: si `marked` no carga (mala cobertura en el campo) cae a texto plano.
 */
window.AgroChatMarkdown = (function () {
    'use strict';

    const SAFE_URL = /^(https?:|mailto:|#)/i;

    function escapeHtml(text) {
        return String(text)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    /** Convierte secuencias \uXXXX literales en sus caracteres (el modelo a veces las devuelve como texto). */
    function decodeUnicodeEscapes(str) {
        return str.replace(/\\u([0-9a-fA-F]{4})/g, (_, hex) => String.fromCharCode(parseInt(hex, 16)));
    }

    function safeHref(href) {
        // Se quitan espacios y caracteres de control: "java\nscript:" no debe esquivar la lista
        const clean = String(href || '').replace(/[\u0000- \u007f-\u009f]/g, '');
        return SAFE_URL.test(clean) ? clean : null;
    }

    function createRenderer(markedLib) {
        if (!markedLib || typeof markedLib.Marked !== 'function') {
            return (raw) => escapeHtml(decodeUnicodeEscapes(raw)).replace(/\n/g, '<br>');
        }
        const renderer = {
            html: (html) => escapeHtml(html),
            link(href, title, text) {
                const url = safeHref(href);
                if (url === null) return text;
                const titleAttr = title ? ` title="${escapeHtml(title)}"` : '';
                return `<a href="${escapeHtml(url)}"${titleAttr} target="_blank" rel="noopener noreferrer">${text}</a>`;
            },
            image: (href, title, text) => escapeHtml(text || ''),
        };
        const parser = new markedLib.Marked({ breaks: true, gfm: true, renderer });
        return (raw) => parser.parse(decodeUnicodeEscapes(raw));
    }

    return { createRenderer, escapeHtml, decodeUnicodeEscapes };
})();
