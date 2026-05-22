/**
 * Configuration → GPS / device placement card.
 *
 * Static map coordinates and device metadata for Meshradar and the
 * local dashboard. Live UART GPS uses the on-board module automatically.
 */

class GpsConfigCard {
    constructor(api) {
        this._api = api;
        this._root = null;
    }

    mount(root) {
        this._root = root;
        this._root.innerHTML = `
            <article class="cfg-card">
                <header class="cfg-card__head">
                    <h3 class="cfg-card__title">GPS and placement</h3>
                    <p class="cfg-card__hint">
                        Coordinates used on the local map and Meshradar fleet view.
                        For a fixed install, use static coordinates. The on-board GPS
                        module is used when you run setup with a live fix.
                    </p>
                </header>
                <form class="cfg-form" data-gps-form>
                    <label class="cfg-field">
                        <span class="cfg-field__label">Device name</span>
                        <input class="cfg-field__input" type="text" maxlength="64"
                               data-gps-device-name>
                    </label>
                    <label class="cfg-field">
                        <span class="cfg-field__label">Hardware description</span>
                        <input class="cfg-field__input" type="text" data-gps-hw-desc
                               placeholder="RAK2287 + Raspberry Pi 4">
                    </label>
                    <fieldset class="cfg-fieldset">
                        <legend class="cfg-fieldset__legend">Static coordinates</legend>
                        <div class="cfg-row">
                            <label class="cfg-field">
                                <span class="cfg-field__label">Latitude</span>
                                <input class="cfg-field__input" type="number" step="0.000001"
                                       data-gps-lat>
                            </label>
                            <label class="cfg-field">
                                <span class="cfg-field__label">Longitude</span>
                                <input class="cfg-field__input" type="number" step="0.000001"
                                       data-gps-lng>
                            </label>
                            <label class="cfg-field cfg-field--narrow">
                                <span class="cfg-field__label">Altitude (m)</span>
                                <input class="cfg-field__input" type="number" step="0.1"
                                       data-gps-alt>
                            </label>
                        </div>
                    </fieldset>
                    <p class="cfg-note">Native gpsd integration is planned for a future release.</p>
                    <div class="cfg-card__actions">
                        <button class="terminal-button terminal-button--primary" type="submit">
                            Save placement
                        </button>
                    </div>
                    <p class="cfg-status" data-gps-status aria-live="polite"></p>
                </form>
            </article>
        `;
        this._form = this._root.querySelector('[data-gps-form]');
        this._deviceName = this._root.querySelector('[data-gps-device-name]');
        this._hwDesc = this._root.querySelector('[data-gps-hw-desc]');
        this._lat = this._root.querySelector('[data-gps-lat]');
        this._lng = this._root.querySelector('[data-gps-lng]');
        this._alt = this._root.querySelector('[data-gps-alt]');
        this._statusEl = this._root.querySelector('[data-gps-status]');
        this._form.addEventListener('submit', (e) => this._onSubmit(e));
    }

    render(config) {
        const device = (config && config.device) || {};
        if (this._deviceName) this._deviceName.value = device.device_name || '';
        if (this._hwDesc) this._hwDesc.value = device.hardware_description || '';
        if (this._lat && device.latitude != null) this._lat.value = device.latitude;
        if (this._lng && device.longitude != null) this._lng.value = device.longitude;
        if (this._alt && device.altitude != null) this._alt.value = device.altitude;
    }

    async _onSubmit(event) {
        event.preventDefault();
        const lat = Number(this._lat.value);
        const lng = Number(this._lng.value);
        if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
            this._setStatus('error', 'Latitude and longitude are required.');
            return;
        }
        const payload = {
            device_name: this._deviceName.value.trim(),
            hardware_description: this._hwDesc.value.trim(),
            latitude: lat,
            longitude: lng,
            altitude: Number(this._alt.value),
        };
        this._setStatus('pending', 'Saving…');
        const result = await this._api.put('/api/config/device', payload);
        if (result) {
            this._setStatus('success', 'Saved.');
            this._api.signalRestart('Device placement updated.');
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

window.GpsConfigCard = GpsConfigCard;
