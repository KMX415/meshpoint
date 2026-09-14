/** Shared tile source for dashboard maps, including locally hosted OSM tiles. */
(() => {
    const DEFAULT_URL = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
    let sourcePromise;

    function getMapTileUrl() {
        if (!sourcePromise) {
            sourcePromise = fetch('/api/config', { credentials: 'same-origin' })
                .then((response) => {
                    if (!response.ok) throw new Error('Map configuration unavailable');
                    return response.json();
                })
                .then((config) => config.dashboard?.map_tile_url || DEFAULT_URL)
                .catch(() => DEFAULT_URL);
        }
        return sourcePromise;
    }

    window.getMapTileUrl = getMapTileUrl;
    window.createMapTileLayer = function (map) {
        // Install immediately so Leaflet has finite zoom bounds before markers fit.
        const layer = L.tileLayer(DEFAULT_URL, {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>',
            maxZoom: 19,
        }).addTo(map);
        getMapTileUrl().then((url) => {
            if (url !== DEFAULT_URL && map.hasLayer(layer)) layer.setUrl(url);
        });
        return layer;
    };
})();
