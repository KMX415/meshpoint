/**
 * Configuration → Advanced — per-channel relay duty throttle (est.).
 */

class RelayThrottleCard {
    constructor(api) {
        this._api = api;
        this._root = null;
        this._throttle = {};
    }

    mount(root) {
        this._root = root;
        this._root.innerHTML = `
            <article class="cfg-card">
                <header class="cfg-card__head">
                    <h3 class="cfg-card__title">Relay channel throttle (est.)</h3>
                    <p class="cfg-card__hint">
                        Rolling 1 h ToA budget per channel. Relay TX only — does not limit native messaging.
                        EU868 capped at 1% regulatory ceiling.
                    </p>
                </header>
                <form class="cfg-form" data-relay-throttle-form>
                    <div class="cfg-throttle-grid" data-throttle-grid></div>
                    <div class="cfg-card__actions">
                        <button class="terminal-button terminal-button--primary"
                                type="submit">Save relay throttle</button>
                    </div>
                    <p class="cfg-status" data-relay-throttle-status aria-live="polite"></p>
                </form>
            </article>
        `;
        this._throttleGrid = this._root.querySelector('[data-throttle-grid]');
        this._statusEl = this._root.querySelector('[data-relay-throttle-status]');
        this._root.querySelector('[data-relay-throttle-form]')
            .addEventListener('submit', (e) => this._onSubmit(e));
        this._paintThrottleGrid();
    }

    render(config) {
        const relay = config.relay || {};
        this._throttle = { ...(relay.channel_throttle_percent || {}) };
        this._paintThrottleGrid();
    }

    _paintThrottleGrid() {
        if (!this._throttleGrid) return;
        const rows = [];
        for (let ch = 0; ch <= 7; ch += 1) {
            const key = String(ch);
            const value = this._throttle[key] != null ? this._throttle[key] : 100;
            rows.push(`
                <label class="cfg-throttle-row">
                    <span class="cfg-throttle-label">Ch ${ch}</span>
                    <input class="cfg-throttle-range" type="range" min="1" max="100" step="1"
                           data-throttle-ch="${ch}" value="${value}">
                    <span class="cfg-throttle-value" data-throttle-val="${ch}">${value}%</span>
                </label>
            `);
        }
        this._throttleGrid.innerHTML = rows.join('');
        this._throttleGrid.querySelectorAll('[data-throttle-ch]').forEach((input) => {
            input.addEventListener('input', () => {
                const ch = input.dataset.throttleCh;
                const pct = Number(input.value);
                this._throttle[ch] = pct;
                const valEl = this._throttleGrid.querySelector(`[data-throttle-val="${ch}"]`);
                if (valEl) valEl.textContent = `${pct}%`;
            });
        });
    }

    _throttlePayload() {
        const payload = {};
        for (let ch = 0; ch <= 7; ch += 1) {
            const key = String(ch);
            const pct = Number(this._throttle[key] != null ? this._throttle[key] : 100);
            if (pct !== 100) payload[key] = pct;
        }
        return payload;
    }

    async _onSubmit(event) {
        event.preventDefault();
        this._setStatus('pending', 'Saving…');
        const result = await this._api.put('/api/config/relay', {
            channel_throttle_percent: this._throttlePayload(),
        });
        if (!result) {
            this._setStatus('error', 'Save failed.');
            return;
        }
        this._setStatus('success', 'Saved.');
        this._api.toast('Relay throttle applied (no restart required).');
        this._api.refresh();
    }

    _setStatus(kind, message) {
        if (!this._statusEl) return;
        this._statusEl.dataset.kind = kind;
        this._statusEl.textContent = message;
    }
}

window.RelayThrottleCard = RelayThrottleCard;
