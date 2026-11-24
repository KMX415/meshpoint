/** PiMesh-only protocol selection inside the normal Configuration page. */
class PimeshProtocolCard {
    constructor(api) {
        this._api = api;
        this._busy = false;
        this._active = '';
    }

    mount(root) {
        this._root = root;
        root.innerHTML = `
            <article class="cfg-card">
                <header class="cfg-card__head">
                    <h3 class="cfg-card__title">PiMesh radio</h3>
                    <p class="cfg-card__hint" data-pimesh-board></p>
                </header>
                <form class="cfg-form">
                    <label class="cfg-field">
                        <span class="cfg-field__label">Radio protocol</span>
                        <select class="cfg-field__input" data-pimesh-protocol>
                            <option value="meshtastic">Meshtastic</option>
                            <option value="meshcore">MeshCore</option>
                        </select>
                        <span class="cfg-field__hint">Switching briefly pauses messaging and reconnects the dashboard. Each protocol keeps its settings and history.</span>
                    </label>
                    <div class="cfg-card__actions">
                        <button class="terminal-button terminal-button--primary" type="submit" disabled>Switch protocol</button>
                    </div>
                    <p class="cfg-status" role="status" aria-live="polite" data-pimesh-status>Checking radio status…</p>
                </form>
            </article>`;
        this._select = root.querySelector('select');
        this._button = root.querySelector('button');
        this._status = root.querySelector('[data-pimesh-status]');
        this._select.addEventListener('change', () => this._updateButton());
        root.querySelector('form').addEventListener('submit', (event) => {
            event.preventDefault();
            this._switch();
        });
    }

    render(config) {
        const allowed = window.PlatformContext?.isPimesh(config);
        this._root.hidden = !allowed;
        if (!allowed) return;
        this._root.querySelector('[data-pimesh-board]').textContent = config.device.hardware_description;
        if (!this._active) {
            this._active = config.device.radio_protocol;
            this._select.value = this._active;
        }
        this._updateButton();
        if (!this._polling) this._refresh();
    }

    _updateButton() {
        this._select.disabled = this._busy;
        this._button.disabled = this._busy || (this._select.value === this._active && !this._failed);
        this._button.textContent = this._failed && this._select.value === this._active ? 'Retry radio connection' : 'Switch protocol';
        this._root.setAttribute('aria-busy', String(this._busy));
    }

    async _readStatus() {
        const response = await fetch('/api/pimesh/status', {
            credentials: 'same-origin', cache: 'no-store', signal: AbortSignal.timeout(5000),
        });
        if (!response.ok) throw new Error(`Radio status unavailable (${response.status})`);
        return response.json();
    }

    async _refresh() {
        try {
            const status = await this._readStatus();
            this._show(status);
            if (status.switching) this._poll();
            else if (status.active !== this._active) window.location.reload();
        } catch (error) {
            this._status.textContent = error.message;
        }
    }

    _show(status) {
        this._busy = status.switching;
        this._failed = status.phase === 'failed';
        const name = status.active === 'meshcore' ? 'MeshCore' : 'Meshtastic';
        this._status.textContent = status.error || (status.switching
            ? `Switching protocol: ${status.phase.replaceAll('_', ' ')}…`
            : `${name}: ${status.connected ? 'connected' : 'waiting for radio connection'}.`);
        this._updateButton();
    }

    async _switch() {
        if (this._busy || (this._select.value === this._active && !this._failed)) return;
        this._busy = true;
        this._updateButton();
        this._status.textContent = 'Starting protocol switch…';
        const target = this._select.value;
        let result;
        try {
            result = await this._api.post('/api/pimesh/protocol', { protocol: target });
        } catch (_) {
            // The service may stop after accepting the request but before replying.
        }
        if (!result) {
            this._status.textContent = 'Checking whether the switch started. Reconnecting to Meshpoint.';
            return this._poll(target);
        }
        this._show(result);
        return this._poll();
    }

    async _poll(uncertainTarget = null) {
        if (this._polling) return;
        this._polling = true;
        // Allow the queued supervisor to start before treating the old state as final.
        const settleAfter = Date.now() + 10000;
        const deadline = Date.now() + 330000;
        try {
            while (Date.now() < deadline && this._root.isConnected) {
                await new Promise(resolve => setTimeout(resolve, 2500));
                try {
                    const status = await this._readStatus();
                    if (status.switching) uncertainTarget = null;
                    if (uncertainTarget && !status.switching && status.active !== uncertainTarget
                        && Date.now() < settleAfter) continue;
                    this._show(status);
                    if (!status.switching) {
                        // Reload mounts all normal cards against the newly active backend.
                        if (status.active !== this._active) window.location.reload();
                        else { this._select.value = status.active; this._updateButton(); }
                        return;
                    }
                } catch (_) {
                    this._status.textContent = 'Reconnecting to Meshpoint. Your settings and history are preserved…';
                }
            }
            this._status.textContent = 'Still waiting for Meshpoint. Reload this page to check recovery status.';
        } finally {
            this._polling = false;
        }
    }
}
window.PimeshProtocolCard = PimeshProtocolCard;
