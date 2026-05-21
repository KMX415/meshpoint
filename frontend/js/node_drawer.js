/**
 * Slide-out detail drawer for a selected node.
 * Shows identity, signal, telemetry sections, and action buttons.
 */
class NodeDrawer {
    constructor(drawerId, options = {}) {
        this._drawer = document.getElementById(drawerId);
        this._onSendMessage = options.onSendMessage || null;
        this._onViewOnMap = options.onViewOnMap || null;
        this._currentNode = null;
        this._sections = {};
    }

    async open(node) {
        this._currentNode = node;
        this._renderSkeleton(node);
        this._drawer.classList.add('nd-drawer--open');

        const [detail, telemetry] = await Promise.all([
            this._fetchDetail(node.node_id),
            this._fetchTelemetry(node.node_id),
        ]);

        const merged = { ...node, ...detail };
        if (telemetry) merged._telemetryHistory = telemetry;
        this._currentNode = merged;
        this._renderFull(merged);
    }

    close() {
        this._drawer.classList.remove('nd-drawer--open');
        this._currentNode = null;
    }

    isOpen() {
        return this._drawer.classList.contains('nd-drawer--open');
    }

    _renderSkeleton(node) {
        const name = this._esc(node.display_name || node.long_name || node.short_name || node.node_id);
        const shortLabel = this._esc(node.short_name || (node.node_id || '').slice(-4)).toUpperCase();
        const color = this._hashColor(node.node_id || '');

        this._drawer.innerHTML = `
            <div class="nd-header">
                <div class="nd-header__left">
                    <div class="nd-avatar" style="background:${color}">${shortLabel}</div>
                    <div class="nd-header__info">
                        <div class="nd-header__name">${name}</div>
                        <div class="nd-header__id">!${this._esc(node.node_id)}</div>
                    </div>
                </div>
                <button class="nd-close" title="Close">&times;</button>
            </div>
            <div class="nd-body">
                <div class="nd-loading">Loading details...</div>
            </div>
        `;

        this._drawer.querySelector('.nd-close').addEventListener('click', () => this.close());
    }

    _renderFull(n) {
        const body = this._drawer.querySelector('.nd-body');
        if (!body) return;

        body.innerHTML = '';
        body.appendChild(this._buildActions(n));
        body.appendChild(this._buildInfoSection(n));
        body.appendChild(this._buildSignalSection(n));
        body.appendChild(this._buildDeviceMetrics(n));
        body.appendChild(this._buildEnvironmentMetrics(n));
        body.appendChild(this._buildPositionSection(n));
    }

    _buildActions(n) {
        const div = document.createElement('div');
        div.className = 'nd-actions';

        const msgBtn = document.createElement('button');
        msgBtn.className = 'nd-action-btn nd-action-btn--primary';
        msgBtn.textContent = 'Send Message';
        msgBtn.addEventListener('click', () => {
            if (this._onSendMessage) this._onSendMessage(n);
            this.close();
        });
        div.appendChild(msgBtn);

        if (n.has_position) {
            const mapBtn = document.createElement('button');
            mapBtn.className = 'nd-action-btn';
            mapBtn.textContent = 'View on Map';
            mapBtn.addEventListener('click', () => {
                if (this._onViewOnMap) this._onViewOnMap(n);
                this.close();
            });
            div.appendChild(mapBtn);
        }

        return div;
    }

    _buildInfoSection(n) {
        const rows = [];
        if (n.hardware_model) rows.push(['Hardware', n.hardware_model]);
        if (n.role != null) rows.push(['Role', this._roleName(n.role)]);
        rows.push(['Protocol', (n.protocol || 'meshtastic').toUpperCase()]);
        if (n.firmware_version) rows.push(['Firmware', n.firmware_version]);
        rows.push(['Node ID', `!${n.node_id}`]);
        rows.push(['First Seen', this._formatDate(n.first_seen)]);
        rows.push(['Last Heard', this._formatDate(n.last_heard)]);
        if (n.packet_count) rows.push(['Packets', n.packet_count.toLocaleString()]);

        return this._buildSection('Node Info', rows, true);
    }

    _buildSignalSection(n) {
        const rssi = n.latest_rssi ?? n.rssi;
        const snr = n.latest_snr ?? n.snr;
        const rows = [];

        if (rssi != null) {
            const q = this._signalQuality(rssi);
            rows.push(['RSSI', `${rssi.toFixed(1)} dBm`]);
            rows.push(['Quality', q.label]);
        }
        if (snr != null) rows.push(['SNR', `${snr.toFixed(1)} dB`]);
        if (n.latest_hops != null) rows.push(['Hops', n.latest_hops]);

        return this._buildSection('Signal', rows, true);
    }

    _buildDeviceMetrics(n) {
        const rows = [];
        const v = n.latest_voltage;
        const b = n.latest_battery;
        const ch = n.latest_channel_util;
        const air = n.latest_air_util;

        if (v != null) rows.push(['Voltage', `${v.toFixed(2)} V`]);
        if (b != null && b > 0) rows.push(['Battery', `${b}%`]);
        if (ch != null) rows.push(['Channel Util', `${ch.toFixed(1)}%`]);
        if (air != null) rows.push(['Air Util TX', `${air.toFixed(1)}%`]);

        const telem = n._telemetryHistory;
        if (telem && telem.length > 0) {
            const latest = telem[0];
            if (latest.uptime_seconds) {
                rows.push(['Uptime', this._formatUptime(latest.uptime_seconds)]);
            }
        }

        return this._buildSection('Device Metrics', rows, rows.length > 0);
    }

    _buildEnvironmentMetrics(n) {
        const rows = [];
        const temp = n.latest_temperature;
        const hum = n.latest_humidity;

        if (temp != null) {
            const tempLabel = window.MeshpointDisplayUnits
                ? window.MeshpointDisplayUnits.formatTemperature(temp)
                : `${temp.toFixed(1)}\u00B0F`;
            if (tempLabel) rows.push(['Temperature', tempLabel]);
        }
        if (hum != null) rows.push(['Humidity', `${hum.toFixed(0)}%`]);

        if (temp != null && hum != null) {
            const dpC = this._dewPointCelsius(temp, hum);
            const dpLabel = window.MeshpointDisplayUnits
                ? window.MeshpointDisplayUnits.formatTemperature(dpC)
                : `${(dpC * 9 / 5 + 32).toFixed(1)}\u00B0F`;
            if (dpLabel) rows.push(['Dew Point', dpLabel]);
        }

        const telem = n._telemetryHistory;
        if (telem && telem.length > 0) {
            const latest = telem[0];
            if (latest.barometric_pressure) {
                rows.push(['Pressure', `${latest.barometric_pressure.toFixed(1)} hPa`]);
            }
        }

        return this._buildSection('Environment', rows, rows.length > 0);
    }

    _buildPositionSection(n) {
        const rows = [];
        if (n.latitude != null) rows.push(['Latitude', n.latitude.toFixed(6)]);
        if (n.longitude != null) rows.push(['Longitude', n.longitude.toFixed(6)]);
        if (n.altitude != null) {
            const altLabel = window.MeshpointDisplayUnits
                ? window.MeshpointDisplayUnits.formatAltitude(n.altitude)
                : `${Math.round(n.altitude)} ft`;
            if (altLabel) rows.push(['Altitude', altLabel]);
        }

        return this._buildSection('Position', rows, rows.length > 0);
    }

    _buildSection(title, rows, expanded) {
        const section = document.createElement('div');
        section.className = 'nd-section';

        const header = document.createElement('div');
        header.className = 'nd-section__header';
        header.innerHTML = `<span class="nd-section__title">${title}</span>
            <span class="nd-section__arrow">${expanded ? '\u25BC' : '\u25B6'}</span>`;

        const content = document.createElement('div');
        content.className = 'nd-section__content';
        if (!expanded || rows.length === 0) content.style.display = 'none';

        if (rows.length === 0) {
            content.innerHTML = '<div class="nd-section__empty">No data available</div>';
        } else {
            rows.forEach(([label, value]) => {
                const row = document.createElement('div');
                row.className = 'nd-row';
                row.innerHTML = `<span class="nd-row__label">${label}</span>
                    <span class="nd-row__value">${this._esc(String(value))}</span>`;
                content.appendChild(row);
            });
        }

        header.addEventListener('click', () => {
            const visible = content.style.display !== 'none';
            content.style.display = visible ? 'none' : '';
            header.querySelector('.nd-section__arrow').textContent = visible ? '\u25B6' : '\u25BC';
        });

        section.appendChild(header);
        section.appendChild(content);
        return section;
    }

    async _fetchDetail(nodeId) {
        try {
            const res = await fetch(`/api/nodes/${nodeId}`);
            if (!res.ok) return {};
            return await res.json();
        } catch { return {}; }
    }

    async _fetchTelemetry(nodeId) {
        try {
            const res = await fetch(`/api/telemetry/${nodeId}`);
            if (!res.ok) return [];
            const data = await res.json();
            return Array.isArray(data) ? data : data.history || [];
        } catch { return []; }
    }

    _signalQuality(rssi) {
        if (rssi > -80) return { label: 'Excellent', cls: 'excellent' };
        if (rssi > -95) return { label: 'Good', cls: 'good' };
        if (rssi > -110) return { label: 'Fair', cls: 'fair' };
        return { label: 'Poor', cls: 'poor' };
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

    /** @param {number} tempC stored Meshtastic environment temperature (Celsius). */
    _dewPointCelsius(tempC, humidity) {
        const a = 17.27;
        const b = 237.7;
        const alpha = (a * tempC) / (b + tempC) + Math.log(humidity / 100);
        return (b * alpha) / (a - alpha);
    }

    _formatDate(ts) {
        if (!ts) return '--';
        const d = new Date(ts);
        return d.toLocaleString([], {
            month: 'short', day: 'numeric',
            hour: '2-digit', minute: '2-digit',
        });
    }

    _formatUptime(seconds) {
        const d = Math.floor(seconds / 86400);
        const h = Math.floor((seconds % 86400) / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        if (d > 0) return `${d}d ${h}h`;
        if (h > 0) return `${h}h ${m}m`;
        return `${m}m`;
    }

    _hashColor(str) {
        let hash = 0;
        for (let i = 0; i < str.length; i++) {
            hash = str.charCodeAt(i) + ((hash << 5) - hash);
        }
        return `hsl(${Math.abs(hash) % 360}, 55%, 45%)`;
    }

    _esc(str) {
        const el = document.createElement('span');
        el.textContent = str || '';
        return el.innerHTML;
    }
}
