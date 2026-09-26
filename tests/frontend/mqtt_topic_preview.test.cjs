const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(
    path.join(__dirname, '../../frontend/js/configuration/mqtt_card.js'),
    'utf8',
);
const context = { window: {} };
vm.runInNewContext(source, context);

function previewCard(channels) {
    const card = new context.window.MqttConfigCard({});
    card._channels = { value: channels };
    card._topicRoot = { value: 'msh' };
    card._region = { value: 'US' };
    card._gateway = { value: 'aabbccdd' };
    card._json = { checked: true };
    card._previewMt = { style: {}, textContent: '' };
    card._previewMc = { style: {}, textContent: '' };
    card._previewJson = { style: {}, textContent: '' };
    return card;
}

test('MQTT topic examples track the selected LongTurbo channel', () => {
    const card = previewCard('LongTurbo\nMeshCore');
    card._renderPreviews();
    assert.equal(card._previewMt.textContent, 'msh/US/2/e/LongTurbo/!aabbccdd');
    assert.equal(card._previewJson.textContent, 'msh/US/2/json/LongTurbo/!aabbccdd');
    assert.equal(card._previewMc.textContent, 'msh/US/2/c/MeshCore/!aabbccdd');

    card._channels.value = 'LongFast\nLongTurbo\nMeshCore';
    card._renderPreviews();
    assert.equal(
        card._previewMt.textContent,
        'msh/US/2/e/LongFast/!aabbccdd\nmsh/US/2/e/LongTurbo/!aabbccdd',
    );

    card._channels.value = 'MeshCore';
    card._renderPreviews();
    assert.equal(card._previewMt.style.display, 'none');
    assert.equal(card._previewJson.style.display, 'none');
    assert.equal(card._previewMc.style.display, '');
});
