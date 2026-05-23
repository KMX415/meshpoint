/**
 * Sidebar logo pip / ring state binding.
 *
 * Mirrors the websocket connection state onto the logo frame's
 * data-state attribute so CSS can render the matching pip color
 * and ring animation. Three states: connecting / online / offline.
 *
 * Single responsibility: keep the data attribute in sync with
 * the live WS state. No DOM creation; the markup lives in
 * frontend/index.html.
 */
class SidebarLogoPip {
    constructor(rootEl, dashboardWs) {
        this._root = rootEl;
        this._ws = dashboardWs;
    }

    init() {
        this._setState('connecting');
        if (!this._ws) {
            this._setState('offline');
            return;
        }
        this._ws.on('connected', () => this._setState('online'));
        this._ws.on('disconnected', () => this._setState('offline'));
        if (this._ws.socket && this._ws.socket.readyState === 1) {
            this._setState('online');
        }
    }

    _setState(state) {
        if (!this._root) return;
        this._root.dataset.state = state;
    }
}

window.SidebarLogoPip = SidebarLogoPip;
