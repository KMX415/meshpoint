/**
 * Simple live packet feed for the local Meshpoint dashboard.
 * Renders incoming packets via WebSocket; row click opens PacketDetailModal.
 */
class SimplePacketFeed {
    constructor(tbodyId, maxRows) {
        this._tbody = document.getElementById(tbodyId);
        this._maxRows = maxRows || 200;
        this._count = 0;
        this._packets = [];
        this._nodeByLastByte = new Map();
        this._onFocus = null;
        const pills = document.getElementById('packet-preset-pills');
        if (window.MeshpointRadioViewFilter) {
            MeshpointRadioViewFilter.wirePills(pills);
            document.addEventListener(MeshpointRadioViewFilter.EVENT, () => this._render());
        }
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
        this._packets.unshift(packet);
        if (this._packets.length > this._maxRows) {
            this._packets.length = this._maxRows;
        }
        this._count += 1;
        this._render();
    }

    _render() {
        if (!this._tbody) return;
        const key = window.MeshpointRadioViewFilter
            ? MeshpointRadioViewFilter.current()
            : 'all';
        const visible = window.MeshpointRadioViewFilter
            ? this._packets.filter((p) => MeshpointRadioViewFilter.matchesPacket(p, key))
            : this._packets;
        this._tbody.replaceChildren();
        for (const packet of visible) {
            this._tbody.appendChild(this._buildRow(packet));
        }
        const countEl = document.getElementById('packet-count');
        if (countEl) countEl.textContent = this._count;
    }

    _buildRow(packet) {
        const tr = document.createElement('tr');
        tr.classList.add('packet-row', 'packet-row--new');
        tr.addEventListener('animationend', () => tr.classList.remove('packet-row--new'));
        tr.innerHTML = this._rowHtml(packet);
        tr.addEventListener('click', () => this._openDetail(tr, packet));
        return tr;
    }

    _rowHtml(packet) {
        const time = this._formatTime(packet);
        const srcShort = this._shortId(packet.source_id);
        const relayByte = packet.relay_node || 0;
        const srcCell = relayByte
            ? `${srcShort} <span class="relay-hop">↝ ${this._resolveRelay(relayByte)}</span>`
            : srcShort;
        const sig = packet.signal || {};
        const rawRssi = sig.rssi != null ? sig.rssi : packet.rssi;
        const rawSnr = sig.snr != null ? sig.snr : packet.snr;
        const rssiVal = rawRssi != null ? Number(rawRssi).toFixed(0) : null;
        const type = packet.packet_type || '--';
        const protocol = packet.protocol || 'meshtastic';
        const hops = packet.hop_start > 0
            ? `${packet.hop_start - packet.hop_limit}/${packet.hop_start}`
            : '--';
        const freqMhz = sig.frequency_mhz || packet.frequency_mhz;
        const freq = freqMhz ? `${Number(freqMhz).toFixed(1)}` : '--';
        const sfVal = sig.spreading_factor || packet.spreading_factor;
        const sf = sfVal ? `SF${sfVal}` : '--';
        return `
            <td>${time}</td>
            <td class="protocol-${protocol}">${protocol}</td>
            <td class="td-source">${srcCell}</td>
            <td>${this._shortId(packet.destination_id)}</td>
            <td class="type-${type.replace(/[^a-zA-Z0-9_-]/g, '')}">${type}</td>
            <td class="${this._rssiClass(rssiVal)}">${rssiVal != null ? rssiVal : '--'}</td>
            <td>${rawSnr != null ? Number(rawSnr).toFixed(1) : '--'}</td>
            <td>${this._presetChip(packet)}</td>
            <td class="td-freq">${freq}</td>
            <td class="td-sf">${sf}</td>
            <td>${hops}</td>
            <td class="packet-details-cell type-${type.replace(/[^a-zA-Z0-9_-]/g, '')}">${this._esc(this._summarize(packet))}</td>
        `;
    }

    _formatTime(packet) {
        if (packet.rx_time) return new Date(packet.rx_time * 1000).toLocaleTimeString();
        if (packet.timestamp) return new Date(packet.timestamp).toLocaleTimeString();
        return new Date().toLocaleTimeString();
    }

    _presetChip(packet) {
        const preset = window.ModemPresetLabel
            ? ModemPresetLabel.fromPacket(packet)
            : null;
        if (!preset) return '<span class="packet-chip packet-chip--unknown">--</span>';
        return `<span class="packet-chip packet-chip--${preset.key}">${preset.chip}</span>`;
    }

    _openDetail(tr, packet) {
        if (!window.PacketDetailModal) return;

        if (this._onFocus) this._onFocus(packet.source_id);

        window.PacketDetailModal.show(packet, {
            formatNodeId: (id) => this._shortId(id),
            selectedRow: tr,
            onClose: () => {
                if (this._onFocus) this._onFocus(null);
            },
        });
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
                if (p.battery_level != null) {
                    // Credit: javastraat/meshpoint 29368c0
                    parts.push(p.battery_level === 101
                        ? 'batt=powered'
                        : `batt=${p.battery_level}%`);
                }
                if (p.voltage != null) parts.push(`${Number(p.voltage).toFixed(1)}V`);
                if (p.temperature != null) {
                    const t = window.MeshpointDisplayUnits
                        ? window.MeshpointDisplayUnits.formatTemperature(p.temperature)
                        : `${Number(p.temperature).toFixed(0)}°C`;
                    if (t) parts.push(t);
                }
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
}
