/**
 * Sidebar telemetry rail.
 *
 * Pinned between the nav and the role/sign-out footer. Always-on
 * status surface so the sidebar reads like a piece of lab equipment
 * with status LEDs, not a passive nav drawer.
 *
 * Three rows:
 *   - Uptime          (slow polled from /api/device/status, 5s)
 *   - Active sessions (same poll, websocket_clients count)
 *   - Noise floor     (live from `noise_floor` WS frame; sparkline
 *                      drawn by NoiseFloorSparkline)
 *
 * Hidden when the sidebar is in icon-only "rail" mode.
 */
class SidebarTelemetryRail {
    constructor(rootEl, dashboardWs) {
        this._root = rootEl;
        this._ws = dashboardWs;
        this._uptimeEl = rootEl.querySelector('#telemetry-uptime');
        this._sessionsEl = rootEl.querySelector('#telemetry-sessions');
        this._noiseEl = rootEl.querySelector('#telemetry-noise-value');
        this._noiseBwEl = rootEl.querySelector('#telemetry-noise-bw');
        this._noiseChip = rootEl.querySelector('.telemetry-rail__noise');
        const canvas = rootEl.querySelector('#telemetry-noise-canvas');
        this._sparkline = canvas ? new NoiseFloorSparkline(canvas) : null;
        this._statusTimer = null;
    }

    init() {
        this._refreshStatus();
        this._statusTimer = setInterval(() => this._refreshStatus(), 5_000);
        if (this._ws) {
            this._ws.on('noise_floor', (data) => this._onNoiseFloor(data));
        }
    }

    destroy() {
        if (this._statusTimer) clearInterval(this._statusTimer);
    }

    async _refreshStatus() {
        try {
            const res = await fetch('/api/device/status', {
                credentials: 'same-origin',
            });
            if (!res.ok) return;
            const data = await res.json();
            this._uptimeEl.textContent = _formatUptime(data.uptime_seconds || 0);
            const sessions = data.websocket_clients;
            if (typeof sessions === 'number') {
                this._sessionsEl.textContent = String(sessions);
            }
        } catch (_e) { /* swallow; next tick will retry */ }
    }

    _onNoiseFloor(data) {
        if (!data) return;
        const value = data.value_dbm;
        const stale = !!data.stale;
        const calibrating = !!data.calibrating;
        const bw = data.bandwidth_khz;
        const samples = Array.isArray(data.samples_dbm) ? data.samples_dbm : [];
        const floor = data.theoretical_floor_dbm;
        const source = data.source;

        if (calibrating || value == null) {
            this._noiseEl.textContent = value == null ? 'calibrating' : `${value.toFixed(0)} dBm`;
        } else {
            this._noiseEl.textContent = `${value.toFixed(0)} dBm`;
        }
        this._noiseEl.title = _buildNoiseTooltip({
            source, value, calibrating, stale, samples_count: data.samples_count,
            theoretical_floor_dbm: floor,
        });

        if (bw) {
            this._noiseBwEl.textContent = `${bw.toFixed(0)} kHz`;
        } else {
            this._noiseBwEl.textContent = '--';
        }

        this._noiseChip.classList.toggle(
            'telemetry-rail__noise--stale', stale,
        );
        this._noiseChip.classList.toggle(
            'telemetry-rail__noise--calibrating', calibrating,
        );

        if (this._sparkline) this._sparkline.setSamples(samples, floor);
    }
}

function _buildNoiseTooltip({ source, value, calibrating, stale, samples_count, theoretical_floor_dbm }) {
    if (calibrating) {
        return (
            'Waiting for the first spectral scan or a few packets '
            + 'before reporting a number.'
        );
    }
    if (value == null) {
        return 'No noise floor data yet.';
    }
    if (source === 'spectral_scan') {
        const margin = (theoretical_floor_dbm != null && value != null)
            ? `${(value - theoretical_floor_dbm).toFixed(1)} dB above theoretical thermal floor`
            : '';
        const fresh = stale ? ' (last scan stale)' : '';
        return (
            `Direct ambient channel power from SX1302 spectral scan${fresh}. `
            + 'Sampled on the same frequency the radio is tuned to. '
            + (margin ? `${margin}.` : '')
        );
    }
    const fresh = stale ? ' (no recent packets)' : '';
    return (
        `Packet-derived upper bound (rolling minimum of rssi - snr)${fresh}. `
        + 'This is a fallback estimate: the true noise floor is at or below this value. '
        + 'Spectral scan was not available on this device.'
    );
}

function _formatUptime(seconds) {
    const s = Math.max(0, Math.floor(seconds));
    const days = Math.floor(s / 86400);
    const hours = Math.floor((s % 86400) / 3600);
    const minutes = Math.floor((s % 3600) / 60);
    if (days > 0) return `${days}d ${hours}h ${minutes}m`;
    if (hours > 0) return `${hours}h ${minutes}m`;
    return `${minutes}m`;
}

window.SidebarTelemetryRail = SidebarTelemetryRail;
