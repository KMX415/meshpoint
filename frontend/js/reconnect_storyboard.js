/**
 * Reconnect storyboard pill.
 *
 * When the websocket drops and recovers, paint a small pill in the
 * top-right showing what's resyncing:
 *   "Reconnecting..." while disconnected
 *   "Resyncing telemetry" -> "rooms" -> "nodes" -> "messages" -> "ready"
 * on reconnect, then fades out.
 *
 * Single responsibility: own the pill DOM and choreograph the
 * stage transitions. Listens to dashboardWs connect/disconnect
 * events; never touches transport itself.
 */
class ReconnectStoryboard {
    static STAGES = [
        { label: 'Resyncing telemetry...', delay: 350 },
        { label: 'Catching up on packets...', delay: 600 },
        { label: 'Refreshing nodes...', delay: 850 },
        { label: 'Ready.', delay: 1100 },
    ];

    constructor(dashboardWs) {
        this._ws = dashboardWs;
        this._root = null;
        this._labelEl = null;
        this._dotEl = null;
        this._wasOnline = false;
        this._timer = null;
    }

    mount() {
        if (document.getElementById('reconnect-storyboard')) return;
        const root = document.createElement('div');
        root.id = 'reconnect-storyboard';
        root.className = 'reconnect-pill';
        root.setAttribute('role', 'status');
        root.setAttribute('aria-live', 'polite');
        root.innerHTML = `
            <span class="reconnect-pill__dot" aria-hidden="true"></span>
            <span class="reconnect-pill__label" id="reconnect-pill-label">--</span>
        `;
        document.body.appendChild(root);
        this._root = root;
        this._labelEl = root.querySelector('#reconnect-pill-label');
        this._dotEl = root.querySelector('.reconnect-pill__dot');
    }

    init() {
        if (!this._ws) return;
        this._ws.on('connected', () => this._onConnected());
        this._ws.on('disconnected', () => this._onDisconnected());
    }

    _onDisconnected() {
        this._wasOnline = true;
        this._show();
        this._setStage('reconnecting', 'Reconnecting...');
    }

    _onConnected() {
        if (!this._wasOnline) {
            // First-ever connect. No storyboard, just hide.
            this._wasOnline = true;
            this._hide();
            return;
        }
        this._show();
        this._setStage('syncing', 'Reconnected.');
        this._stepThroughStages(0);
    }

    _stepThroughStages(index) {
        if (this._timer) clearTimeout(this._timer);
        const stage = ReconnectStoryboard.STAGES[index];
        if (!stage) {
            this._timer = setTimeout(() => this._hide(), 700);
            return;
        }
        this._timer = setTimeout(() => {
            this._setStage(
                index === ReconnectStoryboard.STAGES.length - 1
                    ? 'ready'
                    : 'syncing',
                stage.label,
            );
            this._stepThroughStages(index + 1);
        }, stage.delay);
    }

    _setStage(state, label) {
        if (!this._root) return;
        this._labelEl.textContent = label;
        this._root.classList.remove(
            'reconnect-pill--reconnecting',
            'reconnect-pill--syncing',
            'reconnect-pill--ready',
        );
        this._root.classList.add(`reconnect-pill--${state}`);
    }

    _show() {
        if (this._root) this._root.classList.add('reconnect-pill--visible');
    }

    _hide() {
        if (this._root) this._root.classList.remove('reconnect-pill--visible');
    }
}

window.ReconnectStoryboard = ReconnectStoryboard;
