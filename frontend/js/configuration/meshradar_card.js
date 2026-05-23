/**
 * Configuration → Meshradar card.
 *
 * Cloud uplink tuning (API key, URL, buffers). Does not expose
 * ``upstream.enabled``; disabling cloud stays a yaml/wizard concern.
 */

class MeshradarConfigCard {
    constructor(api) {
        this._api = api;
        this._root = null;
        this._tokenDirty = false;
    }

    mount(root) {
        this._root = root;
        this._root.innerHTML = `
            <article class="cfg-card">
                <header class="cfg-card__head">
                    <h3 class="cfg-card__title">Meshradar</h3>
                    <p class="cfg-card__hint">
                        WebSocket uplink to meshradar.io for fleet map, history, and
                        remote commands. To run fully offline, edit
                        <code>upstream.enabled</code> in local.yaml (not exposed here).
                    </p>
                </header>
                <form class="cfg-form" data-mr-form>
                    <label class="cfg-field">
                        <span class="cfg-field__label">WebSocket URL</span>
                        <input class="cfg-field__input" type="url"
                               data-mr-url placeholder="wss://api.meshradar.io">
                    </label>
                    <label class="cfg-field">
                        <span class="cfg-field__label">API key</span>
                        <input class="cfg-field__input" type="password" data-mr-token
                               placeholder="Leave blank to keep current"
                               autocomplete="new-password">
                    </label>
                    <div class="cfg-row">
                        <label class="cfg-field">
                            <span class="cfg-field__label">Reconnect interval (s)</span>
                            <input class="cfg-field__input" type="number" min="1" max="3600"
                                   data-mr-reconnect>
                        </label>
                        <label class="cfg-field">
                            <span class="cfg-field__label">Offline buffer size</span>
                            <input class="cfg-field__input" type="number" min="100"
                                   max="100000" step="100" data-mr-buffer>
                        </label>
                    </div>
                    <div class="cfg-card__actions">
                        <button class="terminal-button terminal-button--primary" type="submit">
                            Save Meshradar
                        </button>
                    </div>
                    <p class="cfg-status" data-mr-status aria-live="polite"></p>
                </form>
            </article>
        `;
        this._form = this._root.querySelector('[data-mr-form]');
        this._url = this._root.querySelector('[data-mr-url]');
        this._token = this._root.querySelector('[data-mr-token]');
        this._reconnect = this._root.querySelector('[data-mr-reconnect]');
        this._buffer = this._root.querySelector('[data-mr-buffer]');
        this._statusEl = this._root.querySelector('[data-mr-status]');
        this._token.addEventListener('input', () => { this._tokenDirty = true; });
        this._form.addEventListener('submit', (e) => this._onSubmit(e));
    }

    render(config) {
        const up = (config && config.upstream) || {};
        if (this._url) this._url.value = up.url || 'wss://api.meshradar.io';
        if (this._reconnect) {
            this._reconnect.value = up.reconnect_interval_seconds ?? 10;
        }
        if (this._buffer) this._buffer.value = up.buffer_max_size ?? 5000;
        if (this._token) {
            this._token.value = '';
            this._token.placeholder = up.auth_token_set
                ? 'Leave blank to keep current API key'
                : 'Paste Meshradar API key';
        }
        this._tokenDirty = false;
    }

    async _onSubmit(event) {
        event.preventDefault();
        const payload = {
            url: this._url.value.trim(),
            reconnect_interval_seconds: Number(this._reconnect.value),
            buffer_max_size: Number(this._buffer.value),
            auth_token_unchanged: !this._tokenDirty,
        };
        if (this._tokenDirty) {
            payload.auth_token = this._token.value;
        }
        this._setStatus('pending', 'Saving…');
        const result = await this._api.put('/api/config/upstream', payload);
        if (result) {
            this._setStatus('success', 'Saved.');
            this._tokenDirty = false;
            if (this._token) this._token.value = '';
            this._api.signalRestart('Meshradar uplink settings updated.');
        } else {
            this._setStatus('error', 'Save failed.');
        }
    }

    _setStatus(kind, message) {
        if (!this._statusEl) return;
        this._statusEl.dataset.kind = kind;
        this._statusEl.textContent = message;
    }
}

window.MeshradarConfigCard = MeshradarConfigCard;
