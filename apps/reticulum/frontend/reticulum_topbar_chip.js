/**
 * Topbar -- Reticulum chip (plugin "topbar" seam).
 *
 * Ported from core's frontend/topbar/topbar_reticulum_chip.js. That one
 * was fed by TopbarController's shared GET /api/config poll for
 * visibility, then self-polled GET /api/reticulum/status for the live
 * bits. A plugin chip has no core-config-driven enabled flag (the plugin
 * being loaded at all means it's on), so this mounts unconditionally and
 * owns its own visibility + polling from /api/reticulum/status alone --
 * same shape as plugins/apps/dapnet/frontend/dapnet_topbar_chip.js.
 *
 * Reuses the shared `.topbar-serial` / `.topbar-reticulum` CSS wholesale
 * (still core, untouched) -- same brand/lamp/call/sep/freq visual
 * language as the built-in chips. Hidden until the service reports it's
 * available (rns/lxmf installed). When RF is configured, the lamp tracks
 * the live RNode interface, independently of the Reticulum service.
 *
 * The "freq" slot shows the RNode frequency when an RNode is connected
 * (matching the Meshtastic/MeshCore/Pager chips); a backbone-only node has
 * no frequency, so it shows the peer count there instead. The hover title
 * always carries the peer count + which interface is up.
 */
class ReticulumTopbarChip {
    constructor() {
        this._group = null;
        this._timer = null;
    }

    mount(rootEl) {
        this._group = rootEl;
        this._group.hidden = true;
    }

    init() {
        this._refresh();
        this._timer = setInterval(() => this._refresh(), 15_000);
    }

    destroy() {
        clearInterval(this._timer);
        this._timer = null;
    }

    async _refresh() {
        let status = { available: true, running: false, failed: true };
        try {
            const res = await fetch('/api/reticulum/status', { credentials: 'same-origin' });
            if (res.ok) status = await res.json();
        } catch (_e) { /* Show unavailable instead of a stale running state. */ }
        this._paint(status);
    }

    _paint(status) {
        // Hide only when the service is genuinely unusable (rns/lxmf not
        // installed). Otherwise show it -- "starting…" while it comes up.
        if (!status || status.available === false) {
            this._group.hidden = true;
            this._group.textContent = '';
            return;
        }
        if (!this._group.querySelector('.topbar-serial')) {
            this._group.textContent = '';
            this._group.appendChild(this._buildBadge());
        }
        this._group.hidden = false;
        this._applyStatus(status);
    }

    _applyStatus(status) {
        const lamp = this._group.querySelector('.topbar-serial__lamp');
        const callEl = this._group.querySelector('.topbar-serial__call');
        const freqEl = this._group.querySelector('.topbar-serial__freq');
        if (!lamp || !callEl || !freqEl) return;
        const r = status.radio || {};
        const radioOnline = r.connected === true;
        const online = status.running && (!r.rf || radioOnline);
        const radioLabel = radioOnline ? 'RNode connected'
            : r.connected === false ? 'RNode offline' : 'RNode status unknown';

        lamp.classList.remove(
            'topbar-serial__lamp--online',
            'topbar-serial__lamp--offline',
        );
        lamp.classList.add(
            online ? 'topbar-serial__lamp--online' : 'topbar-serial__lamp--offline',
        );
        lamp.setAttribute('aria-label', status.running
            ? (r.rf ? `${radioLabel}; Reticulum service running` : 'Reticulum service running')
            : 'Reticulum service unavailable');

        callEl.textContent = status.running
            ? this._shortAddress(status.own_address)
            : (status.failed ? 'unavailable' : 'starting…');
        // "freq" slot: the RNode frequency when an RNode is connected
        // (matches the Meshtastic/MeshCore/Pager chips), otherwise the peer
        // count -- the meaningful number for a backbone-only node.
        const peers = status.peer_count ?? 0;
        const peersLabel = `${peers} peer${peers === 1 ? '' : 's'}`;
        if (!status.running) {
            freqEl.textContent = '--';
        } else if (r.rf && !radioOnline) {
            freqEl.textContent = radioLabel;
        } else if (r.rf && r.frequency_hz) {
            freqEl.textContent = `${(r.frequency_hz / 1e6).toFixed(3)} MHz`;
        } else {
            freqEl.textContent = peersLabel;
        }
        const root = this._group.querySelector('.topbar-reticulum');
        if (root) {
            const via = r.rf ? radioLabel : (r.backbone ? 'TCP backbone configured' : '');
            root.title = `Reticulum${via ? ` · ${via}` : ''} · ${peersLabel} heard`;
        }
    }

    _shortAddress(addr) {
        if (!addr) return '--';
        const hex = String(addr).replace(/[<>]/g, '');
        return hex.length > 8 ? `${hex.slice(0, 8)}…` : hex;
    }

    _buildBadge() {
        const root = document.createElement('a');
        root.className = 'topbar-serial topbar-reticulum';
        root.href = '#/reticulum';
        root.setAttribute('aria-label', 'Reticulum enabled -- go to Reticulum page');
        root.title = 'Reticulum';

        const brand = document.createElement('span');
        brand.className = 'topbar-serial__brand';
        brand.textContent = 'RETICULUM';
        root.appendChild(brand);

        const lamp = document.createElement('span');
        lamp.className = 'topbar-serial__lamp';
        lamp.setAttribute('role', 'status');
        lamp.setAttribute('aria-live', 'polite');
        const dot = document.createElement('span');
        dot.className = 'topbar-serial__dot';
        dot.setAttribute('aria-hidden', 'true');
        lamp.appendChild(dot);
        root.appendChild(lamp);

        const callEl = document.createElement('span');
        callEl.className = 'topbar-serial__call';
        callEl.textContent = 'starting…';
        root.appendChild(callEl);

        const sep = document.createElement('span');
        sep.className = 'topbar-serial__sep';
        sep.setAttribute('aria-hidden', 'true');
        sep.textContent = '·';
        root.appendChild(sep);

        const freqEl = document.createElement('span');
        freqEl.className = 'topbar-serial__freq';
        freqEl.textContent = '--';
        root.appendChild(freqEl);

        return root;
    }
}

window.registerTopbarChip({ id: 'reticulum', make: () => new ReticulumTopbarChip() });
