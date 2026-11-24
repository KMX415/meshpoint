const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const context = { window: {} };
vm.runInNewContext(fs.readFileSync(path.join(__dirname,
    '../frontend/js/settings/update_panel_controller.js'), 'utf8'), context);
const normalize = context.window.UpdatePanelController.prototype._normalizeChannelId;

test('saved retired RC selections migrate directly to the next RC', () => {
    for (const id of ['rc-074', 'rc-075', 'rc-076', 'rc-077', 'rc-078', 'rc-079', 'rc-080']) {
        assert.equal(normalize.call({}, id), 'rc-081');
    }
});

test('current, stable, custom and experimental selections are preserved', () => {
    for (const id of ['rc-081', 'stable', 'custom', 'wismesh-node', 'pimesh']) {
        assert.equal(normalize.call({}, id), id);
    }
});
