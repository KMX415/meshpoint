/**
 * Configuration → MQTT card.
 *
 * Full ``mqtt:`` block editor per docs/MQTT-AND-MESHRADAR.md: broker
 * credentials, two-gate allowlist, JSON mirror, location precision, HA.
 */

class MqttConfigCard {
    constructor(api) {
        this._api = api;
        this._root = null;
        this._passwordDirty = false;
        this._unsubDisplayUnits = null;
        this._runtimeInterval = null;
    }

    mount(root) {
        this._root = root;
        this._root.innerHTML = `
            <article class="cfg-card">
                <header class="cfg-card__head">
                    <h3 class="cfg-card__title">MQTT</h3>
                    <p class="cfg-card__hint">
                        Community MQTT gateway (meshmap.net, Home Assistant, etc.).
                        Gate 1: enable below. Gate 2: only channels in the allowlist
                        are published. Undecrypted packets never leave the device.
                    </p>
                </header>
                <div class="mqtt-runtime mqtt-runtime--disabled" data-mqtt-runtime hidden>
                    <span class="mqtt-runtime__label">BROKER</span>
                    <span class="mqtt-runtime__state" data-mqtt-runtime-text>Loading…</span>
                </div>
                <form class="cfg-form" data-mqtt-form>
                    <label class="cfg-field cfg-field--toggle">
                        <input type="checkbox" data-mqtt-enabled>
                        <span class="cfg-field__label">MQTT enabled</span>
                    </label>
                    <fieldset class="cfg-fieldset">
                        <legend class="cfg-fieldset__legend">Broker</legend>
                        <div class="cfg-row">
                            <label class="cfg-field">
                                <span class="cfg-field__label">Host</span>
                                <input class="cfg-field__input" type="text"
                                       placeholder="mqtt.meshtastic.org" data-mqtt-host>
                            </label>
                            <label class="cfg-field cfg-field--narrow">
                                <span class="cfg-field__label">Port</span>
                                <input class="cfg-field__input" type="number"
                                       min="1" max="65535" data-mqtt-port>
                            </label>
                        </div>
                        <label class="cfg-field">
                            <span class="cfg-field__label">Username</span>
                            <input class="cfg-field__input" type="text" data-mqtt-user
                                   autocomplete="off">
                        </label>
                        <label class="cfg-field">
                            <span class="cfg-field__label">Password</span>
                            <input class="cfg-field__input" type="password" data-mqtt-pass
                                   placeholder="Leave blank to keep current"
                                   autocomplete="new-password">
                        </label>
                    </fieldset>
                    <fieldset class="cfg-fieldset">
                        <legend class="cfg-fieldset__legend">Topics</legend>
                        <label class="cfg-field">
                            <span class="cfg-field__label">Topic root</span>
                            <input class="cfg-field__input" type="text" placeholder="msh"
                                   data-mqtt-topic-root>
                            <span class="cfg-field__hint">Keep as <code>msh</code>; put
                                state or region in the segment below.</span>
                        </label>
                        <label class="cfg-field">
                            <span class="cfg-field__label">Region segment</span>
                            <input class="cfg-field__input" type="text" placeholder="US"
                                   data-mqtt-region>
                        </label>
                        <label class="cfg-field">
                            <span class="cfg-field__label">Gateway ID (optional)</span>
                            <input class="cfg-field__input" type="text"
                                   placeholder="auto-derived if blank" data-mqtt-gateway>
                        </label>
                    </fieldset>
                    <fieldset class="cfg-fieldset">
                        <legend class="cfg-fieldset__legend">Privacy (gate 2)</legend>
                        <label class="cfg-field">
                            <span class="cfg-field__label">Publish channels</span>
                            <textarea class="cfg-field__input cfg-field__textarea"
                                      rows="4" data-mqtt-channels
                                      placeholder="One channel name per line"></textarea>
                            <span class="cfg-field__hint">Default public presets only on
                                community brokers. Add private names only on your own broker.</span>
                        </label>
                        <label class="cfg-field">
                            <span class="cfg-field__label">Location on MQTT</span>
                            <select class="cfg-field__input" data-mqtt-loc-precision>
                                <option value="exact">Exact coordinates</option>
                                <option value="approximate" data-approximate-option>Approximate</option>
                                <option value="none">None (strip from MQTT)</option>
                            </select>
                        </label>
                    </fieldset>
                    <fieldset class="cfg-fieldset">
                        <legend class="cfg-fieldset__legend">Formats</legend>
                        <label class="cfg-field cfg-field--toggle">
                            <input type="checkbox" data-mqtt-json>
                            <span class="cfg-field__label">Also publish JSON mirror
                                (<code>…/2/json/…</code>)</span>
                        </label>
                        <label class="cfg-field cfg-field--toggle">
                            <input type="checkbox" data-mqtt-ha>
                            <span class="cfg-field__label">Home Assistant auto-discovery</span>
                        </label>
                        <label class="cfg-field cfg-field--toggle">
                            <input type="checkbox" data-mqtt-tls>
                            <span class="cfg-field__label">Use TLS (mqtts)</span>
                        </label>
                    </fieldset>
                    <div class="cfg-preview" data-mqtt-previews>
                        <span class="cfg-preview__label">Example topics (LongFast gateway)</span>
                        <code class="cfg-preview__value" data-mqtt-preview-mt>--</code>
                        <code class="cfg-preview__value" data-mqtt-preview-mc>--</code>
                        <code class="cfg-preview__value" data-mqtt-preview-json style="display:none">--</code>
                    </div>
                    <div class="cfg-card__actions">
                        <button class="terminal-button terminal-button--primary" type="submit">
                            Save MQTT
                        </button>
                    </div>
                    <p class="cfg-status" data-mqtt-status aria-live="polite"></p>
                </form>
            </article>
        `;
        this._form = this._root.querySelector('[data-mqtt-form]');
        this._enabled = this._root.querySelector('[data-mqtt-enabled]');
        this._host = this._root.querySelector('[data-mqtt-host]');
        this._port = this._root.querySelector('[data-mqtt-port]');
        this._user = this._root.querySelector('[data-mqtt-user]');
        this._pass = this._root.querySelector('[data-mqtt-pass]');
        this._topicRoot = this._root.querySelector('[data-mqtt-topic-root]');
        this._region = this._root.querySelector('[data-mqtt-region]');
        this._gateway = this._root.querySelector('[data-mqtt-gateway]');
        this._channels = this._root.querySelector('[data-mqtt-channels]');
        this._locPrecision = this._root.querySelector('[data-mqtt-loc-precision]');
        this._json = this._root.querySelector('[data-mqtt-json]');
        this._ha = this._root.querySelector('[data-mqtt-ha]');
        this._tls = this._root.querySelector('[data-mqtt-tls]');
        this._previewMt = this._root.querySelector('[data-mqtt-preview-mt]');
        this._previewMc = this._root.querySelector('[data-mqtt-preview-mc]');
        this._previewJson = this._root.querySelector('[data-mqtt-preview-json]');
        this._statusEl = this._root.querySelector('[data-mqtt-status]');
        this._runtimeEl = this._root.querySelector('[data-mqtt-runtime]');
        this._runtimeText = this._root.querySelector('[data-mqtt-runtime-text]');

        this._pass.addEventListener('input', () => { this._passwordDirty = true; });
        this._json.addEventListener('change', () => this._renderPreviews());
        this._form.addEventListener('submit', (e) => this._onSubmit(e));
        ['input', 'change'].forEach((ev) => {
            this._form.addEventListener(ev, () => this._renderPreviews());
        });
        this._refreshApproximateOptionLabels();
        if (window.MeshpointDisplayUnits) {
            this._unsubDisplayUnits = window.MeshpointDisplayUnits.onChange(
                () => this._refreshApproximateOptionLabels(),
            );
        }
    }

    _refreshApproximateOptionLabels() {
        const Units = window.MeshpointDisplayUnits;
        if (!Units || !this._locPrecision) return;
        const opt = this._locPrecision.querySelector('option[value="approximate"]');
        if (opt) opt.textContent = Units.approximateLocationOptionLabel();
    }

    render(config) {
        const mqtt = (config && config.mqtt) || {};
        if (this._enabled) this._enabled.checked = !!mqtt.enabled;
        if (this._host) this._host.value = mqtt.broker_host || '';
        if (this._port) this._port.value = mqtt.broker_port ?? 1883;
        if (this._user) this._user.value = mqtt.username || '';
        if (this._pass) {
            this._pass.value = '';
            this._pass.placeholder = mqtt.password_set
                ? 'Leave blank to keep current password'
                : 'Broker password';
        }
        this._passwordDirty = false;
        if (this._topicRoot) this._topicRoot.value = mqtt.topic_root || 'msh';
        if (this._region) this._region.value = mqtt.region_segment || 'US';
        if (this._gateway) {
            const gid = mqtt.gateway_id || '';
            this._gateway.value = gid.startsWith('!') ? gid : gid;
        }
        if (this._channels) {
            const list = mqtt.publish_channels || ['LongFast', 'MeshCore'];
            this._channels.value = list.join('\n');
        }
        if (this._locPrecision) {
            this._locPrecision.value = mqtt.location_precision || 'exact';
        }
        if (this._json) this._json.checked = !!mqtt.publish_json;
        if (this._ha) this._ha.checked = !!mqtt.homeassistant_discovery;
        if (this._tls) this._tls.checked = !!mqtt.tls_enabled;
        this._renderPreviews(mqtt);
        this._refreshRuntime();
        this._startRuntimePolling();
    }

    _startRuntimePolling() {
        if (this._runtimeInterval) return;
        this._runtimeInterval = setInterval(() => {
            const section = document.querySelector('[data-section="configuration/mqtt"]');
            if (section && section.classList.contains('section--active')) {
                this._refreshRuntime();
            } else {
                clearInterval(this._runtimeInterval);
                this._runtimeInterval = null;
            }
        }, 10000);
    }

    async _refreshRuntime() {
        if (!this._runtimeEl) return;
        try {
            const res = await fetch('/api/config/mqtt/runtime');
            if (!res.ok) return;
            const data = await res.json();
            this._renderRuntime(data);
        } catch (_) {
            /* non-fatal */
        }
    }

    _renderRuntime(data) {
        if (!this._runtimeEl || !this._runtimeText) return;
        this._runtimeEl.hidden = false;
        this._runtimeEl.classList.remove(
            'mqtt-runtime--offline',
            'mqtt-runtime--disabled',
        );

        if (!data.config_enabled) {
            this._runtimeEl.classList.add('mqtt-runtime--disabled');
            this._runtimeText.textContent = 'MQTT disabled in config';
            return;
        }

        if (!data.publisher_active) {
            this._runtimeEl.classList.add('mqtt-runtime--offline');
            this._runtimeText.textContent =
                'Enabled but publisher not running (restart Meshpoint after save)';
            return;
        }

        const host = data.broker_host || 'broker';
        const port = data.broker_port ?? 1883;
        const prefix = data.topic_prefix || 'msh';
        const pub = data.publish_count ?? 0;
        const disc = data.disconnect_count ?? 0;

        if (!data.connected) {
            this._runtimeEl.classList.add('mqtt-runtime--offline');
            const rc = data.last_disconnect_rc ?? data.last_connect_rc;
            const rcLabel = rc != null ? ` · rc ${rc}` : '';
            this._runtimeText.textContent =
                `${host}:${port} · disconnected${rcLabel} · ${disc} drops · ${pub} published`;
            return;
        }

        const since = data.connected_since
            ? `since ${new Date(data.connected_since).toLocaleTimeString()}`
            : 'connected';
        const lastPub = data.last_publish_at
            ? ` · last pub ${new Date(data.last_publish_at).toLocaleTimeString()}`
            : '';
        this._runtimeText.textContent =
            `${host}:${port} · ${since} · ${prefix} · ${pub} published · ${disc} drops${lastPub}`;
    }

    _renderPreviews(cached) {
        const mqtt = cached || {};
        const mt = mqtt.topic_preview_meshtastic
            || this._exampleTopic('e', 'LongFast');
        const mc = mqtt.topic_preview_meshcore
            || this._exampleTopic('c', 'MeshCore');
        if (this._previewMt) this._previewMt.textContent = mt;
        if (this._previewMc) this._previewMc.textContent = mc;
        if (this._previewJson) {
            const show = this._json && this._json.checked;
            this._previewJson.style.display = show ? '' : 'none';
            if (show) {
                this._previewJson.textContent = mqtt.topic_preview_json
                    || this._exampleTopic('json', 'LongFast');
            }
        }
    }

    _exampleTopic(segment, channel) {
        const root = (this._topicRoot?.value || 'msh').trim() || 'msh';
        const region = (this._region?.value || 'US').trim() || 'US';
        const gw = (this._gateway?.value || '').trim().replace(/^!/, '') || 'xxxxxxxx';
        const gateway = gw.length === 8 ? `!${gw}` : '!xxxxxxxx';
        return `${root}/${region}/2/${segment}/${channel}/${gateway}`;
    }

    _parseChannels() {
        const raw = (this._channels?.value || '').split(/\r?\n/);
        const out = [];
        const seen = new Set();
        raw.forEach((line) => {
            const name = line.trim();
            if (!name) return;
            const key = name.toLowerCase();
            if (seen.has(key)) return;
            seen.add(key);
            out.push(name);
        });
        return out;
    }

    async _onSubmit(event) {
        event.preventDefault();
        const channels = this._parseChannels();
        if (!channels.length) {
            this._setStatus('error', 'Add at least one publish channel.');
            return;
        }
        const payload = {
            enabled: this._enabled.checked,
            broker_host: this._host.value.trim(),
            broker_port: Number(this._port.value),
            username: this._user.value.trim(),
            password_unchanged: !this._passwordDirty,
            topic_root: this._topicRoot.value.trim() || 'msh',
            region_segment: this._region.value.trim() || 'US',
            gateway_id: this._gateway.value.trim(),
            publish_channels: channels,
            publish_json: this._json.checked,
            location_precision: this._locPrecision.value,
            homeassistant_discovery: this._ha.checked,
            tls_enabled: this._tls ? this._tls.checked : false,
            tls_ca_cert: '',
        };
        if (this._passwordDirty) {
            payload.password = this._pass.value;
        }
        this._setStatus('pending', 'Saving…');
        const result = await this._api.put('/api/config/mqtt', payload);
        if (result) {
            this._setStatus('success', 'Saved.');
            this._passwordDirty = false;
            if (this._pass) this._pass.value = '';
            this._api.signalRestart('MQTT settings updated.');
            if (result.mqtt) this._renderPreviews(result.mqtt);
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
