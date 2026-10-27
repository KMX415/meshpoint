const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function setup(pimesh, protocol = 'meshcore') {
    const mounts = [];
    const hosts = new Map();
    function element() {
        return { innerHTML: '', style: {}, querySelector() { return element(); } };
    }
    const document = { getElementById(id) {
        if (!hosts.has(id)) hosts.set(id, element());
        return hosts.get(id);
    } };
    const window = {};
    for (const name of ['PimeshProtocolCard', 'PimeshBehaviorCard', 'WismeshRadioCard',
        'MeshcoreConfigCard', 'ChannelsConfigCard', 'QuickDeployCard', 'TransmitConfigCard',
        'GpsConfigCard', 'PositionBroadcastCard', 'BroadcastStatusCard', 'RadioConfigEditCard',
        'NodeInfoConfigCard', 'TelemetryBroadcastCard']) {
        window[name] = class {
            constructor(api, options) { this.options = options; }
            mount() { mounts.push({ name, options: this.options }); }
        };
    }
    const context = vm.createContext({ window, document });
    for (const file of ['platform/platform_context.js', 'configuration/configuration_panel.js']) {
        vm.runInContext(fs.readFileSync(path.resolve(__dirname, '../../frontend/js', file), 'utf8'), context);
    }
    const panel = new window.ConfigurationPanel();
    panel._config = {
        device: { platform: pimesh ? 'node' : 'gateway', radio_protocol: protocol },
        platform_ui: { variant: pimesh ? 'pimesh' : 'gateway', protocol_switch: pimesh },
    };
    return { panel, mounts, hosts };
}

test('PiMesh MeshCore has one settings editor and one advert timer across sidebar routes', () => {
    const { panel, mounts } = setup(true);
    for (const route of ['radio', 'channels', 'transmit', 'gps']) panel._mountSection(route);
    assert.equal(mounts.filter(m => m.name === 'MeshcoreConfigCard').length, 0);
    assert.equal(mounts.filter(m => m.name === 'PositionBroadcastCard').length, 0);
    assert.equal(mounts.filter(m => m.name === 'PimeshBehaviorCard').length, 0);
    panel._mountSection('meshcore');
    panel._mountSection('meshcore');
    assert.equal(mounts.filter(m => m.name === 'MeshcoreConfigCard').length, 1);
    assert.equal(mounts.filter(m => m.name === 'PimeshBehaviorCard').length, 1);
    const timers = mounts.filter(m => m.name === 'PositionBroadcastCard');
    assert.equal(timers.length, 1);
    assert.equal(timers[0].options.meshcore, true);
    const status = mounts.find(m => m.name === 'BroadcastStatusCard');
    assert.equal(status.options.editRoute, '#/configuration/meshcore');
});

test('PiMesh Meshtastic retains its Radio behavior and GPS position timer', () => {
    const { panel, mounts } = setup(true, 'meshtastic');
    panel._mountSection('radio');
    assert.equal(mounts.filter(m => m.name === 'WismeshRadioCard').length, 1);
    assert.equal(mounts.filter(m => m.name === 'PimeshBehaviorCard').length, 1);
    panel._mountSection('gps');
    panel._mountSection('meshcore');
    assert.equal(mounts.filter(m => m.name === 'PositionBroadcastCard').length, 1);
    assert.equal(mounts.find(m => m.name === 'PositionBroadcastCard').options, undefined);
});

test('Gateway keeps native channel/transmit editors without PiMesh advert controls', () => {
    const { panel, mounts } = setup(false);
    for (const route of ['radio', 'channels', 'transmit', 'gps', 'meshcore']) panel._mountSection(route);
    for (const name of ['ChannelsConfigCard', 'TransmitConfigCard', 'RadioConfigEditCard']) {
        assert.equal(mounts.filter(m => m.name === name).length, 1);
    }
    assert.equal(mounts.filter(m => m.name === 'PimeshBehaviorCard').length, 0);
    assert.equal(mounts.filter(m => m.name === 'PositionBroadcastCard').length, 1);
    assert.equal(mounts.find(m => m.name === 'PositionBroadcastCard').options, undefined);
});

test('Moved advert editor retains the saved scheduler API and interval, including Off', () => {
    let options, rendered;
    const window = { BroadcastIntervalCard: class {
        constructor(api, value) { options = value; }
        render(config) { rendered = config[options.configKey].interval_minutes; }
    } };
    vm.runInNewContext(fs.readFileSync(path.resolve(__dirname,
        '../../frontend/js/configuration/position_broadcast_card.js'), 'utf8'), { window });
    const card = new window.PositionBroadcastCard({}, { meshcore: true });
    assert.equal(options.putUrl, '/api/config/position');
    assert.equal(options.title, 'MeshCore advertisement interval');
    for (const interval of [15, 60, 0]) {
        card.render({ position: { interval_minutes: interval } });
        assert.equal(rendered, interval);
    }
});
