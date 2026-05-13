/**
 * Leaflet map with marker clustering for the local Meshpoint dashboard.
 * Displays the Meshpoint device and captured nodes with protocol-colored markers.
 */
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
        }).setView([39.8, -98.5], 4);

        L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
            attribution: '&copy; CARTO',
            subdomains: 'abcd',
            maxZoom: 19,
        }).addTo(this._map);

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
    }

    loadNodes(nodes, device) {
        if (!this._initialized) return;

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
        const color = isMeshtastic ? '#06b6d4' : '#a855f7';

        const heard = n.last_heard || n.last_seen;
        const isRecent = heard && (Date.now() - new Date(heard).getTime()) < 60000;

        const marker = L.circleMarker([n.latitude, n.longitude], {
            radius: 6,
            fillColor: color,
            fillOpacity: 0.8,
            color: isRecent ? '#00ff88' : color,
            weight: isRecent ? 2 : 1,
            className: isRecent ? 'node-pulse' : '',
        });

        const name = n.long_name || n.name || n.node_id || '--';
        const rssi = (n.rssi ?? n.latest_rssi) != null
            ? `${Number(n.rssi ?? n.latest_rssi).toFixed(0)} dBm` : '--';

        marker.bindPopup(
            `<strong>${this._esc(name)}</strong><br>` +
            `Protocol: ${n.protocol || 'meshtastic'}<br>` +
            `RSSI: ${rssi}`
        );

        this._markerGroup.addLayer(marker);
        this._markers[n.node_id] = marker;
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

    updateFromPacket(packet) {
        if (!packet.source_id || !this._initialized) return;
        const marker = this._markers[packet.source_id];
        if (marker) {
            marker.setStyle({ color: '#00ff88', weight: 2 });
            this._drawPacketLine(marker);
            setTimeout(() => {
                const proto = (packet.protocol || 'meshtastic') === 'meshtastic' ? '#06b6d4' : '#a855f7';
                marker.setStyle({ color: proto, weight: 1 });
            }, 5000);
        }
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
