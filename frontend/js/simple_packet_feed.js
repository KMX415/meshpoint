/**
 * Simple live packet feed for the local Meshpoint dashboard.
 * Renders incoming packets via WebSocket with expand-on-click.
 */
class SimplePacketFeed {
    constructor(tbodyId, maxRows) {
        this._tbody = document.getElementById(tbodyId);
        this._maxRows = maxRows || 200;
        this._count = 0;

        this._visibleCount = 0;
        this._typeFilter = 'all';
        this._knownTypes = new Set();
        this._filterSelect = document.getElementById('packet-type-filter');
        if (this._filterSelect) {
            this._filterSelect.addEventListener('change', () => {
                this.setTypeFilter(this._filterSelect.value);
            });
        }

        this._nodeByLastByte = new Map();
        this._onFocus = null;
    }

    setOnFocus(cb) {
        this._onFocus = cb;
    }

    loadNodes(nodes) {
        this._nodeByLastByte.clear();
        for (const node of nodes) {
            const id = node.node_id;
            if (id && id.length >= 2) {
                this._nodeByLastByte.set(id.slice(-2).toLowerCase(), id);
            }
        }
    }

    addPacket(packet) {
        this._registerPacketType(packet.packet_type);
        const tr = document.createElement('tr');
        tr.classList.add('packet-row--new');
        tr.addEventListener('animationend', () => tr.classList.remove('packet-row--new'));

        const time = packet.rx_time
            ? new Date(packet.rx_time * 1000).toLocaleTimeString()
            : packet.timestamp
                ? new Date(packet.timestamp).toLocaleTimeString()
                : new Date().toLocaleTimeString();

        const srcShort = this._shortId(packet.source_id);
        const relayByte = packet.relay_node || 0;
        const srcCell = relayByte
            ? `${srcShort} <span class="relay-hop">↝ ${this._resolveRelay(relayByte)}</span>`
            : srcShort;

        const sig = packet.signal || {};
        const rawRssi = sig.rssi != null ? sig.rssi : packet.rssi;
        const rawSnr = sig.snr != null ? sig.snr : packet.snr;
        const rssiVal = rawRssi != null ? Number(rawRssi).toFixed(0) : null;
        const rssi = rssiVal != null ? rssiVal : '--';
        const snr = rawSnr != null ? `${Number(rawSnr).toFixed(1)}` : '--';
        const type = packet.packet_type || '--';
        const protocol = packet.protocol || 'meshtastic';
        const details = this._summarize(packet);

        const destShort = this._shortId(packet.destination_id);
        const hops = packet.hop_start > 0
            ? `${packet.hop_start - packet.hop_limit}/${packet.hop_start}`
            : '--';

        const typeClass = `type-${type.replace(/[^a-zA-Z0-9_-]/g, '')}`;
        const protocolClass = `protocol-${protocol}`;
        const rssiClass = this._rssiClass(rssiVal);

        const freqMhz = sig.frequency_mhz || packet.frequency_mhz;
        const freq = freqMhz ? `${Number(freqMhz).toFixed(1)}` : '--';
        const sfVal = sig.spreading_factor || packet.spreading_factor;
        const sf = sfVal ? `SF${sfVal}` : '--';

        tr.innerHTML = `
            <td>${time}</td>
            <td class="${protocolClass}">${protocol}</td>
            <td class="td-source">${srcCell}</td>
            <td>${destShort}</td>
            <td class="${typeClass}">${type}</td>
            <td class="${rssiClass}">${rssi}</td>
            <td>${snr}</td>
            <td class="td-freq">${freq}</td>
            <td class="td-sf">${sf}</td>
            <td>${hops}</td>
            <td class="packet-details-cell ${typeClass}">${this._esc(details)}</td>
        `;

        tr.addEventListener('click', () => this._toggleDetail(tr, packet));

        this._tbody.prepend(tr);
        this._applyFilterToRow(tr, packet);
        this._count++;
        this._updateCountBadge();

        while (this._tbody.children.length > this._maxRows * 2) {
            const last = this._tbody.lastChild;
            if (last && !last.classList.contains('packet-detail-row')) {
                if (!last.classList.contains('packet-row--hidden')) {
                    this._visibleCount = Math.max(0, this._visibleCount - 1);
                }
            }
            this._tbody.removeChild(last);
        }
        this._updateCountBadge();
    }

    setTypeFilter(type) {
        this._typeFilter = (type || 'all').toLowerCase();
        const rows = Array.from(this._tbody.querySelectorAll('tr:not(.packet-detail-row)'));
        for (const row of rows) {
            const packetType = row.dataset.packetType || '';
            const visible = this._typeFilter === 'all' || packetType === this._typeFilter;
            row.classList.toggle('packet-row--hidden', !visible);

            const next = row.nextElementSibling;
            if (next && next.classList.contains('packet-detail-row') && !visible) {
                next.remove();
            }
        }
        this._visibleCount = rows.filter(r => !r.classList.contains('packet-row--hidden')).length;
        this._updateCountBadge();
    }

    _toggleDetail(tr, packet) {
        if (tr.classList.contains('packet-row--hidden')) {
            return;
        }
        const next = tr.nextElementSibling;
        if (next && next.classList.contains('packet-detail-row')) {
            next.remove();
            if (this._onFocus) this._onFocus(null);
            return;
        }

        const prev = this._tbody.querySelector('.packet-detail-row');
        if (prev) prev.remove();

        if (this._onFocus) this._onFocus(packet.source_id);

        const detailTr = document.createElement('tr');
        detailTr.classList.add('packet-detail-row');
        const td = document.createElement('td');
        td.colSpan = 11;


        const payload = packet.decoded_payload;
        if (payload && typeof payload === 'object') {
            td.textContent = JSON.stringify(payload, null, 2);
        } else {
            td.textContent = `Source: ${packet.source_id || '--'}\nType: ${packet.packet_type || '--'}\nRSSI: ${packet.rssi || '--'} dBm\nSNR: ${packet.snr || '--'} dB`;
        }

        detailTr.appendChild(td);
        tr.after(detailTr);
    }

    _summarize(packet) {
        const p = packet.decoded_payload;
        if (!p) return '--';

        switch (packet.packet_type) {
            case 'text': return p.text || '--';
            case 'position': {
                const parts = [];
                if (p.latitude != null) parts.push(`${p.latitude.toFixed(4)}`);
                if (p.longitude != null) parts.push(`${p.longitude.toFixed(4)}`);
                if (p.altitude != null) parts.push(`alt ${p.altitude}m`);
                return parts.join(', ') || '--';
            }
            case 'nodeinfo':
                return [p.long_name, p.short_name, p.hw_model].filter(Boolean).join(' ') || '--';
            case 'telemetry': {
                const parts = [];
                if (p.battery_level != null) parts.push(`batt=${p.battery_level}%`);
                if (p.voltage != null) parts.push(`${Number(p.voltage).toFixed(1)}V`);
                if (p.temperature != null) parts.push(`${Number(p.temperature).toFixed(0)}°C`);
                return parts.join(' ') || '--';
            }
            default: return '--';
        }
    }

    _rssiClass(val) {
        if (val == null) return '';
        const n = Number(val);
        if (n >= -90) return 'rssi-good';
        if (n >= -110) return 'rssi-mid';
        return 'rssi-bad';
    }

    _resolveRelay(relayByte) {
        const key = relayByte.toString(16).padStart(2, '0');
        const fullId = this._nodeByLastByte.get(key);
        return fullId ? this._shortId(fullId) : `!${key}`;
    }

    _shortId(id) {
        if (!id) return '--';
        if (id === 'ffffffff' || id === 'ffff') return 'BCAST';
        return id.length > 6 ? `!${id.slice(-4)}` : id;
    }

    _esc(str) {
        const el = document.createElement('span');
        el.textContent = str;
        return el.innerHTML;
    }

    _registerPacketType(type) {
        if (!type) return;
        const normalized = String(type).toLowerCase();
        if (this._knownTypes.has(normalized)) return;
        this._knownTypes.add(normalized);
        if (!this._filterSelect) return;

        const option = document.createElement('option');
        option.value = normalized;
        option.textContent = String(type).toUpperCase();
        this._filterSelect.appendChild(option);
    }

    _applyFilterToRow(tr, packet) {
        const packetType = String(packet.packet_type || '').toLowerCase();
        tr.dataset.packetType = packetType;
        const visible = this._typeFilter === 'all' || packetType === this._typeFilter;
        tr.classList.toggle('packet-row--hidden', !visible);
        if (visible) this._visibleCount++;
    }

    _updateCountBadge() {
        const countEl = document.getElementById('packet-count');
        if (!countEl) return;
        if (this._typeFilter === 'all') {
            countEl.textContent = String(this._count);
            return;
        }
        countEl.textContent = `${this._visibleCount}/${this._count}`;
    }
}
