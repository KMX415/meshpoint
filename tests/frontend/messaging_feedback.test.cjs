const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function chat() {
    const context = vm.createContext({ window: {} });
    vm.runInContext(fs.readFileSync(path.resolve(__dirname, '../../frontend/js/messaging_chat.js'), 'utf8')
        + '\nwindow.Chat = MessagingChat;', context);
    const view = Object.create(context.window.Chat.prototype);
    view._feedback = new Map();
    view._messages = [];
    view._esc = value => String(value).replaceAll('<', '&lt;');
    const meta = { innerHTML: '' };
    const bubble = { dataset: {}, querySelector: () => meta };
    view._messagesEl = { querySelector: () => bubble };
    return { view, meta, bubble };
}

function sent(overrides = {}) {
    return { id: 1, direction: 'sent', protocol: 'meshcore', status: 'sent',
        node_id: 'broadcast:meshcore', packet_id: 'mc:one', ...overrides };
}

test('channel metadata distinguishes unknown, zero, one and multiple repeats', () => {
    const { view } = chat();
    assert.doesNotMatch(view._buildMetaHtml(sent()), /Heard/);
    assert.match(view._buildMetaHtml(sent({ heard_repeats: 0 })), /Heard 0 repeats/);
    assert.match(view._buildMetaHtml(sent({ heard_repeats: 1 })), /Heard 1 repeat</);
    assert.match(view._buildMetaHtml(sent({ heard_repeats: 9 })), /Heard 9 repeats/);
    assert.doesNotMatch(view._buildMetaHtml(sent({ protocol: 'meshtastic', heard_repeats: 9 })), /Heard/);
});

test('DM confirmation is visible in history and never invents repeats', () => {
    const { view } = chat();
    assert.match(view._buildMetaHtml(sent({ node_id: 'mc:peer' })), /Delivery unconfirmed/);
    const delivered = view._buildMetaHtml(sent({ node_id: 'mc:peer', status: 'delivered' }));
    assert.match(delivered, /Delivered/);
    assert.doesNotMatch(delivered, /Heard|unconfirmed/);
});

test('early websocket feedback survives send response and subsequent stale updates', () => {
    const { view, meta, bubble } = chat();
    view._messages.push(sent({ id: 100, packet_id: '', status: 'sending...' }));
    view.updateMeshcoreFeedback({ protocol: 'meshcore', packet_id: 'mc:new', heard_repeats: 3 });
    view.updateMessageStatus(100, 'sent', 'mc:new', { id: 5, heard_repeats: 0 });
    assert.equal(view._messages[0].id, 5);
    assert.equal(bubble.dataset.pktId, 'mc:new');
    assert.match(meta.innerHTML, /Heard 3 repeats/);
    view.updateMeshcoreFeedback({ protocol: 'meshcore', packet_id: 'mc:new', heard_repeats: 1 });
    assert.match(meta.innerHTML, /Heard 3 repeats/);
});

test('early DM ACK survives response and unrelated events do not update the bubble', () => {
    const { view, meta } = chat();
    view._messages.push(sent({ id: 100, packet_id: '', node_id: 'mc:peer' }));
    view.updateMeshcoreFeedback({ protocol: 'meshcore', packet_id: 'mc:new', status: 'delivered' });
    view.updateMessageStatus(100, 'sent', 'mc:new', { id: 5 });
    assert.match(meta.innerHTML, /Delivered/);
    view.updateMeshcoreFeedback({ protocol: 'meshcore', packet_id: 'mc:other', heard_repeats: 9 });
    assert.doesNotMatch(meta.innerHTML, /Heard/);
});

test('feedback cache is bounded and unsafe status text is escaped', () => {
    const { view } = chat();
    for (let i = 0; i < 150; i++) view.updateMeshcoreFeedback({ protocol: 'meshcore', packet_id: 'mc:' + i });
    assert.equal(view._feedback.size, 128);
    assert.doesNotMatch(view._buildMetaHtml(sent({ status: '<img onerror=bad>' })), /<img/);
});


test('path details handle unknown, ambiguous, missing signal and escaped names', () => {
    const { view } = chat();
    const html = view._pathsHtml({ count: 3, observations: [{
        hops: [{ id: 'aa', name: '<img>', ambiguous: false }, { id: 'bb', ambiguous: true }, { id: 'cc' }],
        rssi: -96, snr: null,
    }] });
    assert.doesNotMatch(html, /<img>/);
    assert.match(html, /Ambiguous repeater/);
    assert.match(html, /Unknown repeater/);
    assert.match(html, /Your radio/);
    assert.match(html, /Unavailable/);
    assert.match(html, /first 1 saved/);
    assert.match(view._pathsHtml({ recorded: false }), /weren.t recorded/);
    assert.match(view._pathsHtml({ recorded: true }), /No repeated paths/);
});
