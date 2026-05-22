/**
 * Configuration → Advanced card.
 *
 * Storage, relay tuning, radio spectral scan, MeshCore USB capture.
 */

class AdvancedConfigCard {
    constructor(api) {
        this._api = api;
        this._root = null;
    }

    mount(root) {
        this._root = root;
        this._root.innerHTML = `
            <div class="cfg-section" data-adv-root>
                <article class="cfg-card">
                    <header class="cfg-card__head">
                        <h3 class="cfg-card__title">Storage</h3>
                        <p class="cfg-card__hint">Local SQLite retention on the SD card.</p>
                    </header>
                    <form class="cfg-form" data-storage-form>
                        <label class="cfg-field">
                            <span class="cfg-field__label">Max packets retained</span>
                            <input class="cfg-field__input" type="number" min="1000"
                                   max="10000000" data-storage-max>
                        </label>
                        <label class="cfg-field">
                            <span class="cfg-field__label">Cleanup interval (seconds)</span>
                            <input class="cfg-field__input" type="number" min="60" max="86400"
                                   data-storage-cleanup>
                        </label>
                        <div class="cfg-card__actions">
                            <button class="terminal-button terminal-button--primary"
                                    type="submit">Save storage</button>
                        </div>
                        <p class="cfg-status" data-storage-status aria-live="polite"></p>
                    </form>
                </article>
                <article class="cfg-card">
                    <header class="cfg-card__head">
                        <h3 class="cfg-card__title">Relay (experimental)</h3>
                        <p class="cfg-card__hint">SX1262 relay path. Basic enable/rate also
                            on Transmit.</p>
                    </header>
                    <form class="cfg-form" data-relay-form>
                        <label class="cfg-field cfg-field--toggle">
                            <input type="checkbox" data-relay-enabled>
                            <span class="cfg-field__label">Relay enabled</span>
                        </label>
                        <label class="cfg-field">
                            <span class="cfg-field__label">Relay serial port</span>
                            <input class="cfg-field__input" type="text"
                                   placeholder="/dev/ttyACM1" data-relay-port>
                        </label>
                        <div class="cfg-row">
                            <label class="cfg-field cfg-field--narrow">
                                <span class="cfg-field__label">Serial baud</span>
                                <input class="cfg-field__input" type="number" data-relay-baud>
                            </label>
                            <label class="cfg-field cfg-field--narrow">
                                <span class="cfg-field__label">Max / minute</span>
                                <input class="cfg-field__input" type="number" data-relay-rate>
                            </label>
                            <label class="cfg-field cfg-field--narrow">
                                <span class="cfg-field__label">Burst size</span>
                                <input class="cfg-field__input" type="number" data-relay-burst>
                            </label>
                        </div>
                        <div class="cfg-row">
                            <label class="cfg-field">
                                <span class="cfg-field__label">Min relay RSSI (dBm)</span>
                                <input class="cfg-field__input" type="number" step="0.1"
                                       data-relay-min-rssi>
                            </label>
                            <label class="cfg-field">
                                <span class="cfg-field__label">Max relay RSSI (dBm)</span>
                                <input class="cfg-field__input" type="number" step="0.1"
                                       data-relay-max-rssi>
                            </label>
                        </div>
                        <div class="cfg-card__actions">
                            <button class="terminal-button terminal-button--primary"
                                    type="submit">Save relay</button>
                        </div>
                        <p class="cfg-status" data-relay-status aria-live="polite"></p>
                    </form>
                </article>
                <article class="cfg-card">
                    <header class="cfg-card__head">
                        <h3 class="cfg-card__title">Radio (advanced)</h3>
                        <p class="cfg-card__hint">Spectral scan and optional SX1261 SPI path.</p>
                    </header>
                    <form class="cfg-form" data-radio-adv-form>
                        <label class="cfg-field">
                            <span class="cfg-field__label">Spectral scan interval (s)</span>
                            <input class="cfg-field__input" type="number" min="0" max="3600"
                                   step="1" data-radio-scan-interval>
                            <span class="cfg-field__hint">0 disables hardware noise-floor scan.</span>
                        </label>
                        <label class="cfg-field">
                            <span class="cfg-field__label">SX1261 SPI path (optional)</span>
                            <input class="cfg-field__input" type="text"
                                   placeholder="/dev/spidev0.1 or empty" data-radio-sx1261>
                        </label>
                        <div class="cfg-card__actions">
                            <button class="terminal-button terminal-button--primary"
                                    type="submit">Save radio advanced</button>
                        </div>
                        <p class="cfg-status" data-radio-adv-status aria-live="polite"></p>
                    </form>
                </article>
                <article class="cfg-card">
                    <header class="cfg-card__head">
                        <h3 class="cfg-card__title">MeshCore USB capture</h3>
                        <p class="cfg-card__hint">Companion serial source (Heltec, T-Beam, etc.).</p>
                    </header>
                    <form class="cfg-form" data-mc-usb-form>
                        <label class="cfg-field cfg-field--toggle">
                            <input type="checkbox" data-mc-usb-enable>
                            <span class="cfg-field__label">Include meshcore_usb capture source</span>
                        </label>
                        <label class="cfg-field cfg-field--toggle">
                            <input type="checkbox" data-mc-usb-autodetect checked>
                            <span class="cfg-field__label">Auto-detect serial port</span>
                        </label>
                        <label class="cfg-field">
                            <span class="cfg-field__label">Pinned serial port</span>
                            <input class="cfg-field__input" type="text"
                                   placeholder="/dev/ttyACM0" data-mc-usb-port>
                        </label>
                        <label class="cfg-field cfg-field--narrow">
                            <span class="cfg-field__label">Baud rate</span>
                            <input class="cfg-field__input" type="number" data-mc-usb-baud>
                        </label>
                        <div class="cfg-card__actions">
                            <button class="terminal-button terminal-button--primary"
                                    type="submit">Save MeshCore USB</button>
                        </div>
                        <p class="cfg-status" data-mc-usb-status aria-live="polite"></p>
                    </form>
                </article>
            </div>
        `;
        this._storageForm = this._root.querySelector('[data-storage-form]');
        this._relayForm = this._root.querySelector('[data-relay-form]');
        this._radioAdvForm = this._root.querySelector('[data-radio-adv-form]');
        this._mcUsbForm = this._root.querySelector('[data-mc-usb-form]');
        this._storageForm.addEventListener('submit', (e) => this._saveStorage(e));
        this._relayForm.addEventListener('submit', (e) => this._saveRelay(e));
        this._radioAdvForm.addEventListener('submit', (e) => this._saveRadioAdv(e));
        this._mcUsbForm.addEventListener('submit', (e) => this._saveMcUsb(e));
    }

    render(config) {
        const storage = config.storage || {};
        const relay = config.relay || {};
        const radioAdv = config.radio_advanced || {};
        const cap = config.capture || {};
        const mcUsb = cap.meshcore_usb || {};

        this._setVal('[data-storage-max]', storage.max_packets_retained);
        this._setVal('[data-storage-cleanup]', storage.cleanup_interval_seconds);
        this._setChecked('[data-relay-enabled]', relay.enabled);
        this._setVal('[data-relay-port]', relay.serial_port || '');
        this._setVal('[data-relay-baud]', relay.serial_baud ?? 115200);
        this._setVal('[data-relay-rate]', relay.max_relay_per_minute);
        this._setVal('[data-relay-burst]', relay.burst_size);
        this._setVal('[data-relay-min-rssi]', relay.min_relay_rssi);
        this._setVal('[data-relay-max-rssi]', relay.max_relay_rssi);
        this._setVal('[data-radio-scan-interval]', radioAdv.spectral_scan_interval_seconds);
        this._setVal('[data-radio-sx1261]', radioAdv.sx1261_spi_path || '');
        const sources = cap.sources || [];
        this._setChecked('[data-mc-usb-enable]', sources.includes('meshcore_usb'));
        this._setChecked('[data-mc-usb-autodetect]', mcUsb.auto_detect !== false);
        this._setVal('[data-mc-usb-port]', mcUsb.serial_port || '');
        this._setVal('[data-mc-usb-baud]', mcUsb.baud_rate ?? 115200);
    }

    _setVal(sel, v) {
        const el = this._root.querySelector(sel);
        if (el && v != null) el.value = v;
    }

    _setChecked(sel, on) {
        const el = this._root.querySelector(sel);
        if (el) el.checked = !!on;
    }

    async _saveStorage(event) {
        event.preventDefault();
        const status = this._root.querySelector('[data-storage-status]');
        status.dataset.kind = 'pending';
        status.textContent = 'Saving…';
        const result = await this._api.put('/api/config/storage', {
            max_packets_retained: Number(
                this._root.querySelector('[data-storage-max]').value,
            ),
            cleanup_interval_seconds: Number(
                this._root.querySelector('[data-storage-cleanup]').value,
            ),
        });
        this._finish(status, result, 'Storage updated.');
    }

    async _saveRelay(event) {
        event.preventDefault();
        const status = this._root.querySelector('[data-relay-status]');
        status.dataset.kind = 'pending';
        status.textContent = 'Saving…';
        const result = await this._api.put('/api/config/relay', {
            enabled: this._root.querySelector('[data-relay-enabled]').checked,
            serial_port: this._root.querySelector('[data-relay-port]').value.trim(),
            serial_baud: Number(this._root.querySelector('[data-relay-baud]').value),
            max_relay_per_minute: Number(
                this._root.querySelector('[data-relay-rate]').value,
            ),
            burst_size: Number(this._root.querySelector('[data-relay-burst]').value),
            min_relay_rssi: Number(
                this._root.querySelector('[data-relay-min-rssi]').value,
            ),
            max_relay_rssi: Number(
                this._root.querySelector('[data-relay-max-rssi]').value,
            ),
        });
        this._finish(status, result, 'Relay updated.');
    }

    async _saveRadioAdv(event) {
        event.preventDefault();
        const status = this._root.querySelector('[data-radio-adv-status]');
        status.dataset.kind = 'pending';
        status.textContent = 'Saving…';
        const result = await this._api.put('/api/config/radio/advanced', {
            spectral_scan_interval_seconds: Number(
                this._root.querySelector('[data-radio-scan-interval]').value,
            ),
            sx1261_spi_path: this._root.querySelector('[data-radio-sx1261]').value.trim(),
        });
        this._finish(status, result, 'Radio advanced updated.');
    }

    async _saveMcUsb(event) {
        event.preventDefault();
        const status = this._root.querySelector('[data-mc-usb-status]');
        status.dataset.kind = 'pending';
        status.textContent = 'Saving…';
        const result = await this._api.put('/api/config/capture/meshcore-usb', {
            enable_source: this._root.querySelector('[data-mc-usb-enable]').checked,
            auto_detect: this._root.querySelector('[data-mc-usb-autodetect]').checked,
            serial_port: this._root.querySelector('[data-mc-usb-port]').value.trim(),
            baud_rate: Number(this._root.querySelector('[data-mc-usb-baud]').value),
        });
        this._finish(status, result, 'MeshCore USB updated.');
    }

    _finish(statusEl, result, restartMsg) {
        if (result) {
            statusEl.dataset.kind = 'success';
            statusEl.textContent = 'Saved.';
            if (result.restart_required) {
                this._api.signalRestart(restartMsg);
            } else {
                this._api.toast(restartMsg);
            }
            this._api.refresh();
        } else {
            statusEl.dataset.kind = 'error';
            statusEl.textContent = 'Save failed.';
        }
    }
}

window.AdvancedConfigCard = AdvancedConfigCard;
