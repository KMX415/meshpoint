class ConcentratorWebSocket {
    constructor() {
        this.socket = null;
        this.listeners = {};
        this.reconnectDelay = 2000;
        this.maxReconnectDelay = 30000;
        this.currentDelay = this.reconnectDelay;
        this._everOpened = false;
        this._authProbeInFlight = false;
    }

    connect() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const url = `${protocol}//${window.location.host}/ws`;

        // Cookie auth is the primary contract: a same-origin WS
        // upgrade carries the meshpoint_session cookie automatically.
        // No query-string token is required for browser clients.
        this.socket = new WebSocket(url);
        this._everOpened = false;

        this.socket.onopen = () => {
            this.currentDelay = this.reconnectDelay;
            this._everOpened = true;
            this._emit('connected');
            this._updateStatusIndicator(true);
        };

        this.socket.onclose = (event) => {
            if (event && event.code === 4401) {
                // Server rejected the upgrade (no session / expired).
                // Bounce to /login with the current path as `next`.
                const next = encodeURIComponent(location.pathname + location.search);
                location.assign(`/login?next=${next}`);
                return;
            }
            // Defense in depth for handshake-time failures: if the
            // socket never reached the open state, the close code is
            // unreliable across browsers (typically 1006 even when the
            // server intended a custom code). A pre-accept reject on
            // the server reads as 1006 here, identical to a real
            // network blip. Probe an auth-required endpoint so the
            // global 401 interceptor in app.js can redirect us if the
            // failure is auth-shaped, then schedule a reconnect.
            if (!this._everOpened && !this._authProbeInFlight) {
                this._probeAuthAndMaybeRedirect();
            }
            this._emit('disconnected');
            this._updateStatusIndicator(false);
            this._scheduleReconnect();
        };

        this.socket.onerror = () => {
            this._updateStatusIndicator(false);
        };

        this.socket.onmessage = (event) => {
            try {
                const message = JSON.parse(event.data);
                this._emit(message.type, message.data);
            } catch (e) {
                console.error('Failed to parse WebSocket message:', e);
            }
        };
    }

    on(eventType, callback) {
        if (!this.listeners[eventType]) {
            this.listeners[eventType] = [];
        }
        this.listeners[eventType].push(callback);
    }

    _emit(eventType, data) {
        const handlers = this.listeners[eventType] || [];
        handlers.forEach(fn => {
            try { fn(data); } catch (e) { console.error('Handler error:', e); }
        });
    }

    _scheduleReconnect() {
        setTimeout(() => {
            this.currentDelay = Math.min(this.currentDelay * 1.5, this.maxReconnectDelay);
            this.connect();
        }, this.currentDelay);
    }

    async _probeAuthAndMaybeRedirect() {
        this._authProbeInFlight = true;
        try {
            // Any auth-gated /api endpoint works. /api/device/status
            // is small, idempotent, and present on every Meshpoint.
            // The global 401 interceptor in app.js performs the actual
            // location.assign('/login?next=...') if this returns 401.
            await fetch('/api/device/status', { credentials: 'same-origin' });
        } catch (_) {
            /* network-level failure -- not an auth issue, fall through
               and let the reconnect schedule keep retrying */
        } finally {
            this._authProbeInFlight = false;
        }
    }

    _updateStatusIndicator(connected) {
        const sidebarDot = document.getElementById('sidebar-status-dot');
        const sidebarText = document.getElementById('sidebar-status-text');
        if (sidebarDot) {
            sidebarDot.className = connected
                ? 'status-dot status-dot--connected'
                : 'status-dot status-dot--disconnected';
        }
        if (sidebarText && !connected) {
            sidebarText.textContent = 'reconnecting...';
        }
    }
}

window.concentratorWS = new ConcentratorWebSocket();
