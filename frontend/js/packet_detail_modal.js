/**
 * Modal breakdown of a single packet from the live WebSocket feed.
 * Reads only the in-memory packet object — no extra API calls.
 */
class PacketDetailModal {
    constructor() {
        this._overlay = null;
        this._selectedRow = null;
        this._onClose = null;
        this._onKeyDown = this._onKeyDown.bind(this);
    }

    /**
     * @param {object} packet — WebSocket packet payload
     * @param {{ formatNodeId?: function, onClose?: function, selectedRow?: HTMLElement }} opts
     */
    show(packet, opts = {}) {
        this.close({ skipCallback: true });

        this._onClose = opts.onClose || null;
        this._selectedRow = opts.selectedRow || null;
        if (this._selectedRow) {
            this._selectedRow.classList.add('packet-row--selected');
        }

        const overlay = document.createElement('div');
        overlay.className = 'pdm-overlay';
        overlay.setAttribute('role', 'dialog');
        overlay.setAttribute('aria-modal', 'true');
        overlay.setAttribute('aria-label', 'Packet detail');

        const modal = document.createElement('div');
        modal.className = 'pdm-modal';
        modal.addEventListener('click', (e) => e.stopPropagation());

        const timeLabel = this._formatTime(packet);
        modal.innerHTML = `
            <header class="pdm-modal__header">
                <div>
                    <h2 class="pdm-modal__title">Packet detail</h2>
                    <div class="pdm-modal__meta">${this._esc(timeLabel)} · ${this._esc(packet.packet_type || 'unknown')}</div>
                </div>
                <button type="button" class="pdm-modal__close" aria-label="Close">&times;</button>
            </header>
            <div class="pdm-modal__body"></div>
        `;

        const body = modal.querySelector('.pdm-modal__body');
        body.appendChild(this._buildLayer('RF', this._rfRows(packet)));
        body.appendChild(this._buildLayer('Mesh', this._meshRows(packet, opts.formatNodeId)));
        body.appendChild(this._buildLayer('Payload', this._payloadRows(packet)));
        body.appendChild(this._buildLayer('Capture', this._captureRows(packet)));

        modal.querySelector('.pdm-modal__close').addEventListener('click', () => this.close());
        overlay.addEventListener('click', () => this.close());
        overlay.appendChild(modal);
        document.body.appendChild(overlay);
        this._overlay = overlay;

        document.addEventListener('keydown', this._onKeyDown);
        modal.querySelector('.pdm-modal__close').focus();
    }

    close(opts = {}) {
        document.removeEventListener('keydown', this._onKeyDown);
        if (this._overlay) {
            this._overlay.remove();
            this._overlay = null;
        }
        if (this._selectedRow) {
            this._selectedRow.classList.remove('packet-row--selected');
            this._selectedRow = null;
        }
        const cb = this._onClose;
        this._onClose = null;
        if (!opts.skipCallback && cb) cb();
    }

    _onKeyDown(e) {
        if (e.key === 'Escape') this.close();
    }

    _buildLayer(label, rows) {
        const layer = document.createElement('section');
        layer.className = 'pdm-layer';
        const rowsEl = document.createElement('div');
        rowsEl.className = 'pdm-layer__rows';
        for (const row of rows) {
            if (row.html) {
                rowsEl.insertAdjacentHTML('beforeend', row.html);
            } else if (row.expandable) {
                rowsEl.appendChild(this._expandableBlock(row.key, row.full, row.previewLen));
            } else {
                rowsEl.appendChild(this._row(row.key, row.val, row.valClass));
            }
        }
        layer.innerHTML = `<div class="pdm-layer__label">${this._esc(label)}</div>`;
        layer.appendChild(rowsEl);
        return layer;
    }

    _row(key, val, valClass) {
        const row = document.createElement('div');
        row.className = 'pdm-row';
        const cls = valClass ? ` pdm-row__val--${valClass}` : '';
        row.innerHTML = `
            <span class="pdm-row__key">${this._esc(key)}:</span>
            <span class="pdm-row__val${cls}">${this._esc(val)}</span>
        `;
        return row;
    }

    _expandableBlock(key, fullText, previewLen) {
        const wrap = document.createElement('div');
        wrap.className = 'pdm-row';
        const needsToggle = fullText.length > previewLen;
        const preview = needsToggle ? fullText.slice(0, previewLen) + '…' : fullText;

        const keySpan = document.createElement('span');
        keySpan.className = 'pdm-row__key';
        keySpan.textContent = `${key}:`;

        const pre = document.createElement('pre');
        pre.className = 'pdm-payload-text';
        pre.textContent = preview;

        wrap.appendChild(keySpan);
        wrap.appendChild(pre);

        if (needsToggle) {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'pdm-expand';
            btn.textContent = 'Show more';
            let expanded = false;
            btn.addEventListener('click', () => {
                expanded = !expanded;
                pre.textContent = expanded ? fullText : preview;
                btn.textContent = expanded ? 'Show less' : 'Show more';
            });
            wrap.appendChild(btn);
        }
        return wrap;
    }

    _rfRows(packet) {
        const sig = packet.signal || {};
        const rssi = sig.rssi != null ? sig.rssi : packet.rssi;
        const snr = sig.snr != null ? sig.snr : packet.snr;
        const freq = sig.frequency_mhz != null ? sig.frequency_mhz : packet.frequency_mhz;
        const sf = sig.spreading_factor != null ? sig.spreading_factor : packet.spreading_factor;
        const bw = sig.bandwidth_khz != null ? sig.bandwidth_khz : packet.bandwidth_khz;
        const cr = sig.coding_rate || packet.coding_rate;

        const modemParts = [];
        if (sf != null) modemParts.push(`SF${sf}`);
        if (bw != null) modemParts.push(`BW${Number(bw)}`);
        if (cr) modemParts.push(`CR ${cr}`);

        return [
            { key: 'Frequency', val: freq != null ? `${Number(freq).toFixed(3)} MHz` : 'n/a' },
            { key: 'Modem', val: modemParts.length ? modemParts.join(' · ') : 'n/a' },
            {
                key: 'RSSI',
                val: rssi != null ? `${Number(rssi).toFixed(0)} dBm` : 'n/a',
            },
            {
                key: 'SNR',
                val: snr != null ? `${Number(snr).toFixed(1)} dB` : 'n/a',
            },
        ];
    }

    _meshRows(packet, formatNodeId) {
        const fmt = typeof formatNodeId === 'function' ? formatNodeId : (id) => id || 'n/a';
        const hopsTaken = packet.hop_count != null
            ? packet.hop_count
            : (packet.hop_start > 0 ? packet.hop_start - packet.hop_limit : null);
        const hopLabel = packet.hop_start > 0
            ? `${hopsTaken != null ? hopsTaken : '?' } hop${hopsTaken === 1 ? '' : 's'} taken (${packet.hop_limit} left of ${packet.hop_start})`
            : 'n/a';

        const rows = [
            { key: 'From', val: `${fmt(packet.source_id)} (${packet.source_id || 'n/a'})` },
            { key: 'To', val: `${fmt(packet.destination_id)} (${packet.destination_id || 'n/a'})` },
            { key: 'Type', val: packet.packet_type || 'n/a' },
            { key: 'Protocol', val: packet.protocol || 'n/a' },
            { key: 'Hops', val: hopLabel },
            { key: 'Want ACK', val: packet.want_ack ? 'Yes' : 'No' },
        ];

        if (packet.channel_hash != null && packet.channel_hash !== 0) {
            rows.push({
                key: 'Channel hash',
                val: `0x${Number(packet.channel_hash).toString(16).padStart(2, '0')}`,
            });
        }
        if (packet.relay_node) {
            rows.push({
                key: 'Relay byte',
                val: `0x${Number(packet.relay_node).toString(16).padStart(2, '0')}`,
            });
        }
        if (packet.via_mqtt) {
            rows.push({ key: 'Via MQTT', val: 'Yes' });
        }

        const portnum = packet.decoded_payload && packet.decoded_payload.portnum;
        if (portnum != null) {
            rows.push({ key: 'Portnum', val: String(portnum) });
        }

        return rows;
    }

    _payloadRows(packet) {
        const p = packet.decoded_payload;
        const type = packet.packet_type || 'unknown';
        const decrypted = packet.decrypted !== false && type !== 'encrypted';

        if (!decrypted || type === 'encrypted') {
            const hex = (p && p.raw_hex) ? p.raw_hex : null;
            const rows = [
                {
                    key: 'Decrypt',
                    val: 'No matching key',
                    valClass: 'bad',
                },
                { key: 'Channel', val: this._channelLabel(packet) },
            ];
            if (hex) {
                rows.push({
                    key: 'Raw bytes',
                    expandable: true,
                    full: hex,
                    previewLen: 120,
                });
            }
            return rows;
        }

        const rows = [
            { key: 'Decrypt', val: 'Success', valClass: 'good' },
            { key: 'Channel', val: this._channelLabel(packet) },
        ];

        const summary = this._payloadSummary(packet);
        if (summary) {
            rows.push({ key: 'Content', val: summary });
        } else if (p && typeof p === 'object') {
            rows.push({
                key: 'JSON',
                expandable: true,
                full: JSON.stringify(p, null, 2),
                previewLen: 480,
            });
        } else {
            rows.push({ key: 'Content', val: 'n/a' });
        }

        return rows;
    }

    _captureRows(packet) {
        return [
            { key: 'Packet ID', val: packet.packet_id || 'n/a' },
            { key: 'Source', val: packet.capture_source || 'n/a' },
            { key: 'Timestamp', val: packet.timestamp || 'n/a' },
        ];
    }

    _channelLabel(packet) {
        if (packet.channel_hash != null && packet.channel_hash !== 0) {
            return `hash 0x${Number(packet.channel_hash).toString(16).padStart(2, '0')}`;
        }
        const name = packet.decoded_payload && packet.decoded_payload.channel;
        return name || '(unknown)';
    }

    _payloadSummary(packet) {
        const p = packet.decoded_payload;
        if (!p || typeof p !== 'object') return '';

        switch (packet.packet_type) {
            case 'text':
                return p.text || '';
            case 'position': {
                const parts = [];
                if (p.latitude != null) parts.push(`${Number(p.latitude).toFixed(5)}°`);
                if (p.longitude != null) parts.push(`${Number(p.longitude).toFixed(5)}°`);
                if (p.altitude != null) parts.push(`alt ${p.altitude} m`);
                return parts.join(', ');
            }
            case 'nodeinfo':
                return [p.long_name, p.short_name, p.hw_model].filter(Boolean).join(' · ');
            case 'telemetry': {
                const parts = [];
                if (p.battery_level != null) parts.push(`battery ${p.battery_level}%`);
                if (p.voltage != null) parts.push(`${Number(p.voltage).toFixed(2)} V`);
                if (p.temperature != null) {
                    const t = window.MeshpointDisplayUnits
                        ? window.MeshpointDisplayUnits.formatTemperature(p.temperature)
                        : `${Number(p.temperature).toFixed(0)}°C`;
                    if (t) parts.push(t);
                }
                return parts.join(' · ');
            }
            case 'routing':
                return p.error_reason || p.reply_id != null ? `reply ${p.reply_id}` : '';
            case 'traceroute': {
                const route = Array.isArray(p.route) ? p.route.join(' → ') : '';
                return route ? `route: ${route}` : '';
            }
            case 'neighborinfo': {
                const n = Array.isArray(p.neighbors) ? p.neighbors.length : 0;
                return n ? `${n} neighbor(s) reported` : '';
            }
            default:
                return '';
        }
    }

    _formatTime(packet) {
        if (packet.rx_time) {
            return new Date(packet.rx_time * 1000).toLocaleString();
        }
        if (packet.timestamp) {
            return new Date(packet.timestamp).toLocaleString();
        }
        return new Date().toLocaleString();
    }

    _esc(str) {
        const el = document.createElement('span');
        el.textContent = str == null ? '' : String(str);
        return el.innerHTML;
    }
}

window.PacketDetailModal = new PacketDetailModal();
