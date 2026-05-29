/**
 * Rich node card list for the dashboard side panel.
 * Renders Meshtastic-app-style cards with avatar, signal,
 * telemetry chips, role, hardware, and online status.
 */
class NodeCards {
    /** Match Meshtastic-style "recently heard" (not cloud device heartbeat at 15 min). */
    static ONLINE_THRESHOLD_MS = 2 * 60 * 60 * 1000;
    static SORT_KEYS = new Set(['last_heard', 'signal', 'hops', 'name']);
    static FILTER_KEYS = new Set(['all', 'direct', 'relayed']);
    static SORT_STORAGE_KEY = 'meshpoint.nodeCards.sortBy';
    static FILTER_STORAGE_KEY = 'meshpoint.nodeCards.filter';

    constructor(containerId, onCardClick) {
        this._container = document.getElementById(containerId);
        this._onCardClick = onCardClick;
        this._nodes = [];
        this._searchQuery = '';
        this._sortBy = this._loadSavedSort();
        this._filter = this._loadSavedFilter();

        const searchEl = document.getElementById('node-search');
        if (searchEl) {
            searchEl.addEventListener('input', (e) => {
                this._searchQuery = e.target.value.toLowerCase();
                this._render();
            });
        }
        this._wireSort();
        this._wireFilter();
        if (window.MeshpointDisplayUnits) {
            window.MeshpointDisplayUnits.onChange(() => this._render());
        }
    }

    _loadSavedSort() {
        try {
            const v = localStorage.getItem(NodeCards.SORT_STORAGE_KEY);
            return NodeCards.SORT_KEYS.has(v) ? v : 'last_heard';
        } catch (_e) {
            return 'last_heard';
        }
    }

    _loadSavedFilter() {
        try {
            const v = localStorage.getItem(NodeCards.FILTER_STORAGE_KEY);
            return NodeCards.FILTER_KEYS.has(v) ? v : 'all';
        } catch (_e) {
            return 'all';
        }
    }

    _saveSort(value) {
        try { localStorage.setItem(NodeCards.SORT_STORAGE_KEY, value); }
        catch (_e) { /* private mode / quota -- best-effort */ }
    }

    _saveFilter(value) {
        try { localStorage.setItem(NodeCards.FILTER_STORAGE_KEY, value); }
        catch (_e) { /* private mode / quota -- best-effort */ }
    }

    _wireSort() {
        const select = document.getElementById('node-sort');
        if (!select) return;
        select.value = this._sortBy;
        select.addEventListener('change', (e) => {
            const next = e.target.value;
            if (!NodeCards.SORT_KEYS.has(next)) return;
            this._sortBy = next;
            this._saveSort(next);
            this._render();
        });
    }

    _wireFilter() {
        const buttons = document.querySelectorAll('[data-filter]');
        if (!buttons.length) return;
        buttons.forEach((btn) => {
            const value = btn.dataset.filter;
            btn.classList.toggle('nc-pill--active', value === this._filter);
            btn.addEventListener('click', () => {
                if (!NodeCards.FILTER_KEYS.has(value)) return;
                this._filter = value;
                this._saveFilter(value);
                buttons.forEach((b) => {
                    b.classList.toggle('nc-pill--active', b.dataset.filter === value);
                });
                this._render();
            });
        });
    }

    loadNodes(nodes) {
        this._nodes = nodes;
        this._render();
    }

    updateFromPacket(packet) {
        if (!packet.source_id) return;
        const idx = this._nodes.findIndex(n => n.node_id === packet.source_id);
        if (idx >= 0) {
            const n = this._nodes[idx];
            n.last_heard = new Date().toISOString();
            if (packet.rssi != null) n.latest_rssi = packet.rssi;
            if (packet.snr != null) n.latest_snr = packet.snr;
            if (packet.decoded_payload?.long_name) {
                n.long_name = packet.decoded_payload.long_name;
            }
            this._nodes.splice(idx, 1);
            this._nodes.unshift(n);
        } else {
            this._nodes.unshift({
                node_id: packet.source_id,
                long_name: packet.decoded_payload?.long_name || null,
                short_name: packet.decoded_payload?.short_name || null,
                protocol: packet.protocol || 'meshtastic',
                last_heard: new Date().toISOString(),
                latest_rssi: packet.rssi,
                latest_snr: packet.snr,
            });
        }
        this._render();
    }

    _render() {
        let working = this._nodes;
        if (this._searchQuery) {
            working = working.filter(n => {
                const name = (n.long_name || n.short_name || '').toLowerCase();
                const id = (n.node_id || '').toLowerCase();
                return name.includes(this._searchQuery) || id.includes(this._searchQuery);
            });
        }
        working = this._applyFilter(working);
        working = this._applySort(working);

        if (working.length === 0) {
            this._container.innerHTML =
                '<div class="nc-empty">No nodes found</div>';
            return;
        }

        this._container.innerHTML = working.map(n => this._buildCard(n)).join('');

        this._container.querySelectorAll('.nc-card').forEach(el => {
            el.addEventListener('click', () => {
                const nodeId = el.dataset.nodeId;
                const node = this._nodes.find(n => n.node_id === nodeId);
                if (node && this._onCardClick) this._onCardClick(node);
            });
        });
    }

    _applyFilter(nodes) {
        if (this._filter === 'direct') {
            return nodes.filter(n => Number(n.latest_hops ?? n.hop_count ?? 0) === 0);
        }
        if (this._filter === 'relayed') {
            return nodes.filter(n => Number(n.latest_hops ?? n.hop_count ?? 0) > 0);
        }
        return nodes;
    }

    _applySort(nodes) {
        const cmp = this._comparator();
        return nodes.slice().sort(cmp);
    }

    _comparator() {
        const heardDesc = (a, b) => this._compareLastHeardDesc(a, b);
        switch (this._sortBy) {
            case 'signal':
                return (a, b) => this._compareNumDesc(
                    a.latest_rssi ?? a.rssi, b.latest_rssi ?? b.rssi
                ) || heardDesc(a, b);
            case 'hops':
                return (a, b) => this._compareNumAsc(
                    a.latest_hops ?? a.hop_count, b.latest_hops ?? b.hop_count
                ) || heardDesc(a, b);
            case 'name':
                return (a, b) => this._compareName(a, b);
            case 'last_heard':
            default:
                return heardDesc;
        }
    }

    _compareNumDesc(a, b) {
        const an = (a == null || Number.isNaN(Number(a))) ? null : Number(a);
        const bn = (b == null || Number.isNaN(Number(b))) ? null : Number(b);
        if (an === null && bn === null) return 0;
        if (an === null) return 1;
        if (bn === null) return -1;
        return bn - an;
    }

    _compareNumAsc(a, b) {
        const an = (a == null || Number.isNaN(Number(a))) ? null : Number(a);
        const bn = (b == null || Number.isNaN(Number(b))) ? null : Number(b);
        if (an === null && bn === null) return 0;
        if (an === null) return 1;
        if (bn === null) return -1;
        return an - bn;
    }

    _compareLastHeardDesc(a, b) {
        const am = this._heardMs(a.last_heard || a.last_seen);
        const bm = this._heardMs(b.last_heard || b.last_seen);
        const aMissing = Number.isNaN(am);
        const bMissing = Number.isNaN(bm);
        if (aMissing && bMissing) return 0;
        if (aMissing) return 1;
        if (bMissing) return -1;
        return bm - am;
    }

    _compareName(a, b) {
        const an = (a.long_name || a.short_name || a.node_id || '').toString();
        const bn = (b.long_name || b.short_name || b.node_id || '').toString();
        return an.localeCompare(bn, undefined, { sensitivity: 'base' });
    }

    _buildCard(n) {
        const name = this._esc(n.display_name || n.long_name || n.short_name || n.node_id || '--');
        const shortLabel = this._esc(n.short_name || (n.node_id || '').slice(-4)).toUpperCase();
        const avatarColor = this._hashColor(n.node_id || '');
        const proto = n.protocol || 'meshtastic';
        const protoBadge = proto === 'meshcore' ? 'MC' : 'MT';
        const heardAt = n.last_heard || n.last_seen;
        const online = this._isOnline(heardAt);
        const onlineDot = online
            ? '<span class="nc-online nc-online--on" title="Heard within 2 hours"></span>'
            : '<span class="nc-online nc-online--off" title="Not heard within 2 hours"></span>';

        const signal = this._buildSignal(n);
        const telemetry = this._buildTelemetry(n);
        const meta = this._buildMeta(n);

        return `<div class="nc-card" data-node-id="${this._esc(n.node_id)}">
            <div class="nc-card__top">
                <div class="nc-avatar" style="background:${avatarColor}">${shortLabel}</div>
                <div class="nc-card__identity">
                    <div class="nc-card__name">${onlineDot} ${name}</div>
                    <div class="nc-card__heard">${this._timeAgo(heardAt)}</div>
                </div>
                <span class="nc-proto nc-proto--${proto}">${protoBadge}</span>
            </div>
            ${signal}
            ${telemetry}
            ${meta}
        </div>`;
    }

    _buildSignal(n) {
        const parts = [];
        const rssi = n.latest_rssi ?? n.rssi;
        const snr = n.latest_snr ?? n.snr;

        if (rssi != null) {
            const q = this._signalQuality(rssi);
            parts.push(`<span class="nc-chip nc-chip--signal nc-chip--${q.cls}">
                ${this._signalBars(rssi)} ${rssi.toFixed(0)} dBm</span>`);
            if (snr != null) {
                parts.push(`<span class="nc-chip">SNR ${snr.toFixed(1)} dB</span>`);
            }
            parts.push(`<span class="nc-chip nc-chip--quality nc-chip--${q.cls}">${q.label}</span>`);
        }

        if (n.latest_hops != null && n.latest_hops > 0) {
            parts.push(`<span class="nc-chip">${n.latest_hops} hop${n.latest_hops > 1 ? 's' : ''}</span>`);
        }

        return parts.length
            ? `<div class="nc-card__row">${parts.join('')}</div>`
            : '';
    }

    _buildTelemetry(n) {
        const parts = [];
        const voltage = n.latest_voltage;
        const battery = n.latest_battery;
        const temp = n.latest_temperature;
        const humidity = n.latest_humidity;
        const chUtil = n.latest_channel_util;
        const airUtil = n.latest_air_util;
        const alt = n.altitude;

        if (voltage != null) {
            parts.push(`<span class="nc-chip nc-chip--telem">&#9889; ${voltage.toFixed(2)}V</span>`);
        }
        if (battery != null && battery > 0) {
            parts.push(`<span class="nc-chip nc-chip--telem">${this._batteryIcon(battery)} ${battery}%</span>`);
        }
        if (alt != null) {
            const altLabel = window.MeshpointDisplayUnits
                ? window.MeshpointDisplayUnits.formatAltitude(alt)
                : `${Math.round(alt)} ft`;
            if (altLabel) {
                parts.push(`<span class="nc-chip nc-chip--telem">&#9650; ${altLabel}</span>`);
            }
        }
        if (temp != null) {
            const tempLabel = window.MeshpointDisplayUnits
                ? window.MeshpointDisplayUnits.formatTemperature(temp)
                : `${temp.toFixed(1)}\u00B0F`;
            if (tempLabel) {
                parts.push(`<span class="nc-chip nc-chip--telem">&#127777; ${tempLabel}</span>`);
            }
        }
        if (humidity != null) {
            parts.push(`<span class="nc-chip nc-chip--telem">&#128167; ${humidity.toFixed(0)}%</span>`);
        }
        if (chUtil != null) {
            parts.push(`<span class="nc-chip nc-chip--telem">ChUtil ${chUtil.toFixed(1)}%</span>`);
        }
        if (airUtil != null) {
            parts.push(`<span class="nc-chip nc-chip--telem">AirUtil ${airUtil.toFixed(1)}%</span>`);
        }

        return parts.length
            ? `<div class="nc-card__row">${parts.join('')}</div>`
            : '';
    }

    _buildMeta(n) {
        const parts = [];
        if (n.hardware_model) {
            parts.push(`<span class="nc-chip nc-chip--meta">${this._esc(n.hardware_model)}</span>`);
        }
        if (n.role != null) {
            parts.push(`<span class="nc-chip nc-chip--meta">${this._roleName(n.role)}</span>`);
        }
        parts.push(`<span class="nc-chip nc-chip--id">!${this._esc(n.node_id)}</span>`);

        return `<div class="nc-card__row nc-card__row--meta">${parts.join('')}</div>`;
    }

    _signalBars(rssi) {
        const level = rssi > -80 ? 5 : rssi > -95 ? 4 : rssi > -110 ? 3 : rssi > -125 ? 2 : 1;
        let bars = '';
        for (let i = 1; i <= 5; i++) {
            const active = i <= level ? 'active' : '';
            bars += `<span class="nc-bar nc-bar--h${i} ${active}"></span>`;
        }
        return `<span class="nc-bars">${bars}</span>`;
    }

    _signalQuality(rssi) {
        if (rssi > -80) return { label: 'Excellent', cls: 'excellent' };
        if (rssi > -95) return { label: 'Good', cls: 'good' };
        if (rssi > -110) return { label: 'Fair', cls: 'fair' };
        return { label: 'Poor', cls: 'poor' };
    }

    _batteryIcon(pct) {
        if (pct > 75) return '&#128267;';
        if (pct > 25) return '&#128268;';
        return '&#128269;';
    }

    _roleName(role) {
        const names = {
            0: 'CLIENT', 1: 'CLIENT_MUTE', 2: 'ROUTER',
            3: 'ROUTER_CLIENT', 4: 'REPEATER', 5: 'TRACKER',
            6: 'SENSOR', 7: 'TAK', 8: 'CLIENT_HIDDEN',
            9: 'LOST_AND_FOUND', 10: 'TAK_TRACKER',
        };
        if (typeof role === 'number') return names[role] || `ROLE_${role}`;
        return String(role).toUpperCase();
    }

    _heardMs(ts) {
        if (!ts) return NaN;
        const raw = String(ts).trim();
        const hasTz = /[zZ]$|[+-]\d{2}:\d{2}$/.test(raw);
        const iso = hasTz ? raw : raw.replace(' ', 'T') + 'Z';
        const ms = Date.parse(iso);
        return Number.isNaN(ms) ? NaN : ms;
    }

    _isOnline(lastHeard) {
        const ms = this._heardMs(lastHeard);
        if (Number.isNaN(ms)) return false;
        return (Date.now() - ms) < NodeCards.ONLINE_THRESHOLD_MS;
    }

    _timeAgo(ts) {
        if (!ts) return '--';
        const heardMs = this._heardMs(ts);
        if (Number.isNaN(heardMs)) return '--';
        const diff = Math.floor((Date.now() - heardMs) / 1000);
        if (diff < 60) return 'Now';
        if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
        if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
        return `${Math.floor(diff / 86400)}d ago`;
    }

    _hashColor(str) {
        let hash = 0;
        for (let i = 0; i < str.length; i++) {
            hash = str.charCodeAt(i) + ((hash << 5) - hash);
        }
        const hue = Math.abs(hash) % 360;
        return `hsl(${hue}, 55%, 45%)`;
    }

    _esc(str) {
        const el = document.createElement('span');
        el.textContent = str || '';
        return el.innerHTML;
    }
}
