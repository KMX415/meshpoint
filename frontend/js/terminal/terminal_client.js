/**
 * WebSocket client for ``/api/terminal/ws``.
 *
 * Single responsibility: own one connection, encode/decode the
 * three-frame JSON envelope, and delegate UI updates via callbacks.
 * The xterm.js instance is owned by ``TerminalPanelController``;
 * this client does not touch the DOM directly.
 *
 * Frame contract (mirrored on the server):
 *
 *   client -> server:
 *     { "type": "input",  "data": <base64> }
 *     { "type": "resize", "rows": N, "cols": N }
 *
 *   server -> client:
 *     { "type": "ready",  "hostname": "...", "pid": N,
 *       "shell": "/bin/bash", "user": "meshpoint" }
 *     { "type": "output", "data": <base64> }
 *     { "type": "exit",   "code": N }
 *     { "type": "error",  "message": "..." }
 */

class TerminalClient {
    constructor() {
        this._ws = null;
        this.onOutput = null;
        this.onExit = null;
        this.onError = null;
        this.onOpen = null;
        this.onClose = null;
        this.onReady = null;
    }

    get connected() {
        return !!this._ws && this._ws.readyState === WebSocket.OPEN;
    }

    connect() {
        if (this._ws) this.disconnect();
        const proto = location.protocol === 'https:' ? 'wss' : 'ws';
        const url = `${proto}://${location.host}/api/terminal/ws`;
        this._ws = new WebSocket(url);
        this._ws.addEventListener('open', () => this.onOpen?.());
        this._ws.addEventListener('message', (event) => this._handleFrame(event.data));
        this._ws.addEventListener('close', (event) => {
            this.onClose?.({ code: event.code, reason: event.reason });
            this._ws = null;
        });
        this._ws.addEventListener('error', () => {
            this.onError?.('WebSocket error');
        });
    }

    disconnect() {
        if (!this._ws) return;
        try { this._ws.close(); } catch (_) {}
        this._ws = null;
    }

    sendInput(data) {
        if (!this.connected) return;
        const bytes = typeof data === 'string'
            ? new TextEncoder().encode(data)
            : data;
        this._ws.send(JSON.stringify({
            type: 'input',
            data: this._b64(bytes),
        }));
    }

    sendResize(rows, cols) {
        if (!this.connected) return;
        this._ws.send(JSON.stringify({ type: 'resize', rows, cols }));
    }

    _handleFrame(raw) {
        let frame;
        try { frame = JSON.parse(raw); } catch (_) { return; }
        if (!frame || typeof frame !== 'object') return;
        if (frame.type === 'output' && frame.data) {
            this.onOutput?.(this._fromB64(frame.data));
        } else if (frame.type === 'ready') {
            this.onReady?.({
                hostname: frame.hostname,
                pid: frame.pid,
                shell: frame.shell,
                user: frame.user,
            });
        } else if (frame.type === 'exit') {
            this.onExit?.(frame.code ?? 0);
        } else if (frame.type === 'error') {
            this.onError?.(frame.message || 'unknown error');
        }
    }

    _b64(bytes) {
        let binary = '';
        const view = new Uint8Array(bytes);
        for (let i = 0; i < view.length; i++) {
            binary += String.fromCharCode(view[i]);
        }
        return btoa(binary);
    }

    _fromB64(value) {
        const binary = atob(value);
        const len = binary.length;
        const out = new Uint8Array(len);
        for (let i = 0; i < len; i++) out[i] = binary.charCodeAt(i);
        return out;
    }
}

window.TerminalClient = TerminalClient;
