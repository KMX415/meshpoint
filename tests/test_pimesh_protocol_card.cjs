const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function harness(post) {
    let now = 0;
    let reloads = 0;
    const window = { location: { reload: () => reloads++ } };
    const context = vm.createContext({ window, Date: { now: () => now },
        setTimeout: (fn, delay) => { now += delay; fn(); } });
    vm.runInContext(fs.readFileSync(path.join(__dirname,
        '../frontend/js/configuration/pimesh_protocol_card.js'), 'utf8'), context);
    const card = new window.PimeshProtocolCard({ post });
    card._root = { isConnected: true, setAttribute() {} };
    card._select = { value: 'meshcore' };
    card._button = {};
    card._status = {};
    card._active = 'meshtastic';
    return { card, reloads: () => reloads };
}

for (const throws of [false, true]) {
    test(`uncertain POST (${throws ? 'exception' : 'null'}) observes without resubmitting`, async () => {
        let submissions = 0;
        const h = harness(async () => {
            submissions++;
            if (throws) throw new Error('service restarted');
            return null;
        });
        const states = [
            { active: 'meshtastic', switching: false, phase: 'ready' },
            { active: 'meshtastic', switching: true, phase: 'starting' },
            new Error('restarting'),
            { active: 'meshcore', switching: false, phase: 'ready', connected: true },
        ];
        h.card._readStatus = async () => {
            assert.equal(h.card._select.disabled, true);
            const state = states.shift();
            if (state instanceof Error) throw state;
            return state;
        };
        await h.card._switch();
        assert.equal(submissions, 1);
        assert.equal(h.reloads(), 1);
        assert.equal(states.length, 0);
    });
}

test('completed external switch remounts the backend', async () => {
    const h = harness();
    h.card._readStatus = async () => ({ active: 'meshcore', phase: 'ready', switching: false });
    await h.card._refresh();
    assert.equal(h.reloads(), 1);
});

test('unaccepted request settles without another POST or reload', async () => {
    let reads = 0;
    const h = harness(async () => null);
    h.card._readStatus = async () => {
        reads++;
        return { active: 'meshtastic', phase: 'ready', switching: false, connected: true };
    };
    await h.card._switch();
    assert.equal(reads, 4);
    assert.equal(h.reloads(), 0);
    assert.equal(h.card._busy, false);
});
