/**
 * Unknown RF tab — undecodable frames from GET /api/stray_frames.
 */
class UnknownRfTab {
    constructor(containerId) {
        this._container = document.getElementById(containerId);
        this._rendered = false;
        this._hours = 24;
        this._minRssi = '';
        this._refreshInterval = null;
        this._statusStrip = null;
        this._fetchedAt = null;
    }

    async refresh() {
        if (!this._container) return;

        try {
            if (!this._rendered) {
                this._buildLayout();
                this._rendered = true;
            }
            const params = new URLSearchParams({
                limit: '500',
                hours: String(this._hours),
            });
            if (this._minRssi !== '' && !Number.isNaN(Number(this._minRssi))) {
                params.set('min_rssi', this._minRssi);
            }
            const res = await fetch(`/api/stray_frames?${params}`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            this._fetchedAt = Date.now();
            this._renderTable(data);
        } catch (e) {
            console.error('Unknown RF refresh failed:', e);
        }

        if (!this._refreshInterval) {
            this._refreshInterval = setInterval(() => {
                const section = document.querySelector('[data-section="unknown-rf"]');
                if (section && section.classList.contains('section--active')) {
                    this.refresh();
                } else {
                    clearInterval(this._refreshInterval);
                    this._refreshInterval = null;
                }
            }, 15_000);
        }
    }

    _buildLayout() {
        this._container.innerHTML = `
            <div class="unknown-rf-panel">
                <header class="unknown-rf-panel__header">
                    <div>
                        <h2 class="unknown-rf-panel__title">Unknown RF</h2>
                        <p class="unknown-rf-panel__desc">
                            Frames that failed both Meshtastic and MeshCore decode. RF metadata only:
                            no payload stored, no relay, no re-encode.
                        </p>
                    </div>
                </header>
                <div class="unknown-rf-controls">
                    <div class="unknown-rf-field">
                        <label for="urf-hours">Window (hours)</label>
                        <select id="urf-hours">
                            <option value="1">1h</option>
                            <option value="6">6h</option>
                            <option value="24" selected>24h</option>
                            <option value="168">7d</option>
                        </select>
                    </div>
                    <div class="unknown-rf-field">
                        <label for="urf-min-rssi">Min RSSI (dBm)</label>
                        <input id="urf-min-rssi" type="number" min="-150" max="0" step="1" placeholder="any">
                    </div>
                    <button type="button" class="unknown-rf-btn" id="urf-apply">Apply filters</button>
                    <a class="unknown-rf-btn" id="urf-csv" href="#">Export CSV</a>
                </div>
                <p class="unknown-rf-meta" id="urf-meta"></p>
                <div class="unknown-rf-table-wrap">
                    <table class="unknown-rf-table">
                        <thead>
                            <tr>
                                <th>Time</th>
                                <th>Size</th>
                                <th>Ch</th>
                                <th>Freq</th>
                                <th>SF</th>
                                <th>BW</th>
                                <th>RSSI</th>
                                <th>SNR</th>
                                <th>Source</th>
                            </tr>
                        </thead>
                        <tbody id="urf-tbody"></tbody>
                    </table>
                    <div id="urf-empty" class="unknown-rf-empty" hidden>No stray frames in this window.</div>
                </div>
                <div id="urf-status-strip-host"></div>
            </div>
        `;

        const stripHost = document.getElementById('urf-status-strip-host');
        if (stripHost && window.StatusStrip) {
            this._statusStrip = new window.StatusStrip(stripHost, 'UNKNOWN RF');
            this._statusStrip.mount();
        }

        document.getElementById('urf-hours').addEventListener('change', (e) => {
            this._hours = Number(e.target.value);
        });
        document.getElementById('urf-apply').addEventListener('click', () => {
            this._minRssi = document.getElementById('urf-min-rssi').value.trim();
            this.refresh();
        });
        document.getElementById('urf-csv').addEventListener('click', (e) => {
            e.preventDefault();
            const params = new URLSearchParams({
                format: 'csv',
                limit: '2000',
                hours: String(this._hours),
            });
            if (this._minRssi !== '' && !Number.isNaN(Number(this._minRssi))) {
                params.set('min_rssi', this._minRssi);
            }
            window.location.assign(`/api/stray_frames?${params}`);
        });
    }

    _renderTable(data) {
        const tbody = document.getElementById('urf-tbody');
        const meta = document.getElementById('urf-meta');
        const empty = document.getElementById('urf-empty');
        if (!tbody) return;

        const frames = data.frames || [];
        const totalStored = data.total_stored ?? frames.length;
        const windowH = data.window_hours ?? this._hours;
        meta.textContent =
            `Showing ${frames.length} of ${totalStored} stored (last ${windowH}h)`;

        const sfSet = new Set(frames.map((f) => f.spreading_factor).filter((v) => v != null));
        this._statusStrip?.update(
            [
                `${frames.length} shown`,
                `${totalStored} stored`,
                `${windowH}h window`,
                `${sfSet.size} SF buckets`,
            ],
            this._fetchedAt,
        );

        if (!frames.length) {
            tbody.innerHTML = '';
            if (empty) empty.hidden = false;
            return;
        }
        if (empty) empty.hidden = true;

        tbody.innerHTML = frames.map((f) => {
            const ts = this._formatTime(f.timestamp);
            return `<tr>
                <td>${ts}</td>
                <td>${f.frame_size ?? '--'} B</td>
                <td>${f.channel_hash != null ? f.channel_hash : '--'}</td>
                <td>${f.frequency_mhz != null ? `${Number(f.frequency_mhz).toFixed(3)} MHz` : '--'}</td>
                <td>${f.spreading_factor ?? '--'}</td>
                <td>${f.bandwidth_khz != null ? `${f.bandwidth_khz} kHz` : '--'}</td>
                <td>${f.rssi != null ? `${Number(f.rssi).toFixed(0)}` : '--'}</td>
                <td>${f.snr != null ? `${Number(f.snr).toFixed(1)}` : '--'}</td>
                <td>${this._esc(f.capture_source || '--')}</td>
            </tr>`;
        }).join('');
    }

    _formatTime(ts) {
        if (!ts) return '--';
        try {
            const d = new Date(ts);
            return d.toLocaleString();
        } catch (_e) {
            return ts;
        }
    }

    _esc(str) {
        const el = document.createElement('span');
        el.textContent = str;
        return el.innerHTML;
    }
}

window.unknownRfTab = new UnknownRfTab('unknown-rf-panel');
