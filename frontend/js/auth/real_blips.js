/**
 * Live blip renderer for the auth-page radar.
 *
 * Single responsibility: poll ``/api/public/recent_rx``, append a
 * dot for every new sample to the radar host, and let the dot fade
 * out on its own via CSS keyframes. The class is deliberately
 * defensive: if the endpoint is rate-limited or unreachable we just
 * skip the cycle -- the radar visual continues to look alive even
 * with no data because the baseline sweep is CSS-only.
 */

class RealBlips {
    constructor(rootSelector = '#radar', { intervalMs = 4000 } = {}) {
        this._root = document.querySelector(rootSelector);
        this._interval = intervalMs;
        this._timer = null;
        this._seen = new Set();
    }

    start() {
        if (!this._root) return;
        this._tick();
        this._timer = window.setInterval(() => this._tick(), this._interval);
    }

    stop() {
        if (this._timer) window.clearInterval(this._timer);
        this._timer = null;
    }

    async _tick() {
        try {
            const response = await fetch('/api/public/recent_rx', {
                cache: 'no-store',
                credentials: 'omit',
            });
            if (!response.ok) return;
            const body = await response.json();
            (body.blips || []).forEach((blip) => this._spawnIfNew(blip));
        } catch (_e) {
            /* no-op: radar keeps sweeping */
        }
    }

    _spawnIfNew(blip) {
        const key = `${blip.timestamp}-${blip.bearing}-${blip.distance}`;
        if (this._seen.has(key)) return;
        this._seen.add(key);
        this._spawnDot(blip);
        if (this._seen.size > 256) {
            this._seen = new Set(Array.from(this._seen).slice(-128));
        }
    }

    _spawnDot(blip) {
        const dot = document.createElement('div');
        dot.className = 'auth-radar__blip auth-radar__blip--' + this._classFromBucket(blip.rssi_bucket);
        const angle = (Number(blip.bearing) || 0) * Math.PI / 180;
        const radiusPercent = 5 + Math.max(0, Math.min(0.95, blip.distance)) * 45;
        const cx = 50 + radiusPercent * Math.sin(angle);
        const cy = 50 - radiusPercent * Math.cos(angle);
        dot.style.left = `${cx}%`;
        dot.style.top = `${cy}%`;
        this._root.appendChild(dot);
        window.setTimeout(() => dot.remove(), 6000);
    }

    _classFromBucket(bucket) {
        if (bucket === 'strong') return 'strong';
        if (bucket === 'medium') return 'medium';
        return 'weak';
    }
}

window.RealBlips = RealBlips;

document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('radar')) {
        new RealBlips('#radar').start();
    }
});
