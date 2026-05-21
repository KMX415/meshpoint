/**
 * Topbar — orchestrator.
 *
 * Owns the topbar shell that sits above every section. Coordinates
 * four small components:
 *   - TopbarLamp           (websocket connection state)
 *   - TopbarIdentityBadge  (LCD-style short-name)
 *   - TopbarRadioChip      (region · frequency · preset)
 *   - TopbarMeshcoreChip   (companion lamp · name · MHz · channel)
 *   - TopbarActions        (right-side quick-action buttons)
 *
 * Data sources: /api/config for radio + identity values; the existing
 * dashboardWS instance for connection state. Refreshes itself on a
 * 10-second cadence so pulled-config changes from any sub-route
 * propagate without forcing a manual reload.
 */
class TopbarController {
    constructor(rootEl, dashboardWs) {
        this._root = rootEl;
        this._ws = dashboardWs;
        this._refreshTimer = null;
        this._lamp = new TopbarLamp(rootEl.querySelector('.topbar-lamp'));
        this._identity = new TopbarIdentityBadge(
            rootEl.querySelector('.topbar-ident'),
        );
        this._radio = new TopbarRadioChip(
            rootEl.querySelector('.topbar-radio'),
        );
        this._meshcore = new TopbarMeshcoreChip(
            rootEl.querySelector('#topbar-meshcore-group'),
            rootEl.querySelector('.topbar-meshcore'),
        );
        this._actions = new TopbarActions(
            rootEl.querySelector('.topbar-actions'),
        );
    }

    init() {
        this._wireWebSocket();
        this._refreshConfig();
        this._refreshTimer = setInterval(
            () => this._refreshConfig(), 10_000,
        );
    }

    destroy() {
        if (this._refreshTimer) clearInterval(this._refreshTimer);
    }

    _wireWebSocket() {
        if (!this._ws) {
            this._lamp.setState('offline');
            return;
        }
        this._ws.on('connected', () => this._lamp.setState('online'));
        this._ws.on('disconnected', () => this._lamp.setState('reconnecting'));
        // Initial probe in case we attached after the first event.
        if (this._ws.socket && this._ws.socket.readyState === 1) {
            this._lamp.setState('online');
        }
    }

    async _refreshConfig() {
        try {
            const res = await fetch('/api/config', { credentials: 'same-origin' });
            if (!res.ok) return;
            const cfg = await res.json();
            this._radio.setRadio(cfg.radio || null);
            this._meshcore.setMeshcore(cfg.meshcore || null);
            const tx = cfg.transmit || {};
            this._identity.setShortName(tx.short_name);
        } catch (_e) { /* swallow; next tick will retry */ }
    }

    /**
     * Public hook so other components can register a topbar action
     * without poking at the inner DOM. Used by Sprint D for the
     * command palette and theme toggle.
     */
    registerAction(spec) {
        return this._actions.register(spec);
    }
}

window.TopbarController = TopbarController;
