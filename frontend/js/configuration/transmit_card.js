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
                    <p class="cfg-card__hint">Native TX and onboard SX1302 relay. Enable relay here; burst and RSSI filters apply to concentrator rebroadcasts.</p>
                </header>
                <form class="cfg-form" data-tx-form>
                    <label class="cfg-field cfg-field--toggle">
                        <input type="checkbox" data-tx-enabled>
                        <span class="cfg-field__label">Native TX enabled</span>
                    </label>
                    <p class="cfg-card__hint cfg-card__hint--nested">
                        Required for MeshCore companion status, dashboard messaging,
                        and Send Advert. USB packet capture works independently when
                        the MeshCore USB source is enabled.
                    </p>
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
                        <span class="cfg-field__label">Relay max / minute</span>
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
        this._enabledEl = this._root.querySelector('[data-tx-enabled]');
        this._powerEl = this._root.querySelector('[data-tx-power]');
        this._dutyEl = this._root.querySelector('[data-tx-duty]');
        this._relayEnable = this._root.querySelector('[data-tx-relay-enable]');
        this._relayRate = this._root.querySelector('[data-tx-relay-rate]');
        this._relayBurst = this._root.querySelector('[data-tx-relay-burst]');
        this._relayMinRssi = this._root.querySelector('[data-tx-relay-min-rssi]');
        this._relayMaxRssi = this._root.querySelector('[data-tx-relay-max-rssi]');
        this._statusEl = this._root.querySelector('[data-tx-status]');
        this._form.addEventListener('submit', (e) => this._onSubmit(e));
    }

    render(config) {
        const tx = (config && config.transmit) || {};
        if (this._enabledEl) this._enabledEl.checked = !!tx.enabled;
        if (this._powerEl && tx.tx_power_dbm != null) this._powerEl.value = tx.tx_power_dbm;
        if (this._dutyEl && tx.max_duty_cycle_percent != null) this._dutyEl.value = tx.max_duty_cycle_percent;
        if (this._relayEnable) this._relayEnable.checked = !!(tx.relay && tx.relay.enabled);
        if (this._relayRate && tx.relay && tx.relay.max_relay_per_minute != null) {
            this._relayRate.value = tx.relay.max_relay_per_minute;
        }
        const relayFull = config.relay || tx.relay || {};
        if (this._relayBurst && relayFull.burst_size != null) {
            this._relayBurst.value = relayFull.burst_size;
        }
        if (this._relayMinRssi && relayFull.min_relay_rssi != null) {
            this._relayMinRssi.value = relayFull.min_relay_rssi;
        }
        if (this._relayMaxRssi && relayFull.max_relay_rssi != null) {
            this._relayMaxRssi.value = relayFull.max_relay_rssi;
        }
    }

    async _onSubmit(event) {
        event.preventDefault();
        const relay = { enabled: this._relayEnable.checked };
        const rateRaw = this._relayRate.value.trim();
        if (rateRaw !== '') {
            const rate = Number(rateRaw);
            if (!Number.isFinite(rate)) {
                this._setStatus('error', 'Relay rate must be a number.');
                return;
            }
            relay.max_relay_per_minute = rate;
        }
        const payload = {
            enabled: this._enabledEl.checked,
            tx_power_dbm: Number(this._powerEl.value),
            max_duty_cycle_percent: Number(this._dutyEl.value),
            relay,
        };
        this._setStatus('pending', 'Saving…');
        const txResult = await this._api.put('/api/config/transmit', payload);
        if (!txResult) {
            this._setStatus('error', 'Transmit save failed.');
            return;
        }

        const relayFilter = await this._api.put('/api/config/relay', {
            burst_size: Number(this._relayBurst.value),
            min_relay_rssi: Number(this._relayMinRssi.value),
            max_relay_rssi: Number(this._relayMaxRssi.value),
        });
        if (!relayFilter) {
            this._setStatus('error', 'Relay filter save failed.');
            return;
        }

        this._setStatus('success', 'Saved.');
        this._api.signalRestart('Transmit settings updated.');
    }

    _setStatus(kind, message) {
        if (!this._statusEl) return;
        this._statusEl.dataset.kind = kind;
        this._statusEl.textContent = message;
    }
}

window.TransmitConfigCard = TransmitConfigCard;
