/**
 * Leaflet map with marker clustering for the local Meshpoint dashboard.
 * Displays the Meshpoint device and captured nodes with protocol-colored markers.
 */

const MAP_VIEW_STORAGE_KEY = 'meshpoint.nodeMap.view';
const MAP_DEFAULT_CENTER = [39.8, -98.5];
const MAP_DEFAULT_ZOOM = 4;

class NodeMap {
    constructor(containerId) {
        this._containerId = containerId;
        this._map = null;
        this._markerGroup = null;
        this._deviceMarker = null;
        this._markers = {};
        this._initialized = false;
        this._hasFitBounds = false;
        this._init();
    }

    _init() {
        const el = document.getElementById(this._containerId);
        if (!el) return;

        this._map = L.map(this._containerId, {
            zoomControl: true,
            scrollWheelZoom: true,
        });

        const savedView = this._loadSavedView();
        if (savedView) {
            this._map.setView(savedView.center, savedView.zoom);
            // Honor the user's saved view; skip the first-load auto-fit.
            this._hasFitBounds = true;
        } else {
            this._map.setView(MAP_DEFAULT_CENTER, MAP_DEFAULT_ZOOM);
        }

        L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
            attribution: '&copy; CARTO',
            subdomains: 'abcd',
            maxZoom: 19,
        }).addTo(this._map);

        this._wireResizeRecalc();

        this._topologyLayer = L.layerGroup();
        this._topologyVisible = false;
        this._focusLine = null;

        this._markerGroup = L.markerClusterGroup({
            maxClusterRadius: 50,
            disableClusteringAtZoom: 13,
            spiderfyOnMaxZoom: true,
            showCoverageOnHover: false,
            iconCreateFunction: (cluster) => {
                const count = cluster.getChildCount();
                let size = 'small';
                if (count > 50) size = 'large';
                else if (count > 10) size = 'medium';
                return L.divIcon({
                    html: `<div><span>${count}</span></div>`,
                    className: `marker-cluster marker-cluster-${size}`,
                    iconSize: L.point(40, 40),
                });
            },
        });
        this._map.addLayer(this._markerGroup);

        const overlays = { 'Topology Links': this._topologyLayer };
        L.control.layers(null, overlays, { position: 'topright', collapsed: true }).addTo(this._map);

        this._map.on('overlayadd', (e) => {
            if (e.layer === this._topologyLayer) {
                this._topologyVisible = true;
                this._loadTopology();
            }
        });
        this._map.on('overlayremove', (e) => {
            if (e.layer === this._topologyLayer) {
                this._topologyVisible = false;
            }
        });

        this._initialized = true;

        this._map.on('moveend', () => this._saveCurrentView());
        this._map.on('zoomend', () => this._saveCurrentView());

        if (window.MeshpointNodeFavorites) {
            window.MeshpointNodeFavorites.onChange(() => {
                if (this._lastNodes) {
                    this.loadNodes(this._lastNodes, this._lastDevice);
                }
            });
        }
    }

    _loadSavedView() {
        try {
            const raw = localStorage.getItem(MAP_VIEW_STORAGE_KEY);
            if (!raw) return null;
            const parsed = JSON.parse(raw);
            const lat = Number(parsed.lat);
            const lon = Number(parsed.lon);
            const zoom = Number(parsed.zoom);
            if (!Number.isFinite(lat) || !Number.isFinite(lon) || !Number.isFinite(zoom)) {
                return null;
            }
            if (lat < -90 || lat > 90 || lon < -180 || lon > 180) return null;
            if (zoom < 0 || zoom > 19) return null;
            return { center: [lat, lon], zoom };
        } catch (_e) {
            return null;
        }
    }

    _saveCurrentView() {
        if (!this._map) return;
        try {
            const c = this._map.getCenter();
            localStorage.setItem(MAP_VIEW_STORAGE_KEY, JSON.stringify({
                lat: c.lat,
                lon: c.lng,
                zoom: this._map.getZoom(),
            }));
        } catch (_e) {
            /* private mode / quota -- best-effort persistence */
        }
    }

    loadNodes(nodes, device) {
        if (!this._initialized) return;

        this._lastNodes = nodes;
        this._lastDevice = device;

        this._markerGroup.clearLayers();
        this._markers = {};

        const bounds = [];

        if (device && device.latitude && device.longitude) {
            this._addDeviceMarker(device);
            bounds.push([device.latitude, device.longitude]);
        }

        for (const n of nodes) {
            const lat = n.latitude;
            const lon = n.longitude;
            if (lat == null || lon == null) continue;

            bounds.push([lat, lon]);
            this._addNodeMarker(n);
        }

        if (!this._hasFitBounds && bounds.length > 0) {
            if (bounds.length > 1) {
                this._map.fitBounds(bounds, { padding: [40, 40], maxZoom: 14 });
            } else {
                this._map.setView(bounds[0], 13);
            }
            this._hasFitBounds = true;
        }
    }

    _addDeviceMarker(device) {
        if (this._deviceMarker) {
            const cur = this._deviceMarker.getLatLng();
            if (
                Math.abs(cur.lat - device.latitude) < 1e-6
                && Math.abs(cur.lng - device.longitude) < 1e-6
            ) {
                return;  // position unchanged; preserve existing marker + open popup
            }
            this._map.removeLayer(this._deviceMarker);
        }

        this._deviceMarker = L.marker([device.latitude, device.longitude], {
            icon: L.divIcon({
                html: '<div class="device-marker"></div>',
                className: '',
                iconSize: [16, 16],
                iconAnchor: [8, 8],
            }),
            zIndexOffset: 1000,
        });

        const name = device.device_name || 'Meshpoint';
        this._deviceMarker.bindPopup(
            `<strong>${this._esc(name)}</strong><br>` +
            `Type: Meshpoint<br>` +
            `Lat: ${device.latitude.toFixed(4)}<br>` +
            `Lon: ${device.longitude.toFixed(4)}`
        );

        this._deviceMarker.addTo(this._map);
    }

    _addNodeMarker(n) {
        const isMeshtastic = (n.protocol || 'meshtastic') === 'meshtastic';
        const protoColor = isMeshtastic ? '#06b6d4' : '#a855f7';

        const heard = n.last_heard || n.last_seen;
        const isRecent = heard && (Date.now() - new Date(heard).getTime()) < 60000;
        const isFav = !!(window.MeshpointNodeFavorites && window.MeshpointNodeFavorites.has(n.node_id));

        let marker;
        if (isMeshtastic) {
            // Order of border color precedence: recent (green) > favorite (amber) > protocol (cyan).
            let borderColor = protoColor;
            if (isFav) borderColor = '#f59e0b';
            if (isRecent) borderColor = '#00ff88';
            marker = L.circleMarker([n.latitude, n.longitude], {
                radius: 6,
                fillColor: protoColor,
                fillOpacity: 0.8,
                color: borderColor,
                weight: (isRecent || isFav) ? 2 : 1,
                className: isRecent ? 'node-pulse' : '',
            });
            marker._meshpointKind = 'circle';
        } else {
            const recentClass = isRecent ? ' node-marker__diamond--recent' : '';
            const favClass = isFav ? ' node-marker__diamond--fav' : '';
            marker = L.marker([n.latitude, n.longitude], {
                icon: L.divIcon({
                    html: `<div class="node-marker__diamond${favClass}${recentClass}"></div>`,
                    className: '',
                    iconSize: [12, 12],
                    iconAnchor: [6, 6],
                }),
            });
            marker._meshpointKind = 'diamond';
        }

        const name = n.long_name || n.name || n.node_id || '--';
        const rssi = (n.rssi ?? n.latest_rssi) != null
            ? `${Number(n.rssi ?? n.latest_rssi).toFixed(0)} dBm` : '--';
        const lastHeard = this._formatRelativeTime(heard);

        marker.bindPopup(
            `<strong>${this._esc(name)}</strong><br>` +
            `Protocol: ${n.protocol || 'meshtastic'}<br>` +
            `RSSI: ${rssi}<br>` +
            `Last heard: ${lastHeard}`
        );

        this._markerGroup.addLayer(marker);
        this._markers[n.node_id] = marker;
    }

    _formatRelativeTime(timestamp) {
        if (!timestamp) return 'unknown';
        const t = new Date(timestamp).getTime();
        if (Number.isNaN(t)) return 'unknown';
        const diffMs = Date.now() - t;
        if (diffMs < 0) return 'just now';
        const sec = Math.floor(diffMs / 1000);
        if (sec < 60) return `${sec}s ago`;
        const min = Math.floor(sec / 60);
        if (min < 60) return `${min}m ago`;
        const hr = Math.floor(min / 60);
        if (hr < 24) return `${hr}h ago`;
        const days = Math.floor(hr / 24);
        return `${days}d ago`;
    }

    drawFocusLine(sourceNodeId) {
        this.clearFocusLine();
        if (!this._initialized || !this._deviceMarker) return;
        const srcMarker = this._markers[sourceNodeId];
        if (!srcMarker) return;

        this._focusLine = L.polyline(
            [srcMarker.getLatLng(), this._deviceMarker.getLatLng()],
            { color: '#f59e0b', weight: 3, opacity: 0.9 }
        ).addTo(this._map);
    }

    clearFocusLine() {
        if (this._focusLine) {
            this._map.removeLayer(this._focusLine);
            this._focusLine = null;
        }
    }

    centerOn(lat, lng, zoom = 15) {
        if (this._map) this._map.flyTo([lat, lng], zoom);
    }

    _wireResizeRecalc() {
        if (!this._map) return;

        requestAnimationFrame(() => {
            if (this._map) this._map.invalidateSize();
        });

        let resizeTimer = null;
        const recalc = () => {
            if (!this._map) return;
            this._map.invalidateSize();
        };

        window.addEventListener('resize', () => {
            if (resizeTimer) clearTimeout(resizeTimer);
            resizeTimer = setTimeout(recalc, 150);
        });

        document.addEventListener('sidebar:routeActivated', (event) => {
            if (event.detail && event.detail.route === 'dashboard') {
                requestAnimationFrame(recalc);
            }
        });

        if (typeof ResizeObserver === 'function') {
            const el = document.getElementById(this._containerId);
            if (el) {
                this._resizeObserver = new ResizeObserver(() => {
                    if (resizeTimer) clearTimeout(resizeTimer);
                    resizeTimer = setTimeout(recalc, 150);
                });
                this._resizeObserver.observe(el);
            }
        }
    }

    updateFromPacket(packet) {
        if (!packet.source_id || !this._initialized) return;
        const marker = this._markers[packet.source_id];
        if (!marker) return;

        const isMeshtastic = (packet.protocol || 'meshtastic') === 'meshtastic';
        const proto = isMeshtastic ? '#06b6d4' : '#a855f7';

        if (marker._meshpointKind === 'diamond') {
            const el = marker.getElement()?.querySelector('.node-marker__diamond');
            if (el) el.classList.add('node-marker__diamond--recent');
            this._drawPacketLine(marker);
            setTimeout(() => {
                const el2 = marker.getElement()?.querySelector('.node-marker__diamond');
                if (el2) el2.classList.remove('node-marker__diamond--recent');
            }, 5000);
            return;
        }

        // Default: circleMarker (Meshtastic).
        marker.setStyle({ color: '#00ff88', weight: 2 });
        this._drawPacketLine(marker);
        setTimeout(() => {
            const isFav = !!(window.MeshpointNodeFavorites
                && window.MeshpointNodeFavorites.has(packet.source_id));
            marker.setStyle({
                color: isFav ? '#f59e0b' : proto,
                weight: isFav ? 2 : 1,
            });
        }, 5000);
    }

    _drawPacketLine(sourceMarker) {
        if (!this._deviceMarker) return;
        const deviceLatLng = this._deviceMarker.getLatLng();
        const nodeLatLng = sourceMarker.getLatLng();

        const line = L.polyline([nodeLatLng, deviceLatLng], {
            color: '#00e5a0',
            weight: 2,
            opacity: 0.8,
            dashArray: '6, 4',
            className: 'packet-line',
        }).addTo(this._map);

        let opacity = 0.8;
        const fade = setInterval(() => {
            opacity -= 0.1;
            if (opacity <= 0) {
                clearInterval(fade);
                this._map.removeLayer(line);
            } else {
                line.setStyle({ opacity });
            }
        }, 200);
    }

    async _loadTopology() {
        try {
            const res = await fetch('/api/analytics/topology');
            const links = await res.json();
            this._topologyLayer.clearLayers();

            for (const link of links) {
                const srcMarker = this._markers[link.source];
                const tgtMarker = this._markers[link.target];
                if (!srcMarker || !tgtMarker) continue;

                const line = L.polyline(
                    [srcMarker.getLatLng(), tgtMarker.getLatLng()],
                    {
                        color: '#f59e0b',
                        weight: 1.5,
                        opacity: 0.6,
                        dashArray: '4, 4',
                    },
                );

                const rssiLabel = link.rssi != null ? `RSSI: ${link.rssi} dBm` : '';
                const snrLabel = link.snr != null ? `SNR: ${link.snr} dB` : '';
                const tooltip = [
                    `${link.source} ↔ ${link.target}`,
                    rssiLabel, snrLabel,
                ].filter(Boolean).join('<br>');
                line.bindTooltip(tooltip);

                this._topologyLayer.addLayer(line);
            }
        } catch (e) {
            console.error('Topology load failed:', e);
        }
    }

    _esc(str) {
        const el = document.createElement('span');
        el.textContent = str;
        return el.innerHTML;
    }
}
