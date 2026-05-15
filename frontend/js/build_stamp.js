/**
 * Build/version stamp pinned to the bottom-right of the viewport.
 *
 * Reads the live firmware version from /api/system (already polled by
 * the dashboard) and renders a muted, non-interactive label that
 * stays out of the way until you look for it. Useful for support
 * triage: "what version are you running?" is always one glance away.
 *
 * Single responsibility: paint the version label and refresh it on
 * a slow cadence (60 s). No hover tooltips, no click handlers — keep
 * the chrome quiet.
 */
class BuildStamp {
    constructor() {
        this._root = null;
        this._labelEl = null;
        this._timer = null;
    }

    mount() {
        if (document.getElementById('build-stamp')) return;
        const root = document.createElement('div');
        root.id = 'build-stamp';
        root.className = 'build-stamp';
        root.setAttribute('role', 'note');
        root.setAttribute('aria-label', 'Application build version');
        root.innerHTML = `
            <span class="build-stamp__app">meshpoint</span>
            <span class="build-stamp__sep">·</span>
            <span class="build-stamp__version" id="build-stamp-version">--</span>
        `;
        document.body.appendChild(root);
        this._root = root;
        this._labelEl = root.querySelector('#build-stamp-version');
        this._refresh();
        this._timer = setInterval(() => this._refresh(), 60_000);
    }

    destroy() {
        if (this._timer) clearInterval(this._timer);
        if (this._root && this._root.parentNode) {
            this._root.parentNode.removeChild(this._root);
        }
    }

    async _refresh() {
        try {
            const res = await fetch('/api/system', { credentials: 'same-origin' });
            if (!res.ok) return;
            const data = await res.json();
            const device = data.device || {};
            const version = device.firmware_version || '--';
            this._labelEl.textContent = `v${version}`;
        } catch (_e) { /* swallow; next tick will retry */ }
    }
}

window.BuildStamp = BuildStamp;
