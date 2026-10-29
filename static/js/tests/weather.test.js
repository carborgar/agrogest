// Ejecutar con: npm run test:js
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const SCRIPT = fs.readFileSync(path.join(__dirname, '..', 'weather.js'), 'utf8');
const ctx = { window: {} };
vm.runInNewContext(SCRIPT, ctx);
const { updatedNote } = ctx.window.AgroWeather;

const NOW = new Date(2026, 9, 29, 12, 0);   // 29 oct 2026, 12:00 (hora local)
const at = (day, h, m) => new Date(2026, 9, day, h, m).toISOString();

test('hoy: solo la hora', () => {
    assert.equal(updatedNote({ updated_at: at(29, 9, 5) }, NOW), 'Actualizado a las 09:05');
});

test('otro día: día, mes y hora', () => {
    assert.equal(updatedNote({ updated_at: at(28, 18, 5) }, NOW), 'Actualizado el 28 oct, 18:05');
});

test('si AEMET falla se avisa', () => {
    assert.equal(updatedNote({ updated_at: at(29, 9, 5), stale: true }, NOW),
        'Sin datos nuevos de AEMET · actualizado a las 09:05');
});

test('sin fecha no se pinta nada', () => {
    assert.equal(updatedNote({}, NOW), '');
});
