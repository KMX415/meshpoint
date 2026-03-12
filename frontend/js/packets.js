class PacketFeed {
    constructor(tableBodyId, maxRows) {
        this.tbody = document.getElementById(tableBodyId);
        this.maxRows = maxRows || 200;
        this.totalCount = 0;
    }

    addPacket(packet) {
        this.totalCount++;
        const row = this._createRow(packet);

        if (this.tbody.firstChild) {
            this.tbody.insertBefore(row, this.tbody.firstChild);
        } else {
            this.tbody.appendChild(row);
        }

        while (this.tbody.children.length > this.maxRows) {
            this.tbody.removeChild(this.tbody.lastChild);
        }

        this._updateCounters();
    }

    async loadRecent() {
        try {
            const res = await fetch('/api/packets?limit=50');
            const packets = await res.json();
            packets.reverse().forEach(p => this.addPacket(p));
        } catch (e) {
            console.error('Failed to load recent packets:', e);
        }
    }

    _createRow(packet) {
        const row = document.createElement('tr');
        const time = this._formatTime(packet.timestamp);
        const rssi = packet.signal ? `${packet.signal.rssi}` : '--';
        const snr = packet.signal ? `${packet.signal.snr}` : '--';
        const hops = packet.hop_start > 0
            ? `${packet.hop_start - packet.hop_limit}/${packet.hop_start}`
            : '--';

        const detail = this._payloadSummary(packet);
        const typeCls = `type-${this._safeClass(packet.packet_type)}`;

        const cells = [
            { text: time },
            { text: packet.protocol, cls: `protocol-${this._safeClass(packet.protocol)}` },
            { text: this._shortId(packet.source_id) },
            { text: this._shortId(packet.destination_id) },
            { text: packet.packet_type, cls: typeCls },
            { text: rssi },
            { text: snr },
            { text: hops },
            { text: detail, cls: `packet-detail ${typeCls}` },
        ];
        cells.forEach(({ text, cls }) => {
            const td = document.createElement('td');
            if (cls) td.className = cls;
            td.textContent = text;
            row.appendChild(td);
        });
        return row;
    }

    _payloadSummary(packet) {
        const payload = packet.decoded_payload;
        if (!payload) return '';
        const ptype = packet.packet_type;
        const parts = [];

        if (ptype === 'text') {
            const text = payload.text || '';
            if (text) parts.push(text.length > 60 ? text.slice(0, 60) + '…' : text);
        } else if (ptype === 'position') {
            const lat = payload.latitude ?? payload.lat;
            const lon = payload.longitude ?? payload.lon;
            if (lat != null && lon != null) {
                parts.push(`${lat.toFixed(4)}, ${lon.toFixed(4)}`);
            }
            const alt = payload.altitude ?? payload.alt;
            if (alt != null) parts.push(`alt ${Math.round(alt)}m`);
        } else if (ptype === 'telemetry') {
            const batt = payload.battery_level ?? payload.voltage;
            if (batt != null) parts.push(`batt ${batt}`);
            if (payload.temperature != null) parts.push(`${payload.temperature}°C`);
        } else if (ptype === 'nodeinfo') {
            const name = payload.long_name || payload.short_name;
            if (name) parts.push(name);
            if (payload.role) parts.push(`role: ${payload.role}`);
        } else if (ptype === 'waypoint') {
            if (payload.name) parts.push(payload.name);
            const lat = payload.latitude;
            const lon = payload.longitude;
            if (lat != null && lon != null) parts.push(`${lat.toFixed(4)}, ${lon.toFixed(4)}`);
        } else if (ptype === 'range_test') {
            if (payload.text) parts.push(`seq ${payload.text}`);
        } else if (ptype === 'store_forward') {
            if (payload.rr != null) parts.push(`rr=${payload.rr}`);
            if (payload.messages_total != null) parts.push(`msgs ${payload.messages_total}`);
        } else if (ptype === 'detection_sensor') {
            if (payload.text) parts.push(payload.text.length > 60 ? payload.text.slice(0, 60) + '…' : payload.text);
        } else if (ptype === 'paxcounter') {
            if (payload.wifi != null) parts.push(`wifi ${payload.wifi}`);
            if (payload.ble != null) parts.push(`ble ${payload.ble}`);
        } else if (ptype === 'map_report') {
            const name = payload.long_name || payload.short_name;
            if (name) parts.push(name);
            if (payload.firmware_version) parts.push(`fw ${payload.firmware_version}`);
        } else if (ptype === 'encrypted') {
            if (payload.payload_size != null) parts.push(`${payload.payload_size} bytes`);
            if (payload.channel_hash != null) parts.push(`ch 0x${payload.channel_hash.toString(16).padStart(2, '0')}`);
        }
        return parts.join('  ');
    }

    _safeClass(str) {
        return (str || '').replace(/[^a-zA-Z0-9_-]/g, '');
    }

    _formatTime(isoString) {
        try {
            const date = new Date(isoString);
            return date.toLocaleTimeString('en-US', {
                hour12: true,
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit',
            });
        } catch {
            return '--:--:--';
        }
    }

    _shortId(id) {
        if (!id) return '--';
        if (id === 'ffffffff') return 'BCAST';
        if (id === 'ffff') return 'BCAST';
        return id.length > 6 ? `!${id.slice(-4)}` : id;
    }

    _updateCounters() {
        const liveCount = document.getElementById('live-count');
        if (liveCount) liveCount.textContent = this.totalCount;

        const badge = document.getElementById('packet-count-badge');
        if (badge) badge.textContent = `${this.totalCount} packets`;
    }
}

window.PacketFeed = PacketFeed;
