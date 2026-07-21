/**
 * Topbar — orchestrator.
 *
 * Coordinates protocol chips and quick actions:
 *   - TopbarMeshtasticChip  (WS lamp · short name · region · MHz · preset)
 *   - TopbarMeshcoreChip    (companion lamp · name · MHz · channel)
 *   - TopbarActions         (right-side quick-action buttons)
 *
 * Data: /api/config on a 10s cadence; dashboard WebSocket for connection lamp.
 */
class TopbarController {
    constructor(rootEl, dashboardWs) {
        this._root = rootEl;
        this._ws = dashboardWs;
        this._refreshTimer = null;
        this._meshtastic = new TopbarMeshtasticChip(
            rootEl.querySelector('.topbar-meshtastic'),
        );
        this._meshcore = new TopbarMeshcoreChip(
            rootEl.querySelector('#topbar-meshcore-group'),
            rootEl.querySelector('.topbar-meshcore'),
        );
        this._serial = new TopbarSerialChip(
            rootEl.querySelector('#topbar-serial-group'),
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
            this._meshtastic.setConnectionState('offline');
            this._meshcore.setDashboardReachable(false);
            this._serial.setDashboardReachable(false);
            return;
        }
        this._ws.on('connected', () => {
            this._meshtastic.setConnectionState('online');
            this._meshcore.setDashboardReachable(true);
            this._serial.setDashboardReachable(true);
            this._refreshConfig();
        });
        this._ws.on('disconnected', () => {
            this._meshtastic.setConnectionState('reconnecting');
            this._meshcore.setDashboardReachable(false);
            this._serial.setDashboardReachable(false);
        });
        if (this._ws.socket && this._ws.socket.readyState === 1) {
            this._meshtastic.setConnectionState('online');
            this._meshcore.setDashboardReachable(true);
            this._serial.setDashboardReachable(true);
        } else {
            this._meshcore.setDashboardReachable(false);
            this._serial.setDashboardReachable(false);
        }
    }

    async _refreshConfig() {
        try {
            const res = await fetch('/api/config', { credentials: 'same-origin' });
            if (!res.ok) {
                this._meshcore.setDashboardReachable(false);
                this._serial.setDashboardReachable(false);
                return;
            }
            const cfg = await res.json();
            this._meshcore.setDashboardReachable(true);
            this._serial.setDashboardReachable(true);
            const tx = cfg.transmit || {};
            this._meshtastic.setMeshtastic({
                shortName: tx.short_name,
                radio: cfg.radio || null,
            });
            this._meshcore.setMeshcore(cfg.meshcore || null);
            this._serial.setSerial(cfg.serial || []);
            document.dispatchEvent(
                new CustomEvent('meshpoint:configUpdated', { detail: cfg }),
            );
        } catch (_e) {
            this._meshcore.setDashboardReachable(false);
            this._serial.setDashboardReachable(false);
        }
    }

    registerAction(spec) {
        return this._actions.register(spec);
    }
}

window.TopbarController = TopbarController;
