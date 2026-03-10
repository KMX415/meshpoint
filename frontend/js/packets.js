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

        const cells = [
            { text: time },
            { text: packet.protocol, cls: `protocol-${this._safeClass(packet.protocol)}` },
            { text: this._shortId(packet.source_id) },
            { text: this._shortId(packet.destination_id) },
            { text: packet.packet_type, cls: `type-${this._safeClass(packet.packet_type)}` },
            { text: rssi },
            { text: snr },
            { text: hops },
        ];
        cells.forEach(({ text, cls }) => {
            const td = document.createElement('td');
            if (cls) td.className = cls;
            td.textContent = text;
            row.appendChild(td);
        });
        return row;
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
