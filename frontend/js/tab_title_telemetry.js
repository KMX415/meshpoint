/**
 * Browser-tab title telemetry.
 *
 * Surfaces live state into the document.title so users can glance
 * at the OS task bar / browser tab strip and see what's happening
 * without switching tabs. Format:
 *
 *     "(N) Meshpoint · Online · -118 dBm"
 *
 * Where:
 *   - N is the unread-message badge count (when > 0). Hidden if 0.
 *   - "Online" / "Offline" / "Reconnecting" tracks websocket state.
 *   - Last component shows the smoothed noise floor when available.
 *
 * Single responsibility: keep document.title in sync. Reads from
 * the websocket directly; doesn't depend on other UI components.
 */
class TabTitleTelemetry {
    constructor(dashboardWs, baseTitle = 'Meshpoint') {
        this._ws = dashboardWs;
        this._base = baseTitle;
        this._unread = 0;
        this._connection = 'connecting';
        this._noiseValue = null;
        this._timer = null;
    }

    init() {
        if (!this._ws) return;
        this._ws.on('connected', () => {
            this._connection = 'online';
            this._render();
        });
        this._ws.on('disconnected', () => {
            this._connection = 'offline';
            this._render();
        });
        this._ws.on('noise_floor', (data) => {
            if (!data) return;
            this._noiseValue = (data.value_dbm != null && !data.stale)
                ? data.value_dbm : null;
            this._scheduleRender();
        });

        const observer = new MutationObserver(() => this._readUnreadBadge());
        const badgeEl = document.getElementById('msg-unread-badge');
        if (badgeEl) {
            observer.observe(badgeEl, {
                attributes: true,
                childList: true,
                subtree: true,
                characterData: true,
            });
            this._readUnreadBadge();
        }
    }

    _readUnreadBadge() {
        const badgeEl = document.getElementById('msg-unread-badge');
        if (!badgeEl) return;
        const visible = badgeEl.style.display !== 'none';
        const raw = (badgeEl.textContent || '').trim();
        const n = visible ? parseInt(raw, 10) : 0;
        this._unread = Number.isFinite(n) && n > 0 ? n : 0;
        this._render();
    }

    _scheduleRender() {
        // Coalesce noise-floor renders; we only need ~1Hz updates.
        if (this._timer) return;
        this._timer = setTimeout(() => {
            this._timer = null;
            this._render();
        }, 1000);
    }

    _render() {
        const parts = [];
        if (this._unread > 0) parts.push(`(${this._unread})`);
        parts.push(this._base);
        if (this._connection === 'online') parts.push('· Online');
        else if (this._connection === 'offline') parts.push('· Offline');
        else parts.push('· Connecting');
        if (this._noiseValue != null) {
            parts.push(`· ${this._noiseValue.toFixed(0)} dBm`);
        }
        document.title = parts.join(' ');
    }
}

window.TabTitleTelemetry = TabTitleTelemetry;
