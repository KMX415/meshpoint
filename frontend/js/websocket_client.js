class ConcentratorWebSocket {
    constructor() {
        this.socket = null;
        this.listeners = {};
        this.reconnectDelay = 2000;
        this.maxReconnectDelay = 30000;
        this.currentDelay = this.reconnectDelay;
    }

    connect() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const url = `${protocol}//${window.location.host}/ws`;

        this.socket = new WebSocket(url);

        this.socket.onopen = () => {
            this.currentDelay = this.reconnectDelay;
            this._emit('connected');
            this._updateStatusIndicator(true);
        };

        this.socket.onclose = () => {
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

    _updateStatusIndicator(connected) {
        const dot = document.getElementById('ws-status');
        const label = document.getElementById('ws-label');
        if (dot && label) {
            dot.className = connected
                ? 'status-dot status-dot--connected'
                : 'status-dot status-dot--disconnected';
            label.textContent = connected ? 'Connected' : 'Reconnecting...';
        }
    }
}

window.concentratorWS = new ConcentratorWebSocket();
