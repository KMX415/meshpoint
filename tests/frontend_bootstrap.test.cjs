const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const read = file => fs.readFileSync(path.join(__dirname, '..', file), 'utf8');

function boot(identity) {
    const calls = [];
    let ready, release;
    const pending = new Promise(resolve => { release = resolve; });
    const ctx = vm.createContext({console, URL, setInterval: () => {}, setTimeout: () => {},
        document: {addEventListener: (name, fn) => { if (name === 'DOMContentLoaded') ready = fn; }, getElementById: () => null},
        location: {origin:'http://localhost', replace: url => calls.push(url)},
        Router: class {onRouteChange() {} start() {}}, SidebarController: class {bind() {}},
        SignOutController: class {bind() {}}, NodeMap: class {}, NodeCards: class {},
        SimplePacketFeed: class {setOnFocus() {}}, NodeDrawer: class {open() {} close() {}},
        fetch: async url => { calls.push(url); return {ok:true, json:async () => identity}; },
        pending, calls,
    });
    ctx.window = ctx;
    ctx.installViewerAccess = () => {};
    ctx.loadPluginPages = async () => [];
    ctx.concentratorWS = {connect: () => calls.push('connect'), on: name => calls.push('on:' + name)};
    vm.runInContext(read('frontend/js/app.js'), ctx);
    vm.runInContext(`_bootCommandPaletteAndKeymap = _wireSoundEvents = _bootAuthPanel = _bootTerminalPanel
        = _bootUpdatePanel = _bootConfigurationPanel = _bootDangerousPanel = () => {};
        _loadInitial = async () => {calls.push('initial'); await pending;};
        _updateStats = async () => {calls.push('stats');}; _checkForUpdate = () => {};`, ctx);
    return {calls, ready, release};
}

test('connection opens while the initial snapshot is still pending; identity is fetched once', async () => {
    const fixture = boot({role:'admin'});
    const finished = fixture.ready();
    await new Promise(resolve => setImmediate(resolve));
    assert.deepEqual(fixture.calls, ['/api/identity', 'connect', 'initial']);
    fixture.release(); await finished;
    assert.deepEqual(fixture.calls, ['/api/identity', 'connect', 'initial', 'on:packet', 'stats']);
});

test('setup redirect happens before connecting or requesting dashboard data', async () => {
    const fixture = boot({setup_required:true});
    await fixture.ready();
    assert.deepEqual(fixture.calls, ['/api/identity', '/setup']);
});

test('handshake clears placeholders without replacing richer sidebar status', () => {
    const text = {textContent:'connecting...'}, dot = {};
    const ctx = vm.createContext({document:{getElementById:id => id.endsWith('text') ? text : dot}});
    ctx.window = ctx;
    vm.runInContext(read('frontend/js/websocket_client.js'), ctx);
    ctx.concentratorWS._updateStatusIndicator(true);
    assert.equal(text.textContent, 'online');
    text.textContent = 'online · v0.8.0';
    ctx.concentratorWS._updateStatusIndicator(true);
    assert.equal(text.textContent, 'online · v0.8.0');
    ctx.concentratorWS._updateStatusIndicator(false);
    assert.equal(text.textContent, 'reconnecting...');
    ctx.concentratorWS._updateStatusIndicator(true);
    assert.equal(text.textContent, 'online');
});
