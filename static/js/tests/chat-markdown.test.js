// Ejecutar con: npm run test:js
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { JSDOM } = require('jsdom');
const marked = require('marked');

const SCRIPT = fs.readFileSync(path.join(__dirname, '..', 'chat-markdown.js'), 'utf8');
const ctx = { window: {} };
vm.runInNewContext(SCRIPT, ctx);
const { createRenderer } = ctx.window.AgroChatMarkdown;
const render = createRenderer(marked);

const dom = (md) => new JSDOM(`<body>${render(md)}</body>`).window.document;

test('el HTML crudo (img onerror, script) queda como texto', () => {
    const doc = dom('Hola <img src=x onerror="alert(1)"> <script>alert(2)</script>\n\n<div onclick="x()">caja</div>');
    assert.equal(doc.querySelectorAll('img, script, div').length, 0);
    assert.match(doc.body.textContent, /<img src=x onerror=/);
});

test('enlaces javascript:, data: y vbscript: no generan <a>, ni con espacios o entidades', () => {
    for (const url of ['javascript:alert(1)', 'JaVaScRiPt:alert(1)', 'data:text/html,x', 'vbscript:x',
                       'java\tscript:alert(1)', 'java&#115;cript:alert(1)', '/relativo']) {
        const doc = dom(`[pincha](${url})`);
        assert.equal(doc.querySelectorAll('a').length, 0, url);
        assert.match(doc.body.textContent, /pincha/);
    }
});

test('enlaces http, https, mailto y # se admiten con rel y target seguros', () => {
    for (const url of ['http://a.es', 'https://a.es/x?y=1&z=2', 'mailto:a@b.es', '#seccion']) {
        const a = dom(`[ok](${url})`).querySelector('a');
        assert.ok(a, url);
        assert.equal(a.getAttribute('target'), '_blank');
        assert.equal(a.getAttribute('rel'), 'noopener noreferrer');
    }
});

test('un href con comillas no rompe el atributo', () => {
    const doc = dom('[x](https://a.es/"onmouseover="alert(1))');
    const a = doc.querySelector('a');
    if (a) assert.equal(a.hasAttribute('onmouseover'), false);
});

test('las imágenes markdown no se cargan: solo queda el texto alternativo', () => {
    const doc = dom('![logo](https://a.es/x.png) ![x](javascript:alert(1))');
    assert.equal(doc.querySelectorAll('img').length, 0);
    assert.match(doc.body.textContent, /logo/);
});

test('el Markdown normal sigue funcionando', () => {
    const doc = dom('**6 L**\n\n- uno\n- dos\n\n| a | b |\n|---|---|\n| 1 | 2 |');
    assert.equal(doc.querySelector('strong').textContent, '6 L');
    assert.equal(doc.querySelectorAll('li').length, 2);
    assert.equal(doc.querySelectorAll('td').length, 2);
});

test('sin marked cae a texto plano escapado con saltos de línea', () => {
    const plain = createRenderer(null);
    assert.equal(plain('a <b>\nc'), 'a &lt;b&gt;<br>c');
});
