/**
 * Configuration → Transmit card.
 *
 * Single responsibility: edit the ``transmit`` block in ``local.yaml``
 * (TX power, max duty cycle, relay enable, relay rate limits). Shares
 * the ``api`` helper shape used by the existing Radio cards so the
 * surrounding orchestrator can reuse the same plumbing.
 */

class TransmitConfigCard {
    constructor(api) {
        this._api = api;
        this._root = null;
    }

    mount(root) {
        this._root = root;
        this._root.innerHTML = `
            <article class="cfg-card">
                <header class="cfg-card__head">
                    <h3 class="cfg-card__title">Transmit</h3>
                    <p class="cfg-card__hint">Power, duty cycle, and relay behavior. Changes hot-reload on save where possible; some require a restart.</p>
                </header>
                <form class="cfg-form" data-tx-form>
                    <label class="cfg-field">
                        <span class="cfg-field__label">TX power (dBm)</span>
                        <input class="cfg-field__input" type="number" min="0" max="30" step="1" data-tx-power>
                    </label>
                    <label class="cfg-field">
                        <span class="cfg-field__label">Max duty cycle (%)</span>
                        <input class="cfg-field__input" type="number" min="0" max="100" step="0.1" data-tx-duty>
                    </label>
                    <label class="cfg-field cfg-field--toggle">
                        <input type="checkbox" data-tx-relay-enable>
                        <span class="cfg-field__label">Relay enabled</span>
                    </label>
                    <label class="cfg-field">
                        <span class="cfg-field__label">Relay max packets / minute</span>
                        <input class="cfg-field__input" type="number" min="0" max="600" step="1" data-tx-relay-rate>
                    </label>
                    <div class="cfg-card__actions">
                        <button class="terminal-button terminal-button--primary" type="submit">Save</button>
                    </div>
                    <p class="cfg-status" data-tx-status aria-live="polite"></p>
                </form>
            </article>
        `;
        this._form = this._root.querySelector('[data-tx-form]');
        this._powerEl = this._root.querySelector('[data-tx-power]');
        this._dutyEl = this._root.querySelector('[data-tx-duty]');
        this._relayEnable = this._root.querySelector('[data-tx-relay-enable]');
        this._relayRate = this._root.querySelector('[data-tx-relay-rate]');
        this._statusEl = this._root.querySelector('[data-tx-status]');
        this._form.addEventListener('submit', (e) => this._onSubmit(e));
    }

    render(config) {
        const tx = (config && config.transmit) || {};
        if (this._powerEl && tx.tx_power_dbm != null) this._powerEl.value = tx.tx_power_dbm;
        if (this._dutyEl && tx.max_duty_cycle_percent != null) this._dutyEl.value = tx.max_duty_cycle_percent;
        if (this._relayEnable) this._relayEnable.checked = !!(tx.relay && tx.relay.enabled);
        if (this._relayRate && tx.relay && tx.relay.max_packets_per_minute != null) {
            this._relayRate.value = tx.relay.max_packets_per_minute;
        }
    }

    async _onSubmit(event) {
        event.preventDefault();
        const payload = {
            tx_power_dbm: Number(this._powerEl.value),
            max_duty_cycle_percent: Number(this._dutyEl.value),
            relay: {
                enabled: this._relayEnable.checked,
                max_packets_per_minute: Number(this._relayRate.value),
            },
        };
        this._setStatus('pending', 'Saving…');
        const result = await this._api.put('/api/config/transmit', payload);
        if (result) {
            this._setStatus('success', 'Saved.');
            this._api.signalRestart('Transmit settings updated.');
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

window.TransmitConfigCard = TransmitConfigCard;
