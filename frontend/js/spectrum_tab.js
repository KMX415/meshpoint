/**
 * Spectrum tab — canvas waterfall display driven by spectral_row WebSocket events.
 *
 * Frequency runs on the X axis. Time scrolls down (newest row at bottom).
 * RSSI is mapped to a heat colormap: dark blue (weak) → cyan → yellow → red (strong).
 *
 * Usage (called from app.js):
 *   window.spectrumTab = new SpectrumTab('spectrum-panel');
 *   // then in _setupTabs: if (tabId === 'spectrum') spectrumTab.onActivated();
 *   // and: concentratorWS.on('spectral_row', d => spectrumTab.onRow(d));
 */
class SpectrumTab {
    constructor(containerId) {
        this._container = document.getElementById(containerId);
        this._canvas = null;
        this._ctx = null;
        this._running = false;
        this._available = null;   // null = not yet checked
        this._freqStart = 0;
        this._freqStop = 0;
        this._freqStep = 0;
        this._cols = 0;           // number of frequency bins
        this._colMap = {};        // freq_hz → canvas X column
        this._rowHeight = 2;      // pixels per time row
        this._rssiMin = -130;
        this._rssiMax = -50;
        this._initialized = false;
        this._pendingRows = [];   // buffer rows before canvas is ready
        this._render();
    }

    // ── Public API ────────────────────────────────────────────────────

    onActivated() {
        this._checkAvailability();
    }

    /** Called by app.js for every 'spectral_row' WS event. */
    onRow(data) {
        if (!data || data.freq_hz == null || data.rssi_dbm == null) return;

        if (!this._initialized) {
            this._pendingRows.push(data);
            return;
        }

        this._drawRow(data.freq_hz, data.rssi_dbm);
        this._maybeUpdateStatus(true);
    }

    // ── Internal ──────────────────────────────────────────────────────

    _render() {
        if (!this._container) return;
        this._container.innerHTML = `
            <div class="spectrum">
                <div class="spectrum__controls">
                    <span class="spectrum__label">Start</span>
                    <input class="spectrum__input" id="sp-freq-start" type="number" value="902000000" step="100000">
                    <span class="spectrum__sep">Hz</span>
                    <span class="spectrum__label">Stop</span>
                    <input class="spectrum__input" id="sp-freq-stop" type="number" value="928000000" step="100000">
                    <span class="spectrum__sep">Hz</span>
                    <span class="spectrum__label">Step</span>
                    <input class="spectrum__input" id="sp-freq-step" type="number" value="200000" step="100000" style="width:80px">
                    <span class="spectrum__sep">Hz</span>
                    <span class="spectrum__label">Samples</span>
                    <input class="spectrum__input" id="sp-nb-scan" type="number" value="2000" step="500" style="width:72px">
                    <button class="spectrum__btn" id="sp-start-btn">Start Scan</button>
                    <button class="spectrum__btn spectrum__btn--stop" id="sp-stop-btn" style="display:none">Stop</button>
                    <span class="spectrum__status" id="sp-status">Idle</span>
                </div>

                <div class="spectrum__panel" id="sp-panel">
                    <div class="spectrum__freq-axis" id="sp-freq-axis"></div>
                    <div class="spectrum__canvas-wrap" id="sp-canvas-wrap">
                        <canvas class="spectrum__canvas" id="sp-canvas"></canvas>
                        <div class="spectrum__overlay" id="sp-overlay">
                            <span class="spectrum__idle-msg">Press Start Scan to begin</span>
                            <span class="spectrum__idle-sub">Requires SX1261 companion radio (RAK2287 / SenseCap M1)</span>
                        </div>
                    </div>
                    <div class="spectrum__legend">
                        <span class="spectrum__legend-lo">${this._rssiMin} dBm</span>
                        <div class="spectrum__legend-bar"></div>
                        <span class="spectrum__legend-hi">${this._rssiMax} dBm</span>
                    </div>
                </div>
            </div>
        `;

        document.getElementById('sp-start-btn').addEventListener('click', () => this._startScan());
        document.getElementById('sp-stop-btn').addEventListener('click', () => this._stopScan());
    }

    async _checkAvailability() {
        if (this._available !== null) return;
        try {
            const res = await fetch('/api/spectrum/status');
            const data = await res.json();
            this._available = data.available;
            if (!this._available) {
                this._showUnavailable();
            }
        } catch (_) {
            // Leave available as null; user can still try to start.
        }
    }

    _showUnavailable() {
        const panel = document.getElementById('sp-panel');
        if (!panel) return;
        panel.innerHTML = `
            <div class="spectrum__unavailable">
                <span>Spectral scan not available</span>
                <span class="spectrum__unavailable-sub">libloragw was not found or spectral scan is not supported by this hardware</span>
            </div>
        `;
    }

    async _startScan() {
        const freqStart = parseInt(document.getElementById('sp-freq-start').value);
        const freqStop  = parseInt(document.getElementById('sp-freq-stop').value);
        const freqStep  = parseInt(document.getElementById('sp-freq-step').value);
        const nbScan    = parseInt(document.getElementById('sp-nb-scan').value);

        if (isNaN(freqStart) || isNaN(freqStop) || freqStart >= freqStop) {
            this._setStatus('Invalid frequency range', 'error');
            return;
        }

        try {
            const res = await fetch('/api/spectrum/scan/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    freq_start_hz: freqStart,
                    freq_stop_hz: freqStop,
                    freq_step_hz: freqStep,
                    nb_scan: nbScan,
                }),
            });

            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                this._setStatus(`Error: ${err.detail || res.status}`, 'error');
                return;
            }

            this._initCanvas(freqStart, freqStop, freqStep);
            this._running = true;
            document.getElementById('sp-start-btn').style.display = 'none';
            document.getElementById('sp-stop-btn').style.display = '';
            this._setStatus('Scanning…', 'running');
            this._hideOverlay();
        } catch (e) {
            this._setStatus('Request failed', 'error');
        }
    }

    async _stopScan() {
        try {
            await fetch('/api/spectrum/scan/stop', { method: 'POST' });
        } catch (_) {}
        this._running = false;
        document.getElementById('sp-start-btn').style.display = '';
        document.getElementById('sp-stop-btn').style.display = 'none';
        this._setStatus('Stopped', '');
    }

    _initCanvas(freqStart, freqStop, freqStep) {
        this._freqStart = freqStart;
        this._freqStop  = freqStop;
        this._freqStep  = freqStep;

        const bins = Math.floor((freqStop - freqStart) / freqStep) + 1;
        this._cols = bins;

        // Build freq → column mapping
        this._colMap = {};
        for (let i = 0; i < bins; i++) {
            const f = freqStart + i * freqStep;
            this._colMap[f] = i;
        }

        const wrap = document.getElementById('sp-canvas-wrap');
        const canvas = document.getElementById('sp-canvas');
        if (!canvas || !wrap) return;

        const w = wrap.clientWidth || 800;
        const h = wrap.clientHeight || 400;

        canvas.width  = bins;
        canvas.height = Math.floor(h / this._rowHeight);

        this._canvas = canvas;
        this._ctx    = canvas.getContext('2d');

        // Clear to dark
        this._ctx.fillStyle = '#0a0a1a';
        this._ctx.fillRect(0, 0, canvas.width, canvas.height);

        this._initialized = true;

        // Drain buffered rows
        for (const row of this._pendingRows) {
            this._drawRow(row.freq_hz, row.rssi_dbm);
        }
        this._pendingRows = [];

        this._buildFreqAxis(freqStart, freqStop);
    }

    _buildFreqAxis(freqStart, freqStop) {
        const axis = document.getElementById('sp-freq-axis');
        if (!axis) return;

        const labels = 7;
        const span = freqStop - freqStart;
        let html = '';
        for (let i = 0; i <= labels; i++) {
            const f = freqStart + Math.round((span / labels) * i);
            html += `<span class="spectrum__freq-label">${(f / 1e6).toFixed(2)} MHz</span>`;
        }
        axis.innerHTML = html;
    }

    _drawRow(freq_hz, rssi_dbm) {
        if (!this._ctx || !this._canvas) return;

        const col = this._colMap[freq_hz];
        if (col === undefined) return;

        const ctx    = this._ctx;
        const canvas = this._canvas;

        // Scroll existing content up by rowHeight pixels
        if (col === 0) {
            const img = ctx.getImageData(0, 0, canvas.width, canvas.height);
            ctx.putImageData(img, 0, -this._rowHeight);
            // Clear the new bottom row
            ctx.fillStyle = '#0a0a1a';
            ctx.fillRect(0, canvas.height - this._rowHeight, canvas.width, this._rowHeight);
        }

        const y = canvas.height - this._rowHeight;
        ctx.fillStyle = this._rssiToColor(rssi_dbm);
        ctx.fillRect(col, y, 1, this._rowHeight);
    }

    _rssiToColor(rssi) {
        const t = Math.max(0, Math.min(1,
            (rssi - this._rssiMin) / (this._rssiMax - this._rssiMin)
        ));

        // Heat ramp: dark blue → cyan → yellow → red
        const stops = [
            [0.00, [10,  10,  26]],
            [0.15, [13,  34,  68]],
            [0.30, [10,  82,  128]],
            [0.45, [14,  128, 170]],
            [0.60, [26,  181, 176]],
            [0.72, [78,  205, 196]],
            [0.82, [168, 230, 192]],
            [0.91, [247, 220, 111]],
            [1.00, [231, 76,  60]],
        ];

        for (let i = 1; i < stops.length; i++) {
            if (t <= stops[i][0]) {
                const lo = stops[i - 1];
                const hi = stops[i];
                const frac = (t - lo[0]) / (hi[0] - lo[0]);
                const r = Math.round(lo[1][0] + frac * (hi[1][0] - lo[1][0]));
                const g = Math.round(lo[1][1] + frac * (hi[1][1] - lo[1][1]));
                const b = Math.round(lo[1][2] + frac * (hi[1][2] - lo[1][2]));
                return `rgb(${r},${g},${b})`;
            }
        }
        return 'rgb(231,76,60)';
    }

    _setStatus(msg, type) {
        const el = document.getElementById('sp-status');
        if (!el) return;
        el.textContent = msg;
        el.className = 'spectrum__status'
            + (type === 'running' ? ' spectrum__status--running' : '')
            + (type === 'error'   ? ' spectrum__status--error'   : '');
    }

    _hideOverlay() {
        const overlay = document.getElementById('sp-overlay');
        if (overlay) overlay.style.display = 'none';
    }

    _maybeUpdateStatus(hasData) {
        if (this._running && hasData) {
            this._setStatus('Scanning…', 'running');
        }
    }
}
