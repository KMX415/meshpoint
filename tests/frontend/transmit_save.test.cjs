const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function setup(result) {
    const window = {};
    vm.runInNewContext(fs.readFileSync(path.resolve(__dirname,
        '../../frontend/js/configuration/transmit_card.js'), 'utf8'), { window });
    const calls = [], restarts = [], elements = new Map();
    const root = {
        innerHTML: '',
        querySelector(selector) {
            const attribute = selector.slice(1, -1);
            // Missing controls must return null, as they do in the browser.
            if (!this.innerHTML.includes(attribute)) return null;
            if (!elements.has(selector)) elements.set(selector, {
                _value: '', get value() { return this._value; },
                set value(v) { this._value = String(v); },
                checked: false, dataset: {}, textContent: '',
                addEventListener() {},
            });
            return elements.get(selector);
        },
    };
    const card = new window.TransmitConfigCard({
        async put(url, payload) {
            calls.push({ url, payload: JSON.parse(JSON.stringify(payload)) });
            if (result instanceof Error) throw result;
            return result;
        },
        signalRestart(message) { restarts.push(message); },
    });
    card.mount(root);
    card.render({ transmit: { enabled: true, tx_power_dbm: 17,
        max_duty_cycle_percent: 1, relay: { enabled: false, max_relay_per_minute: 12 } } });
    return { card, calls, restarts, status: elements.get('[data-tx-status]') };
}

test('saving visible TX settings succeeds without absent relay filter controls', async () => {
    const { card, calls, restarts, status } = setup({ saved: true, restart_required: true });
    await card._onSubmit({ preventDefault() {} });
    assert.deepEqual(calls, [{ url: '/api/config/transmit', payload: {
        enabled: true, tx_power_dbm: 17, max_duty_cycle_percent: 1,
        relay: { enabled: false, max_relay_per_minute: 12 },
    } }]);
    assert.equal(status.dataset.kind, 'success');
    assert.equal(status.textContent, 'Saved.');
    assert.deepEqual(restarts, ['Transmit settings updated.']);
});

for (const [name, result] of [['failed response', null], ['request rejection', new Error('offline')]]) {
    test(`${name} leaves an error instead of Saving and does not signal restart`, async () => {
        const { card, calls, restarts, status } = setup(result);
        await card._onSubmit({ preventDefault() {} });
        assert.equal(calls.length, 1);
        assert.equal(status.dataset.kind, 'error');
        assert.equal(status.textContent, 'Transmit save failed.');
        assert.deepEqual(restarts, []);
    });
}