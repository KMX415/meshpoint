/**
 * Topbar — connection lamp.
 *
 * Renders an "ONLINE / RECONNECTING / OFFLINE" status pill driven by
 * the WebSocket connection state. The lamp animates a subtle pulse
 * when online so the chrome reads as "alive" rather than static.
 *
 * Single responsibility: own the lamp DOM and its three visual states.
 * The orchestrator (TopbarController) feeds it state changes.
 */
class TopbarLamp {
    constructor(rootEl) {
        this._root = rootEl;
        this._dot = rootEl.querySelector('.topbar-lamp__dot');
        this._label = rootEl.querySelector('.topbar-lamp__label');
        this._state = 'connecting';
    }

    setState(state) {
        if (state === this._state) return;
        this._state = state;
        this._root.classList.remove(
            'topbar-lamp--online',
            'topbar-lamp--offline',
            'topbar-lamp--reconnecting',
        );
        if (state === 'online') {
            this._root.classList.add('topbar-lamp--online');
            this._label.textContent = 'ONLINE';
        } else if (state === 'offline') {
            this._root.classList.add('topbar-lamp--offline');
            this._label.textContent = 'OFFLINE';
        } else {
            this._root.classList.add('topbar-lamp--reconnecting');
            this._label.textContent = 'RECONNECTING';
        }
    }
}

window.TopbarLamp = TopbarLamp;
