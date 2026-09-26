const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../frontend/js/map_tiles.js'), 'utf8');
const defaultUrl = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';

function boot(fetch) {
    const layers = [];
    const ctx = vm.createContext({fetch, L: {
        tileLayer(url, options) {
            const layer = {url, options, addTo(map) {map.layers.add(this); return this;},
                setUrl(value) {this.url = value;}};
            layers.push(layer);
            return layer;
        },
    }});
    ctx.window = ctx;
    vm.runInContext(source, ctx);
    const map = {layers: new Set(), hasLayer(layer) {return this.layers.has(layer);}};
    return {ctx, map, layers};
}

test('map gets finite zoom bounds immediately and switches to configured local tiles', async () => {
    let resolve, calls = 0;
    const response = new Promise(done => {resolve = done;});
    const {ctx, map} = boot(() => {calls++; return response;});
    const layer = ctx.createMapTileLayer(map);
    assert.equal(map.hasLayer(layer), true);
    assert.equal(layer.options.maxZoom, 19);
    assert.equal(layer.url, defaultUrl);
    const second = ctx.createMapTileLayer(map);
    const url = '/api/offline-map/tiles/test/{z}/{x}/{y}.png';
    resolve({ok: true, json: async () => ({dashboard: {map_tile_url: url}})});
    await ctx.getMapTileUrl();
    assert.equal(layer.url, url);
    assert.equal(second.url, url);
    assert.equal(calls, 1);
});

test('configuration failures keep the default tile source', async () => {
    for (const fetch of [async () => {throw Error('offline');},
        async () => ({ok: false}), async () => ({ok: true, json: async () => ({})})]) {
        const {ctx, map} = boot(fetch);
        const layer = ctx.createMapTileLayer(map);
        assert.equal(await ctx.getMapTileUrl(), defaultUrl);
        assert.equal(layer.url, defaultUrl);
    }
});

test('a detached map layer is not updated when configuration arrives', async () => {
    const {ctx, map} = boot(async () => ({ok: true,
        json: async () => ({dashboard: {map_tile_url: '/tiles/{z}/{x}/{y}.png'}})}));
    const layer = ctx.createMapTileLayer(map);
    map.layers.clear();
    await ctx.getMapTileUrl();
    assert.equal(layer.url, defaultUrl);
});
