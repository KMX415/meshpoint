/**
 * Configuration → GPS card.
 *
 * Single responsibility: edit the ``gps`` block in ``local.yaml``
 * (UART vs static toggle, baud rate, timeout). gpsd integration is
 * deferred to v0.7.5; the card surfaces a "coming soon" notice for
 * that capability so operators know to expect it in the next minor.
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
                    <h3 class="cfg-card__title">GPS</h3>
                    <p class="cfg-card__hint">Pick the location source. Static coords let you spoof a fixed position; UART reads from the on-board GPS.</p>
                </header>
                <form class="cfg-form" data-gps-form>
                    <fieldset class="cfg-fieldset">
                        <legend class="cfg-fieldset__legend">Source</legend>
                        <label class="cfg-field cfg-field--toggle">
                            <input type="radio" name="gps-source" value="uart" data-gps-source>
                            <span class="cfg-field__label">UART (built-in module)</span>
                        </label>
                        <label class="cfg-field cfg-field--toggle">
                            <input type="radio" name="gps-source" value="static" data-gps-source>
                            <span class="cfg-field__label">Static coordinates</span>
                        </label>
                    </fieldset>
                    <div class="cfg-row" data-gps-uart-row>
                        <label class="cfg-field">
                            <span class="cfg-field__label">UART baud</span>
                            <input class="cfg-field__input" type="number" min="9600" max="115200" step="2400" data-gps-baud>
                        </label>
                        <label class="cfg-field cfg-field--narrow">
                            <span class="cfg-field__label">Fix timeout (s)</span>
                            <input class="cfg-field__input" type="number" min="1" max="3600" data-gps-timeout>
                        </label>
                    </div>
                    <div class="cfg-row" data-gps-static-row style="display:none">
                        <label class="cfg-field">
                            <span class="cfg-field__label">Latitude</span>
                            <input class="cfg-field__input" type="number" step="0.000001" data-gps-lat>
                        </label>
                        <label class="cfg-field">
                            <span class="cfg-field__label">Longitude</span>
                            <input class="cfg-field__input" type="number" step="0.000001" data-gps-lng>
                        </label>
                    </div>
                    <p class="cfg-note">Native gpsd integration is planned for v0.7.5.</p>
                    <div class="cfg-card__actions">
                        <button class="terminal-button terminal-button--primary" type="submit">Save GPS</button>
                    </div>
                    <p class="cfg-status" data-gps-status aria-live="polite"></p>
                </form>
            </article>
        `;
        this._form = this._root.querySelector('[data-gps-form]');
        this._sourceInputs = Array.from(this._root.querySelectorAll('[data-gps-source]'));
        this._uartRow = this._root.querySelector('[data-gps-uart-row]');
        this._staticRow = this._root.querySelector('[data-gps-static-row]');
        this._baud = this._root.querySelector('[data-gps-baud]');
        this._timeout = this._root.querySelector('[data-gps-timeout]');
        this._lat = this._root.querySelector('[data-gps-lat]');
        this._lng = this._root.querySelector('[data-gps-lng]');
        this._statusEl = this._root.querySelector('[data-gps-status]');

        this._sourceInputs.forEach((el) => {
            el.addEventListener('change', () => this._toggleRows());
        });
        this._form.addEventListener('submit', (e) => this._onSubmit(e));
    }

    render(config) {
        const gps = (config && config.gps) || {};
        const source = gps.source || 'uart';
        this._sourceInputs.forEach((el) => {
            el.checked = el.value === source;
        });
        if (this._baud && gps.baud != null) this._baud.value = gps.baud;
        if (this._timeout && gps.timeout_seconds != null) this._timeout.value = gps.timeout_seconds;
        const device = (config && config.device) || {};
        if (this._lat && device.latitude != null) this._lat.value = device.latitude;
        if (this._lng && device.longitude != null) this._lng.value = device.longitude;
        this._toggleRows();
    }

    _toggleRows() {
        const checked = this._sourceInputs.find((el) => el.checked);
        const source = checked ? checked.value : 'uart';
        if (this._uartRow) this._uartRow.style.display = source === 'uart' ? '' : 'none';
        if (this._staticRow) this._staticRow.style.display = source === 'static' ? '' : 'none';
    }

    async _onSubmit(event) {
        event.preventDefault();
        const checked = this._sourceInputs.find((el) => el.checked);
        const source = checked ? checked.value : 'uart';
        const payload = { source };
        if (source === 'uart') {
            payload.baud = Number(this._baud.value);
            payload.timeout_seconds = Number(this._timeout.value);
        } else {
            payload.latitude = Number(this._lat.value);
            payload.longitude = Number(this._lng.value);
        }
        this._setStatus('pending', 'Saving…');
        const result = await this._api.put('/api/config/gps', payload);
        if (result) {
            this._setStatus('success', 'Saved.');
            this._api.signalRestart('GPS source updated.');
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
