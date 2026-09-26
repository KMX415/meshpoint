const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const read = file => fs.readFileSync(path.join(__dirname, '..', file), 'utf8');

test('Meshtastic chip visibility follows configured capture sources, not socket connectivity', async () => {
    let sources = [];
    let protocol = null;
    const elements = {};
    const element = () => ({textContent:'', setAttribute() {}, classList:{remove() {}, add() {}, toggle() {}}});
    const root = {...element(), hidden:true, querySelector: selector => elements[selector] ||= element()};
    const ctx = vm.createContext({document:{dispatchEvent() {}}, CustomEvent:class {},
        fetch:async () => ({ok:true, json:async () => ({capture:{sources}, device:{radio_protocol:protocol}, radio:{region:'US'}, transmit:{short_name:'TEST'}})})});
    ctx.window = ctx;
    ctx.PlatformContext = {
        isPimesh: () => protocol !== null,
        isNodePlatform: () => sources.includes('meshtasticd') || protocol !== null,
        meshtasticdRuntime: () => ({short_name:'HAT'}),
        meshtasticdConfig: () => ({}),
    };
    vm.runInContext(read('frontend/topbar/topbar_meshtastic_chip.js'), ctx);
    vm.runInContext(read('frontend/topbar/topbar_controller.js'), ctx);
    const chip = new ctx.TopbarMeshtasticChip(root);
    const controller = Object.create(ctx.TopbarController.prototype);
    controller._root = root;
    controller._meshtastic = chip;
    controller._meshcore = {setDashboardReachable() {}, setMeshcore() {}};
    controller._serial = {setDashboardReachable() {}, setSerial() {}};
    controller._syncPollCadence = () => {};
    for (const [configured, visible] of [[[],false], [['meshcore_usb'],false], [['mock'],false],
        [['concentrator'],true], [['serial'],true], [['meshtasticd'],true], [[],false]]) {
        sources = configured;
        await controller._refreshConfig();
        chip.setConnectionState('online');
        assert.equal(root.hidden, !visible, JSON.stringify(sources));
    }
    for (const active of ['meshtastic', 'meshcore', 'meshtastic']) {
        protocol = active;
        sources = active === 'meshtastic' ? ['meshtasticd'] : ['meshcore_usb'];
        await controller._refreshConfig();
        assert.equal(root.hidden, active !== 'meshtastic', active);
    }
});
