const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const context = vm.createContext({ window: {} });
vm.runInContext(fs.readFileSync(path.resolve(__dirname, '../../frontend/js/configuration/gps_card.js'), 'utf8'), context);
const Card = context.window.GpsConfigCard;
test('privacy remains visible and unchanged across registered/live source switches', () => {
    for (const precision of ['approximate', 'exact', 'none']) {
        const card = Object.create(Card.prototype);
        const liveInput = {};
        const registeredInput = {};
        card._meshPrecisionWrap = { hidden: true };
        card._meshPrecision = { value: precision };
        card._meshLiveChip = { classList: { toggle() {} }, querySelector: () => liveInput };
        card._root = { querySelector: () => registeredInput };
        for (const [gps, mesh] of [['static', 'static'], ['gpsd', 'live'], ['gpsd', 'static'], ['static', 'live']]) {
            card._updateMeshControls(gps, mesh);
            assert.equal(card._meshPrecisionWrap.hidden, false);
            assert.equal(card._meshPrecision.value, precision);
            assert.equal(liveInput.disabled, gps === 'static');
        }
        assert.equal(registeredInput.checked, true);
    }
});
