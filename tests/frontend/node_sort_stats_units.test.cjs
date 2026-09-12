// Run with: node --test tests/frontend/node_sort_stats_units.test.cjs
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '../..');

function fixture() {
    const elements = new Map();
    const stored = new Map();
    const listeners = new Map();
    const add = id => {
        const el = { textContent: '', value: '', style: {}, events: {},
            addEventListener(type, fn) { this.events[type] = fn; } };
        elements.set(id, el);
        return el;
    };
    add('node-sort');
    add('stats-panel');
    for (const prefix of ['ss-direct', 'ss-mesh']) {
        for (const suffix of ['mi', 'unit', 'detail', 'bar']) add(`${prefix}-${suffix}`);
    }
    const window = {
        StatsChartHost: class {},
        addEventListener(type, fn) {
            if (!listeners.has(type)) listeners.set(type, []);
            listeners.get(type).push(fn);
        },
        dispatchEvent(event) { for (const fn of listeners.get(event.type) || []) fn(event); },
    };
    const context = vm.createContext({ window, console,
        CustomEvent: class { constructor(type, options) { this.type = type; this.detail = options.detail; } },
        localStorage: { getItem: key => stored.get(key) ?? null, setItem: (key, value) => stored.set(key, value) },
        document: { getElementById: id => elements.get(id) || null,
            querySelectorAll: () => [], addEventListener() {} },
    });
    const load = file => vm.runInContext(fs.readFileSync(path.join(root, 'frontend/js', file), 'utf8'), context);
    return { context, window, elements, stored, load };
}

test('packet comparator sorts counts, missing values, favorites and hop filters', () => {
    const f = fixture();
    f.load('node_cards_sort.js');
    const sort = f.window.MeshpointNodeCardsSort;
    const nodes = [
        { node_id: 'zero', packet_count: 0, last_heard: '2026-09-12', hop_count: 0 },
        { node_id: 'older', packet_count: 9, last_heard: '2026-09-10', hop_count: 2 },
        { node_id: 'newer', packet_count: '9', last_heard: '2026-09-11', hop_count: 0 },
        { node_id: 'null', packet_count: null, last_heard: '2026-09-11', hop_count: 1 },
        { node_id: 'invalid', packet_count: 'bad', last_heard: '2026-09-10', hop_count: 0 },
        { node_id: 'most', packet_count: 20, last_heard: '2026-09-09', hop_count: 1 },
    ];
    const ids = items => Array.from(items, node => node.node_id);
    assert.deepEqual(ids(sort.applySort(nodes, 'packets')), ['most', 'newer', 'older', 'zero', 'null', 'invalid']);
    assert.deepEqual(ids(sort.applySort(nodes, 'packets', ['older'])), ['older', 'most', 'newer', 'zero', 'null', 'invalid']);
    assert.deepEqual(ids(sort.applySort(sort.applyFilter(nodes, 'direct'), 'packets')), ['newer', 'zero', 'invalid']);
    assert.deepEqual(ids(sort.applySort(sort.applyFilter(nodes, 'relayed'), 'packets')), ['most', 'older', 'null']);
    assert.equal(nodes[0].node_id, 'zero', 'sorting must not mutate the source list');
});

test('real script order accepts the dropdown change and restores packet sorting', () => {
    const f = fixture();
    const html = fs.readFileSync(path.join(root, 'frontend/index.html'), 'utf8');
    assert.ok(html.indexOf('js/node_cards_sort.js') < html.indexOf('js/node_cards.js'));
    assert.match(html, /<option value="packets">Sort: Packets<\/option>/);
    f.load('node_cards_sort.js');
    f.load('node_cards.js');
    const cards = vm.runInContext('new NodeCards("nodes", () => {})', f.context);
    let renders = 0;
    cards._render = () => renders++;
    f.elements.get('node-sort').events.change({ target: { value: 'packets' } });
    assert.equal(cards._sortBy, 'packets');
    assert.equal(renders, 1);
    assert.equal(f.stored.get('meshpoint.nodeCards.sortBy'), 'packets');
    const reloaded = vm.runInContext('new NodeCards("nodes", () => {})', f.context);
    assert.equal(reloaded._sortBy, 'packets');
    assert.equal(f.elements.get('node-sort').value, 'packets');
});

test('stats range values and labels follow live unit changes without fetching', () => {
    const f = fixture();
    f.load('meshpoint_display_units.js');
    f.load('stats_tab.js');
    const stats = f.window.statsTab;
    stats._rendered = true;
    stats._updateRange({ farthest_direct: { miles: 1 } }, { miles: 10 });
    const text = id => f.elements.get(id).textContent;
    assert.equal(text('ss-direct-mi'), '1.0');
    assert.equal(text('ss-direct-unit'), 'mi');
    assert.equal(Number(text('ss-mesh-mi')), 10);
    const directBar = f.elements.get('ss-direct-bar').style.width;
    f.window.MeshpointDisplayUnits.savePrefs({ distance: 'metric' });
    assert.equal(text('ss-direct-mi'), '1.6');
    assert.equal(text('ss-direct-unit'), 'km');
    assert.equal(text('ss-mesh-mi'), '16');
    assert.equal(text('ss-mesh-unit'), 'km');
    assert.equal(f.elements.get('ss-direct-bar').style.width, directBar);
    f.window.MeshpointDisplayUnits.savePrefs({ distance: 'imperial' });
    assert.equal(text('ss-direct-unit'), 'mi');
    assert.equal(text('ss-direct-mi'), '1.0');
    stats._updateRange({ farthest_direct: { miles: 0.01 } }, { miles: null });
    assert.equal(text('ss-direct-mi'), '53');
    assert.equal(text('ss-direct-unit'), 'ft');
    assert.equal(text('ss-mesh-mi'), '--');
    f.window.MeshpointDisplayUnits.savePrefs({ distance: 'metric' });
    assert.equal(text('ss-direct-mi'), '16');
    assert.equal(text('ss-direct-unit'), 'm');
    assert.equal(text('ss-mesh-unit'), 'km');
});
