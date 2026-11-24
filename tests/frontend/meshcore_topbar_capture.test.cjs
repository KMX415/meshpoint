// Run with: node --test tests/frontend/meshcore_topbar_capture.test.cjs
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

test('MeshCore pill follows USB capture while native TX is disabled', () => {
    const elements = new Map();
    const makeElement = () => ({
        textContent: '',
        attributes: {},
        classList: { add() {}, remove() {} },
        setAttribute(name, value) { this.attributes[name] = value; },
    });
    for (const selector of [
        '.topbar-meshcore__name', '.topbar-meshcore__freq',
        '.topbar-meshcore__channel', '.topbar-meshcore__lamp',
    ]) elements.set(selector, makeElement());
    const group = { hidden: false };
    const chip = makeElement();
    chip.querySelector = selector => elements.get(selector);
    const window = {};
    const context = vm.createContext({ window });
    const script = path.resolve(__dirname, '../../frontend/topbar/topbar_meshcore_chip.js');
    vm.runInContext(fs.readFileSync(script, 'utf8'), context);
    const pill = new window.TopbarMeshcoreChip(group, chip);
    pill.setDashboardReachable(true);

    pill.setMeshcore({ companion_expected: true, connected: false, capture_connected: true });
    assert.equal(group.hidden, false);
    assert.equal(elements.get('.topbar-meshcore__name').textContent, 'Companion');
    assert.equal(elements.get('.topbar-meshcore__lamp').attributes['aria-label'], 'MeshCore companion connected');

    pill.setMeshcore({ companion_expected: true, connected: false, capture_connected: false });
    assert.equal(elements.get('.topbar-meshcore__name').textContent, 'No companion');
    assert.equal(elements.get('.topbar-meshcore__lamp').attributes['aria-label'], 'MeshCore companion offline');
});
