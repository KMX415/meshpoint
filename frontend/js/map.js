class NodeMap {
    constructor(elementId) {
        this.map = L.map(elementId, {
            zoomControl: true,
            attributionControl: false,
        }).setView([0, 0], 2);

        L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
            maxZoom: 19,
        }).addTo(this.map);

        this.markers = {};
        this.markerGroup = L.layerGroup().addTo(this.map);
        this._centerOnDevice();
    }

    async _centerOnDevice() {
        try {
            const res = await fetch('/api/device');
            const device = await res.json();
            if (device.latitude != null && device.longitude != null) {
                this.map.setView([device.latitude, device.longitude], 12);
            }
        } catch (e) {
            console.error('Could not center map on device:', e);
        }
    }

    async loadNodes() {
        try {
            const response = await fetch('/api/nodes/map');
            const nodes = await response.json();
            this.updateMarkers(nodes);
        } catch (e) {
            console.error('Failed to load map nodes:', e);
        }
    }

    updateMarkers(nodes) {
        nodes.forEach(node => {
            if (node.latitude == null || node.longitude == null) return;

            const key = node.node_id;
            const color = node.protocol === 'meshcore' ? '#a855f7' : '#3b82f6';

            if (this.markers[key]) {
                this.markers[key].setLatLng([node.latitude, node.longitude]);
                this.markers[key].setPopupContent(this._buildPopup(node));
            } else {
                const marker = L.circleMarker([node.latitude, node.longitude], {
                    radius: 7,
                    fillColor: color,
                    color: '#fff',
                    weight: 1,
                    opacity: 0.9,
                    fillOpacity: 0.8,
                }).bindPopup(this._buildPopup(node));

                marker.addTo(this.markerGroup);
                this.markers[key] = marker;
            }
        });

        if (nodes.length > 0 && Object.keys(this.markers).length <= nodes.length) {
            const bounds = this.markerGroup.getBounds();
            if (bounds.isValid()) {
                this.map.fitBounds(bounds, { padding: [30, 30] });
            }
        }
    }

    _buildPopup(node) {
        const signal = node.signal
            ? `<br>RSSI: ${node.signal.rssi} dBm | SNR: ${node.signal.snr} dB`
            : '';
        return `<div style="font-family:monospace;font-size:12px;">
            <strong>${node.display_name}</strong><br>
            ID: ${node.node_id}<br>
            Protocol: ${node.protocol}<br>
            Packets: ${node.packet_count}
            ${signal}
        </div>`;
    }

    invalidateSize() {
        setTimeout(() => this.map.invalidateSize(), 100);
    }
}

window.NodeMap = NodeMap;
