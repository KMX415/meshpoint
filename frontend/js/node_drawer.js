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
        this._metricsChart = null;
        this._metricsHours = 24;
        this._adminConfigAvailable = false;
        this._adminDebounceSeconds = 30;
        this._adminPollTimer = null;
        this._adminConfigDebounceUntil = 0;
        this._adminWritePollTimer = null;
        this._dangerousModal = window.DangerousModal
            ? new window.DangerousModal()
            : null;

        if (window.MeshpointNodeFavorites) {
            window.MeshpointNodeFavorites.onChange(() => this._refreshFavoriteButton());
        }
    }

    async open(node) {
        this._currentNode = node;
        this._metricsHours = 24;
        this._renderSkeleton(node);
        this._drawer.classList.add('nd-drawer--open');

        const [detail, metrics, adminStatus] = await Promise.all([
            this._fetchDetail(node.node_id),
            this._fetchMetricsHistory(node.node_id, this._metricsHours),
            this._fetchAdminConfigStatus(),
        ]);
        if (adminStatus) {
            this._adminConfigAvailable = !!adminStatus.available;
            this._adminDebounceSeconds = adminStatus.debounce_seconds || 30;
        }

        const merged = { ...node, ...detail };
        merged._metricsHistory = metrics;
        if (metrics.telemetry && metrics.telemetry.length > 0) {
            merged._telemetryHistory = metrics.telemetry.slice().reverse();
        }
        this._currentNode = merged;
        this._renderFull(merged);
    }

    close() {
        this._stopAdminPoll();
        this._stopAdminWritePoll();
        if (this._metricsChart) {
            this._metricsChart.destroy();
            this._metricsChart = null;
        }
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
        const isFav = !!(window.MeshpointNodeFavorites && window.MeshpointNodeFavorites.has(node.node_id));
        const favClass = isFav ? ' nd-header__favorite--on' : '';
        const favTitle = isFav ? 'Remove favorite' : 'Add favorite';
        const favGlyph = isFav ? '\u2605' : '\u2606';

        this._drawer.innerHTML = `
            <div class="nd-header">
                <div class="nd-header__left">
                    <div class="nd-avatar" style="background:${color}">${shortLabel}</div>
                    <div class="nd-header__info">
                        <div class="nd-header__name">${name}</div>
                        <div class="nd-header__id">!${this._esc(node.node_id)}</div>
                    </div>
                </div>
                <button class="nd-header__favorite${favClass}"
                        data-favorite-toggle
                        aria-pressed="${isFav ? 'true' : 'false'}"
                        aria-label="${favTitle}"
                        title="${favTitle}">${favGlyph}</button>
                <button class="nd-close" title="Close">&times;</button>
            </div>
            <div class="nd-body">
                <div class="nd-loading">Loading details...</div>
            </div>
        `;

        this._drawer.querySelector('.nd-close').addEventListener('click', () => this.close());
        const favBtn = this._drawer.querySelector('[data-favorite-toggle]');
        if (favBtn) {
            favBtn.addEventListener('click', () => {
                if (!this._currentNode || !window.MeshpointNodeFavorites) return;
                window.MeshpointNodeFavorites.toggle(this._currentNode.node_id);
            });
        }
    }

    _refreshFavoriteButton() {
        if (!this._currentNode) return;
        const btn = this._drawer.querySelector('[data-favorite-toggle]');
        if (!btn) return;
        const isFav = !!(window.MeshpointNodeFavorites
            && window.MeshpointNodeFavorites.has(this._currentNode.node_id));
        btn.classList.toggle('nd-header__favorite--on', isFav);
        btn.setAttribute('aria-pressed', isFav ? 'true' : 'false');
        const title = isFav ? 'Remove favorite' : 'Add favorite';
        btn.setAttribute('aria-label', title);
        btn.setAttribute('title', title);
        btn.innerHTML = isFav ? '\u2605' : '\u2606';
    }

    _renderFull(n) {
        const body = this._drawer.querySelector('.nd-body');
        if (!body) return;

        body.innerHTML = '';
        body.appendChild(this._buildActions(n));
        body.appendChild(this._buildRemoteConfigSection(n));
        body.appendChild(this._buildMetricsChartSection(n));
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

    _buildRemoteConfigSection(n) {
        const section = document.createElement('div');
        section.className = 'nd-section nd-section--remote-config';

        const header = document.createElement('div');
        header.className = 'nd-section__header';
        header.innerHTML = `<span class="nd-section__title">Remote Configuration</span>
            <span class="nd-section__arrow">\u25BC</span>`;

        const content = document.createElement('div');
        content.className = 'nd-section__content nd-remote-config';

        if (!this._adminConfigAvailable) {
            content.innerHTML = `<p class="nd-remote-config__hint">Set <code>meshtastic.admin_key_b64</code> in local.yaml to enable ADMIN config read.</p>`;
        } else {
            const toolbar = document.createElement('div');
            toolbar.className = 'nd-remote-config__toolbar';

            const select = document.createElement('select');
            select.className = 'nd-remote-config__select';
            select.setAttribute('aria-label', 'Config section');
            [
                ['device', 'Device'],
                ['owner', 'Owner'],
                ['lora', 'LoRa'],
                ['position', 'Position'],
            ].forEach(([value, label]) => {
                const opt = document.createElement('option');
                opt.value = value;
                opt.textContent = label;
                select.appendChild(opt);
            });
            toolbar.appendChild(select);

            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'nd-action-btn nd-remote-config__btn';
            btn.textContent = 'Request Config';
            btn.addEventListener('click', () => {
                this._requestRemoteConfig(n.node_id, select.value, btn, statusEl, resultEl);
            });
            toolbar.appendChild(btn);
            content.appendChild(toolbar);

            const statusEl = document.createElement('p');
            statusEl.className = 'nd-remote-config__status';
            statusEl.textContent = 'No request yet.';
            content.appendChild(statusEl);

            const resultEl = document.createElement('div');
            resultEl.className = 'nd-remote-config__result';
            content.appendChild(resultEl);

            this._refreshRemoteConfigPanel(n.node_id, btn, statusEl, resultEl);
            content.appendChild(this._buildRemoteConfigWriteForm(n));
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

    async _requestRemoteConfig(nodeId, section, btn, statusEl, resultEl) {
        const now = Date.now();
        if (now < this._adminConfigDebounceUntil) {
            const left = Math.ceil((this._adminConfigDebounceUntil - now) / 1000);
            statusEl.textContent = `Wait ${left}s before another request.`;
            return;
        }

        btn.disabled = true;
        statusEl.textContent = 'Sending ADMIN request…';
        resultEl.innerHTML = '';

        try {
            const res = await fetch(
                `/api/admin/nodes/${encodeURIComponent(nodeId)}/config/request`,
                {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ section }),
                },
            );
            const body = await res.json().catch(() => ({}));
            if (!res.ok) {
                statusEl.textContent = body.detail || `Request failed (${res.status})`;
                if (res.status === 429) {
                    this._adminConfigDebounceUntil = Date.now() + this._adminDebounceSeconds * 1000;
                }
                return;
            }
            this._adminConfigDebounceUntil = Date.now() + this._adminDebounceSeconds * 1000;
            statusEl.textContent = 'Waiting for response (up to 30s)…';
            this._startAdminPoll(nodeId, btn, statusEl, resultEl);
        } catch (err) {
            statusEl.textContent = 'Network error requesting config.';
        } finally {
            btn.disabled = Date.now() < this._adminConfigDebounceUntil;
        }
    }

    _startAdminPoll(nodeId, btn, statusEl, resultEl) {
        this._stopAdminPoll();
        const started = Date.now();
        const poll = async () => {
            const data = await this._fetchRemoteConfigStatus(nodeId);
            if (!data) return;

            if (data.status === 'pending') {
                const elapsed = Math.floor((Date.now() - started) / 1000);
                statusEl.textContent = `Waiting for response… ${elapsed}s`;
                return;
            }

            this._stopAdminPoll();
            btn.disabled = Date.now() < this._adminConfigDebounceUntil;

            if (data.status === 'complete') {
                statusEl.textContent = `Received ${data.section || ''} config.`;
                resultEl.innerHTML = this._formatRemoteConfigResult(data.config);
            } else if (data.status === 'timeout') {
                statusEl.innerHTML = 'No response within 30s. '
                    + '<button type="button" class="nd-remote-config__retry">Retry</button>';
                const retry = statusEl.querySelector('.nd-remote-config__retry');
                if (retry) {
                    retry.addEventListener('click', () => {
                        const select = this._drawer.querySelector('.nd-remote-config__select');
                        const section = select ? select.value : 'device';
                        this._requestRemoteConfig(nodeId, section, btn, statusEl, resultEl);
                    });
                }
            } else {
                statusEl.textContent = data.error || `Status: ${data.status}`;
            }
        };
        this._adminPollTimer = setInterval(poll, 2000);
        poll();
    }

    _stopAdminPoll() {
        if (this._adminPollTimer) {
            clearInterval(this._adminPollTimer);
            this._adminPollTimer = null;
        }
    }

    async _refreshRemoteConfigPanel(nodeId, btn, statusEl, resultEl) {
        const data = await this._fetchRemoteConfigStatus(nodeId);
        if (!data || data.status === 'idle') return;
        if (data.status === 'pending') {
            statusEl.textContent = 'Request in progress…';
            this._startAdminPoll(nodeId, btn, statusEl, resultEl);
            return;
        }
        if (data.status === 'complete' && data.config) {
            statusEl.textContent = `Last read: ${data.section || ''}`;
            resultEl.innerHTML = this._formatRemoteConfigResult(data.config);
        } else if (data.error) {
            statusEl.textContent = data.error;
        }
    }

    _formatRemoteConfigResult(config) {
        if (!config) return '';
        const rows = this._flattenConfigRows(config, '');
        if (rows.length === 0) {
            return '<p class="nd-remote-config__hint">Empty response.</p>';
        }
        return rows.map(([k, v]) => (
            `<div class="nd-row"><span class="nd-row__label">${this._esc(k)}</span>`
            + `<span class="nd-row__value">${this._esc(String(v))}</span></div>`
        )).join('');
    }

    _flattenConfigRows(obj, prefix) {
        const rows = [];
        if (obj == null || typeof obj !== 'object') {
            return rows;
        }
        Object.entries(obj).forEach(([key, value]) => {
            const path = prefix ? `${prefix}.${key}` : key;
            if (value != null && typeof value === 'object' && !Array.isArray(value)) {
                rows.push(...this._flattenConfigRows(value, path));
            } else if (Array.isArray(value)) {
                rows.push([path, value.join(', ')]);
            } else if (value !== '' && value != null) {
                rows.push([path, value]);
            }
        });
        return rows;
    }

    async _fetchAdminConfigStatus() {
        try {
            const res = await fetch('/api/admin/remote-config/status', { credentials: 'same-origin' });
            if (!res.ok) return null;
            return await res.json();
        } catch {
            return null;
        }
    }

    _buildRemoteConfigWriteForm(n) {
        const form = document.createElement('div');
        form.className = 'nd-remote-config__write';

        const title = document.createElement('p');
        title.className = 'nd-remote-config__write-title';
        title.textContent = 'Apply changes (limited fields)';
        form.appendChild(title);

        const fields = [
            { key: 'long_name', label: 'Long name', type: 'text', max: 40 },
            { key: 'short_name', label: 'Short name', type: 'text', max: 4 },
            {
                key: 'role',
                label: 'Device role',
                type: 'select',
                options: [
                    ['', '— leave unchanged —'],
                    ['0', 'CLIENT'],
                    ['2', 'ROUTER'],
                    ['3', 'ROUTER_CLIENT'],
                    ['4', 'REPEATER'],
                    ['5', 'TRACKER'],
                    ['6', 'SENSOR'],
                ],
            },
            { key: 'screen_on_secs', label: 'Screen timeout (s)', type: 'number', min: 0, max: 600 },
            { key: 'telemetry_interval_secs', label: 'Telemetry interval (s)', type: 'number', min: 30, max: 86400 },
        ];

        const inputs = {};
        fields.forEach((field) => {
            const row = document.createElement('label');
            row.className = 'nd-remote-config__field';
            row.textContent = field.label;
            let input;
            if (field.type === 'select') {
                input = document.createElement('select');
                field.options.forEach(([value, label]) => {
                    const opt = document.createElement('option');
                    opt.value = value;
                    opt.textContent = label;
                    input.appendChild(opt);
                });
            } else {
                input = document.createElement('input');
                input.type = field.type;
                if (field.max != null) input.maxLength = field.max;
                if (field.min != null) input.min = String(field.min);
                if (field.max != null && field.type === 'number') input.max = String(field.max);
                input.placeholder = 'unchanged';
            }
            input.className = 'nd-remote-config__input';
            input.dataset.writeKey = field.key;
            row.appendChild(input);
            form.appendChild(row);
            inputs[field.key] = input;
        });

        const writeStatus = document.createElement('p');
        writeStatus.className = 'nd-remote-config__status';
        form.appendChild(writeStatus);

        const writeBtn = document.createElement('button');
        writeBtn.type = 'button';
        writeBtn.className = 'nd-action-btn nd-action-btn--primary nd-remote-config__write-btn';
        writeBtn.textContent = 'Apply Changes';
        writeBtn.addEventListener('click', () => {
            this._submitRemoteConfigWrite(n.node_id, inputs, writeBtn, writeStatus);
        });
        form.appendChild(writeBtn);

        this._refreshRemoteWritePanel(n.node_id, writeStatus);
        return form;
    }

    async _submitRemoteConfigWrite(nodeId, inputs, btn, statusEl) {
        const payload = {};
        Object.entries(inputs).forEach(([key, el]) => {
            const raw = (el.value || '').trim();
            if (!raw) return;
            if (key === 'role') payload.role = parseInt(raw, 10);
            else if (key === 'screen_on_secs' || key === 'telemetry_interval_secs') {
                payload[key] = parseInt(raw, 10);
            } else {
                payload[key] = raw;
            }
        });

        if (Object.keys(payload).length === 0) {
            statusEl.textContent = 'Enter at least one field to change.';
            return;
        }

        if (payload.role != null) {
            if (!this._dangerousModal) {
                statusEl.textContent = 'Confirmation modal unavailable.';
                return;
            }
            const roleLabel = inputs.role.selectedOptions[0]?.textContent || payload.role;
            const ok = await this._dangerousModal.confirm({
                label: 'Change device role',
                description: `This sends an ADMIN write to change role to ${roleLabel}. Mesh behavior may change immediately.`,
                typedPhrase: 'CONFIRM',
            });
            if (!ok) {
                statusEl.textContent = 'Role change cancelled.';
                return;
            }
            payload.role_confirm = 'CONFIRM';
        }

        btn.disabled = true;
        statusEl.textContent = 'Sending ADMIN write…';

        try {
            const res = await fetch(
                `/api/admin/nodes/${encodeURIComponent(nodeId)}/config/write`,
                {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                },
            );
            const body = await res.json().catch(() => ({}));
            if (!res.ok) {
                statusEl.textContent = body.detail || `Write failed (${res.status})`;
                return;
            }
            statusEl.textContent = 'Write sent — verifying…';
            this._startAdminWritePoll(nodeId, statusEl);
        } catch {
            statusEl.textContent = 'Network error during write.';
        } finally {
            btn.disabled = false;
        }
    }

    _startAdminWritePoll(nodeId, statusEl) {
        this._stopAdminWritePoll();
        const poll = async () => {
            const data = await this._fetchRemoteWriteStatus(nodeId);
            if (!data) return;
            if (data.status === 'verifying' || data.status === 'writing') {
                statusEl.textContent = 'Verifying write (auto read-back)…';
                return;
            }
            this._stopAdminWritePoll();
            if (data.status === 'verified') {
                statusEl.textContent = 'Write verified by follow-up read.';
            } else if (data.status === 'verify_timeout') {
                statusEl.textContent = data.error || 'Verify read timed out.';
            } else if (data.status === 'failed') {
                statusEl.textContent = data.error || 'Write failed.';
            }
        };
        this._adminWritePollTimer = setInterval(poll, 2000);
        poll();
    }

    _stopAdminWritePoll() {
        if (this._adminWritePollTimer) {
            clearInterval(this._adminWritePollTimer);
            this._adminWritePollTimer = null;
        }
    }

    async _refreshRemoteWritePanel(nodeId, statusEl) {
        const data = await this._fetchRemoteWriteStatus(nodeId);
        if (!data || data.status === 'idle') return;
        if (data.status === 'verifying' || data.status === 'writing') {
            statusEl.textContent = 'Write in progress…';
            this._startAdminWritePoll(nodeId, statusEl);
            return;
        }
        if (data.status === 'verified') {
            statusEl.textContent = 'Last write verified.';
        } else if (data.error) {
            statusEl.textContent = data.error;
        }
    }

    async _fetchRemoteWriteStatus(nodeId) {
        try {
            const res = await fetch(
                `/api/admin/nodes/${encodeURIComponent(nodeId)}/config/write`,
                { credentials: 'same-origin' },
            );
            if (!res.ok) return null;
            return await res.json();
        } catch {
            return null;
        }
    }

    async _fetchRemoteConfigStatus(nodeId) {
        try {
            const res = await fetch(
                `/api/admin/nodes/${encodeURIComponent(nodeId)}/config`,
                { credentials: 'same-origin' },
            );
            if (!res.ok) return null;
            return await res.json();
        } catch {
            return null;
        }
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

    _buildMetricsChartSection(n) {
        const section = document.createElement('div');
        section.className = 'nd-section nd-section--chart';

        const header = document.createElement('div');
        header.className = 'nd-section__header';
        header.innerHTML = `<span class="nd-section__title">Metrics over time</span>
            <span class="nd-section__arrow">\u25BC</span>`;

        const content = document.createElement('div');
        content.className = 'nd-section__content nd-metrics';

        const range = document.createElement('div');
        range.className = 'nd-metrics__range';
        range.setAttribute('role', 'group');
        range.setAttribute('aria-label', 'Time range');
        const ranges = [
            { h: 1, label: '1H' },
            { h: 6, label: '6H' },
            { h: 24, label: '24H' },
            { h: null, label: 'All' },
        ];
        ranges.forEach(({ h, label }) => {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'nd-metrics__range-btn';
            btn.textContent = label;
            if (h === this._metricsHours) btn.classList.add('nd-metrics__range-btn--active');
            if (h === null && this._metricsHours === null) {
                btn.classList.add('nd-metrics__range-btn--active');
            }
            btn.addEventListener('click', () => this._onMetricsRangeChange(n.node_id, h, range));
            range.appendChild(btn);
        });
        content.appendChild(range);

        const wrap = document.createElement('div');
        wrap.className = 'nd-metrics__chart-wrap';
        const canvas = document.createElement('canvas');
        canvas.className = 'nd-metrics__canvas';
        canvas.setAttribute('role', 'img');
        canvas.setAttribute('aria-label', 'Node metrics chart');
        wrap.appendChild(canvas);
        content.appendChild(wrap);

        const hint = document.createElement('p');
        hint.className = 'nd-metrics__hint';
        hint.textContent =
            'Built from telemetry packets and per-packet RSSI. Click legend labels to show or hide lines (RSSI is off by default when there are many points).';
        content.appendChild(hint);

        const empty = document.createElement('div');
        empty.className = 'nd-metrics__empty';
        empty.style.display = 'none';
        empty.textContent = 'Not enough history yet. Values appear as telemetry packets arrive.';
        content.appendChild(empty);

        if (window.NodeMetricsChart) {
            this._metricsChart = new NodeMetricsChart(canvas);
            const ok = this._metricsChart.render(n._metricsHistory);
            if (!ok) {
                wrap.style.display = 'none';
                empty.style.display = 'block';
            }
        } else {
            wrap.style.display = 'none';
            empty.style.display = 'block';
            empty.textContent = 'Chart library not loaded.';
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

    async _onMetricsRangeChange(nodeId, hours, rangeEl) {
        this._metricsHours = hours;
        rangeEl.querySelectorAll('.nd-metrics__range-btn').forEach((btn) => {
            btn.classList.remove('nd-metrics__range-btn--active');
        });
        const labels = { 1: '1H', 6: '6H', 24: '24H' };
        const activeLabel = hours == null ? 'All' : labels[hours];
        rangeEl.querySelectorAll('.nd-metrics__range-btn').forEach((btn) => {
            if (btn.textContent === activeLabel) {
                btn.classList.add('nd-metrics__range-btn--active');
            }
        });

        const metrics = await this._fetchMetricsHistory(nodeId, hours);
        if (this._currentNode) {
            this._currentNode._metricsHistory = metrics;
            this._currentNode._telemetryHistory = (metrics.telemetry || []).slice().reverse();
        }
        if (this._metricsChart) {
            const wrap = this._drawer.querySelector('.nd-metrics__chart-wrap');
            const empty = this._drawer.querySelector('.nd-metrics__empty');
            const ok = this._metricsChart.render(metrics);
            if (wrap && empty) {
                wrap.style.display = ok ? '' : 'none';
                empty.style.display = ok ? 'none' : 'block';
            }
        }
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

    async _fetchMetricsHistory(nodeId, hours) {
        try {
            let url = `/api/nodes/${encodeURIComponent(nodeId)}/metrics_history?limit=500`;
            if (hours != null) url += `&hours=${hours}`;
            const res = await fetch(url);
            if (!res.ok) return { telemetry: [], signal: [] };
            return await res.json();
        } catch {
            return { telemetry: [], signal: [] };
        }
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
