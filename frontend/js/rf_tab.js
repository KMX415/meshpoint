/**
 * RF Environment tab — noise-floor sparkline + spectral histogram.
 * Reads GET /api/rf/status; live sparkline also accepts WS noise_floor.
 */
class RfTab {
    constructor(containerId) {
        this._containerId = containerId;
        this._container = null;
        this._rendered = false;
        this._refreshInterval = null;
        this._histogramChart = null;
        this._sparkline = null;
        this._wsBound = false;
        this._statusStrip = null;
        this._fetchedAt = null;
    }

    _mount() {
        if (!this._container) {
            this._container = document.getElementById(this._containerId);
        }
        return this._container;
    }

    async refresh() {
        const container = this._mount();
        if (!container) {
            console.error('RF panel mount #%s not found', this._containerId);
            return;
        }

        this._ensureShell();

        try {
            const res = await fetch('/api/rf/status', { credentials: 'same-origin' });
            if (!res.ok) {
                throw new Error(`HTTP ${res.status}`);
            }
            const data = await res.json();
            this._fetchedAt = Date.now();
            this._clearFetchError();
            this._update(data);
        } catch (e) {
            console.error('RF status refresh failed:', e);
            this._showFetchError(e);
        }

        if (!this._refreshInterval) {
            this._refreshInterval = setInterval(() => {
                const section = document.querySelector('[data-section="rf"]');
                if (section && section.classList.contains('section--active')) {
                    this.refresh();
                } else {
                    clearInterval(this._refreshInterval);
                    this._refreshInterval = null;
                }
            }, 5000);
        }
    }

    _ensureShell() {
        if (this._rendered) return;
        this._buildLayout();
        this._rendered = true;
        this._bindWebSocket();
    }

    _showFetchError(err) {
        const host = document.getElementById('rf-fetch-error');
        if (!host) return;
        const detail = err && err.message ? err.message : 'request failed';
        host.hidden = false;
        host.textContent = (
            `Could not load RF status (${detail}). `
            + 'If you just updated, restart meshpoint so the API is available, then try again.'
        );
    }

    _clearFetchError() {
        const host = document.getElementById('rf-fetch-error');
        if (host) host.hidden = true;
    }

    _buildLayout() {
        const container = this._mount();
        if (!container) return;
        container.innerHTML = `
            <div class="rf-panel">
                <header class="rf-panel__header">
                    <h2 class="rf-panel__title">RF Environment</h2>
                    <p class="rf-panel__desc">
                        Local noise-floor readout and the latest SX1302 spectral-scan histogram.
                        Values marked <span class="rf-badge rf-badge--live">Live scan</span> come from hardware;
                        <span class="rf-badge rf-badge--fallback">Packet fallback</span> is an upper bound from decoded packets.
                    </p>
                    <p id="rf-fetch-error" class="rf-panel__error" hidden role="alert"></p>
                </header>
                <div class="rf-grid">
                    <article class="rf-card">
                        <h3 class="rf-card__title">Noise floor</h3>
                        <p class="rf-card__hint" id="rf-noise-hint">Loading…</p>
                        <div class="rf-readout">
                            <span class="rf-readout__value" id="rf-noise-value">--</span>
                            <span class="rf-readout__unit">dBm</span>
                            <span id="rf-noise-badge" class="rf-badge rf-badge--calibrating">…</span>
                        </div>
                        <div class="rf-sparkline-wrap">
                            <canvas id="rf-noise-sparkline" aria-label="Noise floor history"></canvas>
                        </div>
                        <dl class="rf-meta" id="rf-noise-meta"></dl>
                    </article>
                    <article class="rf-card">
                        <h3 class="rf-card__title">Spectral scan</h3>
                        <p class="rf-card__hint" id="rf-scan-hint">Loading…</p>
                        <dl class="rf-meta" id="rf-scan-meta"></dl>
                        <div class="rf-scan-stats" id="rf-scan-stats"></div>
                    </article>
                    <article class="rf-card rf-card--wide">
                        <h3 class="rf-card__title">Channel histogram</h3>
                        <p class="rf-card__hint">Latest hardware scan — RSSI level distribution across the tuned channel.</p>
                        <div class="rf-histogram-wrap">
                            <canvas id="rf-histogram" aria-label="Spectral scan histogram"></canvas>
                            <div id="rf-histogram-empty" class="rf-histogram-empty" hidden>
                                No hardware scan yet. Enable spectral scan under Configuration → Advanced
                                or wait for the first scheduled scan.
                            </div>
                        </div>
                    </article>
                </div>
                <div id="rf-status-strip-host"></div>
            </div>
        `;

        const stripHost = document.getElementById('rf-status-strip-host');
        if (stripHost && window.StatusStrip) {
            this._statusStrip = new window.StatusStrip(stripHost, 'RF ENV');
            this._statusStrip.mount();
        }

        const canvas = document.getElementById('rf-noise-sparkline');
        if (canvas && window.NoiseFloorSparkline) {
            this._sparkline = new window.NoiseFloorSparkline(canvas);
        }
    }

    _bindWebSocket() {
        if (this._wsBound || !window.concentratorWS) return;
        this._wsBound = true;
        window.concentratorWS.on('noise_floor', (frame) => {
            const section = document.querySelector('[data-section="rf"]');
            if (!section || !section.classList.contains('section--active')) return;
            this._updateNoiseFloor(frame);
        });
    }

    _update(data) {
        this._updateNoiseFloor(data.noise_floor || {});
        this._updateSpectralScan(data.spectral_scan || {});
        this._updateStatusStrip(data.noise_floor || {}, data.spectral_scan || {});
    }

    _updateStatusStrip(nf, scan) {
        if (!this._statusStrip) return;
        const source = nf.source === 'spectral_scan' ? 'live scan' : 'packet fallback';
        const noise = nf.value_dbm != null ? `${Number(nf.value_dbm).toFixed(1)} dBm` : 'calibrating';
        const samples = nf.samples_count ?? 0;
        const scanState = scan.running ? 'scan on' : 'scan off';
        const scans = scan.scans_run != null ? `${scan.scans_run} scans` : 'no scans';
        this._statusStrip.update(
            [noise, source, `${samples} samples`, scanState, scans],
            this._fetchedAt,
        );
    }

    _updateNoiseFloor(nf) {
        const valueEl = document.getElementById('rf-noise-value');
        const badgeEl = document.getElementById('rf-noise-badge');
        const hintEl = document.getElementById('rf-noise-hint');
        const metaEl = document.getElementById('rf-noise-meta');
        if (!valueEl || !badgeEl) return;

        const source = nf.source || 'packets';
        const calibrating = !!nf.calibrating;
        const stale = !!nf.stale;
        const value = nf.value_dbm;

        if (calibrating || value == null) {
            valueEl.textContent = '--';
        } else {
            valueEl.textContent = Number(value).toFixed(1);
        }

        badgeEl.className = 'rf-badge';
        if (calibrating) {
            badgeEl.classList.add('rf-badge--calibrating');
            badgeEl.textContent = 'Calibrating';
        } else if (source === 'spectral_scan') {
            badgeEl.classList.add('rf-badge--live');
            badgeEl.textContent = stale ? 'Live scan (stale)' : 'Live scan';
        } else {
            badgeEl.classList.add('rf-badge--fallback');
            badgeEl.textContent = stale ? 'Packet fallback (stale)' : 'Packet fallback';
        }

        if (hintEl) {
            hintEl.textContent = RfTab._noiseHint(nf);
        }

        if (metaEl) {
            const bw = nf.bandwidth_khz != null ? `${nf.bandwidth_khz} kHz` : '--';
            const theory = nf.theoretical_floor_dbm != null
                ? `${Number(nf.theoretical_floor_dbm).toFixed(1)} dBm` : '--';
            const median = nf.median_dbm != null
                ? `${Number(nf.median_dbm).toFixed(1)} dBm` : '--';
            metaEl.innerHTML = `
                <div><dt>Bandwidth</dt><dd>${bw}</dd></div>
                <div><dt>Theoretical floor</dt><dd>${theory}</dd></div>
                <div><dt>Median (scan)</dt><dd>${median}</dd></div>
                <div><dt>Samples</dt><dd>${nf.samples_count ?? 0}</dd></div>
            `;
        }

        if (this._sparkline) {
            this._sparkline.setSamples(
                nf.samples_dbm || [],
                nf.theoretical_floor_dbm,
            );
        }
    }

    _updateSpectralScan(scan) {
        const hintEl = document.getElementById('rf-scan-hint');
        const metaEl = document.getElementById('rf-scan-meta');
        const statsEl = document.getElementById('rf-scan-stats');
        const emptyEl = document.getElementById('rf-histogram-empty');
        const canvas = document.getElementById('rf-histogram');

        if (hintEl) {
            hintEl.textContent = scan.message || (
                scan.running
                    ? `Scanning every ${scan.interval_seconds || 0}s on the active channel.`
                    : 'Spectral scan service is not running.'
            );
        }

        if (metaEl) {
            const freq = scan.frequency_hz != null
                ? `${(scan.frequency_hz / 1e6).toFixed(3)} MHz` : '--';
            const enabled = scan.enabled ? 'Yes' : 'No';
            const supported = scan.supported ? 'Yes' : 'No';
            const running = scan.running ? 'Yes' : 'No';
            metaEl.innerHTML = `
                <div><dt>Enabled</dt><dd>${enabled}</dd></div>
                <div><dt>Hardware</dt><dd>${supported}</dd></div>
                <div><dt>Running</dt><dd>${running}</dd></div>
                <div><dt>Frequency</dt><dd>${freq}</dd></div>
                <div><dt>Interval</dt><dd>${scan.interval_seconds ?? 0}s</dd></div>
            `;
        }

        if (statsEl) {
            statsEl.innerHTML = `
                <span>Scans completed: <strong>${scan.scans_run ?? 0}</strong></span>
                <span>Failed: <strong>${scan.scans_failed ?? 0}</strong></span>
            `;
        }

        const hist = scan.histogram;
        const hasHist = hist && Array.isArray(hist.levels_dbm) && hist.levels_dbm.length > 0
            && (hist.total_samples > 0 || (hist.counts || []).some((c) => c > 0));

        if (emptyEl) {
            emptyEl.hidden = !!hasHist;
            if (!hasHist) {
                emptyEl.textContent = RfTab._histogramEmptyText(scan);
            }
        }
        if (canvas) canvas.hidden = !hasHist;

        if (!hasHist || typeof Chart === 'undefined') {
            if (this._histogramChart) {
                this._histogramChart.destroy();
                this._histogramChart = null;
            }
            return;
        }

        const labels = hist.levels_dbm.map((lvl) => `${lvl}`);
        const counts = hist.counts || [];

        if (!this._histogramChart) {
            const root = getComputedStyle(document.documentElement);
            const token = (name, fallback) => root.getPropertyValue(name).trim() || fallback;
            const textSecondary = token('--text-secondary', '#94a3b8');
            const textMuted = token('--text-muted', '#64748b');
            this._histogramChart = new Chart(canvas, {
                type: 'bar',
                data: {
                    labels,
                    datasets: [{
                        label: 'Samples',
                        data: counts,
                        backgroundColor: 'rgba(6, 182, 212, 0.55)',
                        borderColor: 'rgba(6, 182, 212, 0.9)',
                        borderWidth: 1,
                    }],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false },
                        title: {
                            display: true,
                            text: `Floor ${hist.floor_dbm ?? '--'} dBm · Median ${hist.median_dbm ?? '--'} dBm`,
                            color: textSecondary,
                            font: { size: 11 },
                        },
                    },
                    scales: {
                        x: {
                            title: { display: true, text: 'RSSI level (dBm)', color: textMuted },
                            ticks: { color: textSecondary, maxTicksLimit: 12 },
                            grid: { color: 'rgba(51, 65, 85, 0.35)' },
                        },
                        y: {
                            title: { display: true, text: 'Sample count', color: textMuted },
                            ticks: { color: textSecondary },
                            grid: { color: 'rgba(51, 65, 85, 0.35)' },
                            beginAtZero: true,
                        },
                    },
                },
            });
            return;
        }

        this._histogramChart.data.labels = labels;
        this._histogramChart.data.datasets[0].data = counts;
        if (this._histogramChart.options.plugins.title) {
            this._histogramChart.options.plugins.title.text =
                `Floor ${hist.floor_dbm ?? '--'} dBm · Median ${hist.median_dbm ?? '--'} dBm`;
        }
        this._histogramChart.update('none');
    }

    static _noiseHint(nf) {
        if (nf.calibrating) {
            return 'Waiting for the first spectral scan or a few packets before reporting a number.';
        }
        if (nf.value_dbm == null) {
            return 'No noise floor data yet.';
        }
        if (nf.source === 'spectral_scan') {
            return 'Direct ambient channel power from the SX1302 spectral scan on the tuned frequency.';
        }
        return 'Upper bound from rolling minimum of (RSSI − SNR) on decoded packets. True floor is at or below this value.';
    }

    static _histogramEmptyText(scan) {
        if (scan.fleet_expected_fallback) {
            return (
                'Hardware histogram not available on this carrier. '
                + 'Expected on RAK V2 and SenseCap M1; use the noise-floor card above (packet fallback).'
            );
        }
        if (!scan.enabled) {
            return 'Hardware scan disabled. Set spectral scan interval under Configuration → Advanced.';
        }
        return 'No hardware scan yet. Wait for the first scheduled scan or check Configuration → Advanced.';
    }
}

function _bootRfTab() {
    window.rfTab = new RfTab('rf-panel');
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _bootRfTab);
} else {
    _bootRfTab();
}
