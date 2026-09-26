const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function harness(put) {
    const window = {};
    vm.runInNewContext(fs.readFileSync('frontend/js/configuration/pimesh_behavior_card.js', 'utf8'), { window });
    const card = new window.PimeshBehaviorCard({ put });
    card._protocol = 'meshcore';
    card._root = { setAttribute() {}, querySelector: () => ({}) };
    card._actual = { protocol: 'meshcore', mode: 'monitor', modes: ['monitor', 'forward', 'no_tx'] };
    card._role = { value: 'forward' };
    card._filter = {};
    card._save = { disabled: false };
    card._reload = {};
    card._status = {};
    card._show = actual => { card._actual = actual; };
    return { card, window };
}

test('uncertain save requires a reload and never resubmits automatically', async () => {
    let calls = 0;
    const { card } = harness(async () => { calls++; return null; });
    await card._submit();
    assert.equal(calls, 1);
    assert.equal(card._actual, null);
    assert.equal(card._save.disabled, true);
    assert.match(card._status.textContent, /unconfirmed/);
    await card._submit();
    assert.equal(calls, 1);
});

test('mismatched response cannot be reported as saved', async () => {
    const { card } = harness(async () => ({ protocol: 'meshcore', mode: 'monitor' }));
    await card._submit();
    assert.match(card._status.textContent, /unconfirmed/);
});

test('viewer cannot save and ordinary renders preserve edits', async () => {
    const { card, window } = harness(async () => { throw new Error('unexpected write'); });
    window.meshpointReadOnly = true;
    card._update();
    assert.equal(card._save.disabled, true);
    window.PlatformContext = { isPimesh: () => true };
    card.render({ device: { radio_protocol: 'meshcore' } });
    assert.equal(card._role.value, 'forward');
    await card._submit();
});

test('non-PiMesh render does not request backend state', () => {
    const { card, window } = harness();
    window.PlatformContext = { isPimesh: () => false };
    card._protocol = null;
    card._load = () => { throw new Error('unexpected read'); };
    card.render({});
    assert.equal(card._root.hidden, true);
});
