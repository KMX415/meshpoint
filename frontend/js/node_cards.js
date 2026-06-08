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
    static FAVORITES_ONLY_STORAGE_KEY = 'meshpoint.nodeCards.favoritesOnly';

    constructor(containerId, onCardClick) {
        this._container = document.getElementById(containerId);
        this._onCardClick = onCardClick;
        this._nodes = [];
        this._searchQuery = '';
        this._sortBy = this._loadSavedSort();
        this._filter = this._loadSavedFilter();
        this._favoritesOnly = this._loadSavedFavoritesOnly();
        this._observer = null;
        this._sparklines = new Map();
        this._bucketCache = new Map();
        this._loadingNodes = new Set();
        this._signalHealth = null;
        this._configPromise = null;
        this._quarantine = new Map();
        this._quarantineTimer = null;

        const searchEl = document.getElementById('node-search');
        if (searchEl) {
            searchEl.addEventListener('input', (e) => {
                this._searchQuery = e.target.value.toLowerCase();
                this._render();
            });
        }
        this._wireSort();
        this._wireFilter();
        this._wireFavoritesToggle();
        if (window.MeshpointDisplayUnits) {
            window.MeshpointDisplayUnits.onChange(() => this._render());
        }
        if (window.MeshpointNodeFavorites) {
            window.MeshpointNodeFavorites.onChange(() => this._render());
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

    _loadSavedFavoritesOnly() {
        try {
            return localStorage.getItem(NodeCards.FAVORITES_ONLY_STORAGE_KEY) === '1';
        } catch (_e) {
            return false;
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

    _saveFavoritesOnly(value) {
        try {
            localStorage.setItem(NodeCards.FAVORITES_ONLY_STORAGE_KEY, value ? '1' : '0');
        } catch (_e) { /* private mode / quota -- best-effort */ }
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

    _wireFavoritesToggle() {
        const btn = document.getElementById('node-favorites-toggle');
        if (!btn) return;
        this._reflectFavoritesToggle(btn);
        btn.addEventListener('click', () => {
            this._favoritesOnly = !this._favoritesOnly;
            this._saveFavoritesOnly(this._favoritesOnly);
            this._reflectFavoritesToggle(btn);
            this._render();
        });
    }

    _reflectFavoritesToggle(btn) {
        const on = this._favoritesOnly;
        btn.classList.toggle('nc-pill--active', on);
        btn.setAttribute('aria-pressed', on ? 'true' : 'false');
        btn.innerHTML = on ? '\u2605' : '\u2606';
        btn.title = on ? 'Showing favorites only (click to clear)' : 'Show only favorited nodes';
    }

    loadNodes(nodes) {
        this._nodes = nodes;
        this._render();
    }

    setQuarantine(entries) {
        this._quarantine.clear();
        (entries || []).forEach((entry) => {
            if (entry && entry.node_id) {
                this._quarantine.set(entry.node_id, { ...entry });
            }
        });
        this._syncQuarantineTimer();
        this._render();
    }

    _syncQuarantineTimer() {
        if (this._quarantine.size === 0) {
            if (this._quarantineTimer) {
                clearInterval(this._quarantineTimer);
                this._quarantineTimer = null;
            }
            return;
        }
        if (this._quarantineTimer) return;
        this._quarantineTimer = setInterval(() => {
            let changed = false;
            for (const [nodeId, entry] of this._quarantine) {
                const next = Math.max(0, (entry.seconds_remaining ?? 0) - 1);
                if (next === 0) {
                    this._quarantine.delete(nodeId);
                } else {
                    entry.seconds_remaining = next;
                }
                changed = true;
            }
            if (changed) this._render();
            if (this._quarantine.size === 0) this._syncQuarantineTimer();
        }, 1000);
    }

    _ensureSignalHealthConfig() {
        if (this._configPromise) return this._configPromise;
        this._configPromise = fetch('/api/config', { credentials: 'same-origin' })
            .then((res) => (res.ok ? res.json() : {}))
            .then((data) => {
                this._signalHealth = data.signal_health || null;
            })
            .catch(() => {
                this._signalHealth = null;
            });
        return this._configPromise;
    }

    updateFromPacket(packet) {
        if (!packet.source_id) return;
        this._bucketCache.delete(packet.source_id);
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

        this._container.querySelectorAll('[data-favorite-toggle]').forEach((btn) => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const card = btn.closest('.nc-card');
                const nodeId = card?.dataset?.nodeId;
                if (nodeId && window.MeshpointNodeFavorites) {
                    window.MeshpointNodeFavorites.toggle(nodeId);
                }
            });
        });

        this._container.querySelectorAll('.nc-card').forEach(el => {
            el.addEventListener('click', () => {
                const nodeId = el.dataset.nodeId;
                const node = this._nodes.find(n => n.node_id === nodeId);
                if (node && this._onCardClick) this._onCardClick(node);
            });
        });

        this._observeCards();
    }

    _observeCards() {
        if (this._observer) this._observer.disconnect();
        if (!window.SignalSparkline || typeof IntersectionObserver === 'undefined') {
            return;
        }

        this._ensureSignalHealthConfig();
        this._observer = new IntersectionObserver((entries) => {
            entries.forEach((entry) => {
                if (!entry.isIntersecting) return;
                const card = entry.target;
                const nodeId = card.dataset.nodeId;
                if (nodeId) this._loadSignalData(nodeId, card);
                this._observer.unobserve(card);
            });
        }, { root: null, rootMargin: '48px', threshold: 0.08 });

        this._container.querySelectorAll('.nc-card').forEach((card) => {
            this._observer.observe(card);
        });
    }

    async _loadSignalData(nodeId, cardEl) {
        if (!nodeId || this._loadingNodes.has(nodeId)) return;

        if (this._bucketCache.has(nodeId)) {
            this._applySignalHealth(nodeId, cardEl, this._bucketCache.get(nodeId));
            return;
        }

        this._loadingNodes.add(nodeId);
        try {
            await this._ensureSignalHealthConfig();
            const url = `/api/nodes/${encodeURIComponent(nodeId)}/metrics_history`
                + '?hours=24&bucket_minutes=15&limit=100';
            const res = await fetch(url, { credentials: 'same-origin' });
            if (!res.ok) return;
            const data = await res.json();
            const buckets = data.signal_buckets || [];
            this._bucketCache.set(nodeId, buckets);
            this._applySignalHealth(nodeId, cardEl, buckets);
        } catch (e) {
            console.error('Signal bucket load failed:', nodeId, e);
        } finally {
            this._loadingNodes.delete(nodeId);
        }
    }

    _applySignalHealth(nodeId, cardEl, buckets) {
        const canvas = cardEl.querySelector('[data-sparkline]');
        if (!canvas || !window.SignalSparkline) return;

        let spark = this._sparklines.get(nodeId);
        if (!spark) {
            spark = new window.SignalSparkline(canvas);
            this._sparklines.set(nodeId, spark);
        }
        spark.setBuckets(buckets, { bucketMinutes: 15 });

        const badge = cardEl.querySelector('[data-health-badge]');
        if (!badge) return;

        const health = window.SignalSparkline.classifyHealth(
            buckets,
            this._signalHealth,
        );
        if (!health.level) {
            badge.className = 'nc-health-badge nc-health-badge--hidden';
            badge.setAttribute('aria-hidden', 'true');
            badge.textContent = '';
            badge.removeAttribute('title');
            return;
        }

        badge.className = `nc-health-badge nc-health-badge--${health.level}`;
        badge.setAttribute('aria-hidden', 'false');
        badge.title = `1h avg ${health.avgRssi.toFixed(0)} dBm (${health.packetCount} pkts)`;
        badge.textContent = health.level === 'green'
            ? 'Good'
            : health.level === 'yellow'
                ? 'Fair'
                : 'Poor';
    }

    _applyFilter(nodes) {
        const filtered = window.MeshpointNodeCardsSort
            ? window.MeshpointNodeCardsSort.applyFilter(nodes, this._filter)
            : nodes;
        if (this._favoritesOnly && window.MeshpointNodeFavorites) {
            const favs = new Set(window.MeshpointNodeFavorites.list());
            return filtered.filter((n) => favs.has(n.node_id));
        }
        return filtered;
    }

    _applySort(nodes) {
        const favs = window.MeshpointNodeFavorites
            ? new Set(window.MeshpointNodeFavorites.list())
            : new Set();
        if (window.MeshpointNodeCardsSort) {
            return window.MeshpointNodeCardsSort.applySort(nodes, this._sortBy, favs);
        }
        return nodes.slice();
    }

    _buildCard(n) {
        const name = this._esc(n.display_name || n.long_name || n.short_name || n.node_id || '--');
        const shortLabel = this._esc(n.short_name || (n.node_id || '').slice(-4)).toUpperCase();
        const avatarColor = this._hashColor(n.node_id || '');
        const proto = n.protocol || 'meshtastic';
        const protoBadge = proto === 'meshcore' ? 'MC' : 'MT';
        const quarantineBadge = this._quarantineBadge(n.node_id);
        const heardAt = n.last_heard || n.last_seen;
        const online = this._isOnline(heardAt);
        const onlineDot = online
            ? '<span class="nc-online nc-online--on" title="Heard within 2 hours"></span>'
            : '<span class="nc-online nc-online--off" title="Not heard within 2 hours"></span>';
        const isFav = !!(window.MeshpointNodeFavorites && window.MeshpointNodeFavorites.has(n.node_id));
        const favClass = isFav ? ' nc-card__favorite--on' : '';
        const favTitle = isFav ? 'Remove favorite' : 'Add favorite';
        const favGlyph = isFav ? '\u2605' : '\u2606';

        const signal = this._buildSignal(n);
        const health = this._buildHealthRow(n);
        const telemetry = this._buildTelemetry(n);
        const meta = this._buildMeta(n);

        return `<div class="nc-card${isFav ? ' nc-card--fav' : ''}" data-node-id="${this._esc(n.node_id)}">
            <div class="nc-card__top">
                <div class="nc-avatar" style="background:${avatarColor}">${shortLabel}</div>
                <div class="nc-card__identity">
                    <div class="nc-card__name">${onlineDot} ${name}</div>
                    <div class="nc-card__heard">${this._timeAgo(heardAt)}</div>
                </div>
                <button type="button"
                        class="nc-card__favorite${favClass}"
                        data-favorite-toggle
                        aria-label="${favTitle}"
                        aria-pressed="${isFav ? 'true' : 'false'}"
                        title="${favTitle}">${favGlyph}</button>
                ${quarantineBadge}
                <span class="nc-proto nc-proto--${proto}">${protoBadge}</span>
            </div>
            ${signal}
            ${health}
            ${telemetry}
            ${meta}
        </div>`;
    }

    _quarantineBadge(nodeId) {
        const entry = this._quarantine.get(nodeId);
        if (!entry) return '';
        const reason = entry.reason === 'rate_storm' ? 'high rate' : 'replay storm';
        const secs = Math.max(0, entry.seconds_remaining ?? 0);
        const min = Math.floor(secs / 60);
        const sec = secs % 60;
        const countdown = min > 0 ? `${min}m ${sec}s` : `${sec}s`;
        return `<span class="nc-quarantine-badge" title="Storm guard: relay blocked (${reason})">${countdown}</span>`;
    }

    _buildHealthRow(n) {
        const rssi = n.latest_rssi ?? n.rssi;
        if (rssi == null) return '';
        return `<div class="nc-card__health">
            <span class="nc-health-badge nc-health-badge--hidden"
                  data-health-badge
                  aria-hidden="true"></span>
            <canvas class="nc-sparkline" data-sparkline aria-hidden="true"></canvas>
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
