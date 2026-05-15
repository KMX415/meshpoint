/**
 * Configuration → MQTT card.
 *
 * Single responsibility: edit the ``mqtt`` block in ``local.yaml``
 * (enable, broker host/port, topic root, region segment, encrypted
 * toggle, gateway id) with a live preview of the resulting topic
 * prefix so operators can see what their packets will publish under.
 */

class MqttConfigCard {
    constructor(api) {
        this._api = api;
        this._root = null;
    }

    mount(root) {
        this._root = root;
        this._root.innerHTML = `
            <article class="cfg-card">
                <header class="cfg-card__head">
                    <h3 class="cfg-card__title">MQTT</h3>
                    <p class="cfg-card__hint">Hierarchical topic publishing for upstream consumers. The preview below shows the actual topic prefix packets will use.</p>
                </header>
                <form class="cfg-form" data-mqtt-form>
                    <label class="cfg-field cfg-field--toggle">
                        <input type="checkbox" data-mqtt-enabled>
                        <span class="cfg-field__label">MQTT enabled</span>
                    </label>
                    <div class="cfg-row">
                        <label class="cfg-field">
                            <span class="cfg-field__label">Broker host</span>
                            <input class="cfg-field__input" type="text" placeholder="mqtt.example.com" data-mqtt-host>
                        </label>
                        <label class="cfg-field cfg-field--narrow">
                            <span class="cfg-field__label">Port</span>
                            <input class="cfg-field__input" type="number" min="1" max="65535" data-mqtt-port>
                        </label>
                    </div>
                    <label class="cfg-field">
                        <span class="cfg-field__label">Topic root</span>
                        <input class="cfg-field__input" type="text" placeholder="msh" data-mqtt-topic-root>
                    </label>
                    <label class="cfg-field">
                        <span class="cfg-field__label">Region segment</span>
                        <input class="cfg-field__input" type="text" placeholder="US" data-mqtt-region>
                    </label>
                    <label class="cfg-field cfg-field--toggle">
                        <input type="checkbox" data-mqtt-encrypted>
                        <span class="cfg-field__label">Encrypted payloads</span>
                    </label>
                    <label class="cfg-field">
                        <span class="cfg-field__label">Gateway ID (optional)</span>
                        <input class="cfg-field__input" type="text" placeholder="auto-derived if blank" data-mqtt-gateway>
                    </label>
                    <div class="cfg-preview">
                        <span class="cfg-preview__label">Topic prefix preview</span>
                        <code class="cfg-preview__value" data-mqtt-preview>--</code>
                    </div>
                    <div class="cfg-card__actions">
                        <button class="terminal-button terminal-button--primary" type="submit">Save MQTT</button>
                    </div>
                    <p class="cfg-status" data-mqtt-status aria-live="polite"></p>
                </form>
            </article>
        `;
        this._form = this._root.querySelector('[data-mqtt-form]');
        this._enabled = this._root.querySelector('[data-mqtt-enabled]');
        this._host = this._root.querySelector('[data-mqtt-host]');
        this._port = this._root.querySelector('[data-mqtt-port]');
        this._topicRoot = this._root.querySelector('[data-mqtt-topic-root]');
        this._region = this._root.querySelector('[data-mqtt-region]');
        this._encrypted = this._root.querySelector('[data-mqtt-encrypted]');
        this._gateway = this._root.querySelector('[data-mqtt-gateway]');
        this._preview = this._root.querySelector('[data-mqtt-preview]');
        this._statusEl = this._root.querySelector('[data-mqtt-status]');

        this._form.addEventListener('submit', (e) => this._onSubmit(e));
        ['input', 'change'].forEach((ev) => {
            this._form.addEventListener(ev, () => this._renderPreview());
        });
    }

    render(config) {
        const mqtt = (config && config.mqtt) || {};
        if (this._enabled) this._enabled.checked = !!mqtt.enabled;
        if (this._host) this._host.value = mqtt.broker_host || '';
        if (this._port) this._port.value = mqtt.broker_port || 1883;
        if (this._topicRoot) this._topicRoot.value = mqtt.topic_root || 'msh';
        if (this._region) this._region.value = mqtt.region_segment || '';
        if (this._encrypted) this._encrypted.checked = !!mqtt.encrypted;
        if (this._gateway) this._gateway.value = mqtt.gateway_id || '';
        this._renderPreview();
    }

    _renderPreview() {
        if (!this._preview) return;
        const root = (this._topicRoot.value || 'msh').trim();
        const region = (this._region.value || '').trim();
        const encrypted = this._encrypted.checked ? 'e' : 'c';
        const segments = [root];
        if (region) segments.push(region);
        segments.push(encrypted);
        this._preview.textContent = segments.join('/') + '/...';
    }

    async _onSubmit(event) {
        event.preventDefault();
        const payload = {
            enabled: this._enabled.checked,
            broker_host: this._host.value.trim(),
            broker_port: Number(this._port.value),
            topic_root: this._topicRoot.value.trim() || 'msh',
            region_segment: this._region.value.trim(),
            encrypted: this._encrypted.checked,
            gateway_id: this._gateway.value.trim(),
        };
        this._setStatus('pending', 'Saving…');
        const result = await this._api.put('/api/config/mqtt', payload);
        if (result) {
            this._setStatus('success', 'Saved.');
            this._api.signalRestart('MQTT settings updated.');
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

window.MqttConfigCard = MqttConfigCard;
