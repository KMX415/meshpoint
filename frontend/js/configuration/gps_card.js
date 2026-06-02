/**
 * Configuration -> GPS card.
 *
 * Composes three smaller pieces:
 *   - GpsSkyplotView   (left half: SVG bullseye)
 *   - GpsStatsColumn   (right half: fix mode + coords + sats + DOP)
 *   - source switcher + per-source config form (below the skyplot)
 *
 * Lifecycle:
 *   - mount()       wires DOM and registers form/source-switch handlers
 *   - render(cfg)   seeds initial values from the config payload
 *   - polling       starts on first render() and runs only while
 *                   /api/device/gps-status reports a "live" source
 *                   (gpsd) or while the card is visible. Static sources
 *                   poll once per render to populate the lamp+coords;
 *                   no need for sub-second updates.
 */

class GpsConfigCard {
    constructor(api) {
        this._api = api;
        this._root = null;
        this._skyplot = new window.GpsSkyplotView();
        this._stats = new window.GpsStatsColumn();
        this._timer = null;
        this._currentSource = 'static';
    }

    mount(root) {
        this._root = root;
        this._root.innerHTML = `
            <article class="cfg-card gps-card">
                <header class="cfg-card__head">
                    <h3 class="cfg-card__title">GPS and placement</h3>
                    <p class="cfg-card__hint">
                        Live fix from gpsd (USB GPS), UART (RAK Pi HAT), or static
                        coordinates you enter manually. Used by the local map and
                        Meshradar fleet view.
                    </p>
                </header>

                <div class="gps-hero">
                    <div class="gps-hero__skyplot" data-skyplot></div>
                    <div class="gps-hero__stats" data-stats></div>
                </div>

                <form class="cfg-form gps-form" data-gps-form>
                    <fieldset class="cfg-fieldset">
                        <legend class="cfg-fieldset__legend">Source</legend>
                        <div class="gps-source-switch" role="radiogroup">
                            <label class="gps-source-chip">
                                <input type="radio" name="gps-source" value="static" checked>
                                <span>Static</span>
                            </label>
                            <label class="gps-source-chip">
                                <input type="radio" name="gps-source" value="gpsd">
                                <span>gpsd</span>
                            </label>
                            <label class="gps-source-chip">
                                <input type="radio" name="gps-source" value="uart">
                                <span>UART</span>
                            </label>
                        </div>
                        <p class="cfg-field__hint" data-source-hint></p>
                    </fieldset>

                    <fieldset class="cfg-fieldset" data-static-fields>
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
                        <label class="cfg-field">
                            <span class="cfg-field__label">Hardware description</span>
                            <input class="cfg-field__input" type="text" data-gps-hw-desc
                                   placeholder="RAK2287 + Raspberry Pi 4">
                        </label>
                    </fieldset>

                    <fieldset class="cfg-fieldset" data-gpsd-fields hidden>
                        <legend class="cfg-fieldset__legend">gpsd connection</legend>
                        <div class="cfg-row">
                            <label class="cfg-field">
                                <span class="cfg-field__label">Host</span>
                                <input class="cfg-field__input" type="text"
                                       data-gpsd-host placeholder="127.0.0.1">
                            </label>
                            <label class="cfg-field cfg-field--narrow">
                                <span class="cfg-field__label">Port</span>
                                <input class="cfg-field__input" type="number"
                                       min="1" max="65535"
                                       data-gpsd-port placeholder="2947">
                            </label>
                        </div>
                        <div class="cfg-row">
                            <label class="cfg-field cfg-field--narrow">
                                <span class="cfg-field__label">Update interval (s)</span>
                                <input class="cfg-field__input" type="number"
                                       min="1" max="300" data-gpsd-interval>
                            </label>
                            <label class="cfg-field cfg-field--narrow">
                                <span class="cfg-field__label">Min fix quality</span>
                                <select class="cfg-field__input" data-gpsd-quality>
                                    <option value="1">1 — accept any reading</option>
                                    <option value="2" selected>2 — require 2D fix</option>
                                    <option value="3">3 — require 3D fix</option>
                                </select>
                            </label>
                        </div>
                        <p class="cfg-field__hint">
                            Plug a USB GPS into the Pi. gpsd auto-detects the
                            device on hotplug. Skyplot updates as satellites
                            come into view.
                        </p>
                    </fieldset>

                    <fieldset class="cfg-fieldset" data-uart-fields hidden>
                        <legend class="cfg-fieldset__legend">UART (on-board GPS)</legend>
                        <div class="cfg-row">
                            <label class="cfg-field">
                                <span class="cfg-field__label">Serial device</span>
                                <input class="cfg-field__input" type="text"
                                       data-uart-path placeholder="/dev/ttyAMA0">
                            </label>
                            <label class="cfg-field cfg-field--narrow">
                                <span class="cfg-field__label">Baud</span>
                                <input class="cfg-field__input" type="number"
                                       min="4800" max="115200"
                                       data-uart-baud placeholder="9600">
                            </label>
                        </div>
                        <div class="cfg-row">
                            <label class="cfg-field cfg-field--narrow">
                                <span class="cfg-field__label">Update interval (s)</span>
                                <input class="cfg-field__input" type="number"
                                       min="1" max="300" data-uart-interval>
                            </label>
                            <label class="cfg-field cfg-field--narrow">
                                <span class="cfg-field__label">Min fix quality</span>
                                <select class="cfg-field__input" data-uart-quality>
                                    <option value="1">1 — accept any reading</option>
                                    <option value="2" selected>2 — require 2D fix</option>
                                    <option value="3">3 — require 3D fix</option>
                                </select>
                            </label>
                        </div>
                        <p class="cfg-field__hint">
                            RAK Pi HAT GPS on /dev/ttyAMA0 (install.sh enables UART).
                            Fix and satellite count update live; full skyplot needs gpsd.
                        </p>
                    </fieldset>

                    <div class="cfg-card__actions">
                        <button class="terminal-button terminal-button--primary" type="submit">
                            Save GPS settings
                        </button>
                    </div>
                    <p class="cfg-status" data-gps-status aria-live="polite"></p>
                </form>
            </article>
        `;

        this._skyplot.mount(this._root.querySelector('[data-skyplot]'));
        this._stats.mount(this._root.querySelector('[data-stats]'));
        this._form = this._root.querySelector('[data-gps-form]');
        this._statusEl = this._root.querySelector('[data-gps-status]');
        this._sourceHint = this._root.querySelector('[data-source-hint]');

        this._lat = this._root.querySelector('[data-gps-lat]');
        this._lng = this._root.querySelector('[data-gps-lng]');
        this._alt = this._root.querySelector('[data-gps-alt]');
        this._hwDesc = this._root.querySelector('[data-gps-hw-desc]');

        this._gpsdHost = this._root.querySelector('[data-gpsd-host]');
        this._gpsdPort = this._root.querySelector('[data-gpsd-port]');
        this._gpsdInterval = this._root.querySelector('[data-gpsd-interval]');
        this._gpsdQuality = this._root.querySelector('[data-gpsd-quality]');

        this._staticFields = this._root.querySelector('[data-static-fields]');
        this._gpsdFields = this._root.querySelector('[data-gpsd-fields]');
        this._uartFields = this._root.querySelector('[data-uart-fields]');
        this._uartPath = this._root.querySelector('[data-uart-path]');
        this._uartBaud = this._root.querySelector('[data-uart-baud]');
        this._uartInterval = this._root.querySelector('[data-uart-interval]');
        this._uartQuality = this._root.querySelector('[data-uart-quality]');

        this._form.addEventListener('submit', (e) => this._onSubmit(e));
        this._root.querySelectorAll('input[name="gps-source"]').forEach((radio) => {
            radio.addEventListener('change', () => this._onSourceChange(radio.value));
        });
    }

    render(config) {
        const device = (config && config.device) || {};
        const location = (config && config.location) || {};

        const source = (location.source || 'static').toLowerCase();
        this._currentSource = source;

        const radio = this._root.querySelector(`input[name="gps-source"][value="${source}"]`);
        if (radio) radio.checked = true;
        this._showFieldsetForSource(source);
        this._updateSourceHint(source);

        if (this._lat && device.latitude != null) this._lat.value = device.latitude;
        if (this._lng && device.longitude != null) this._lng.value = device.longitude;
        if (this._alt && device.altitude != null) this._alt.value = device.altitude;
        if (this._hwDesc) this._hwDesc.value = device.hardware_description || '';

        if (this._gpsdHost && location.gpsd_host) this._gpsdHost.value = location.gpsd_host;
        if (this._gpsdPort && location.gpsd_port) this._gpsdPort.value = location.gpsd_port;
        if (this._gpsdInterval && location.update_interval_seconds) {
            this._gpsdInterval.value = location.update_interval_seconds;
        }
        if (this._gpsdQuality && location.min_fix_quality) {
            this._gpsdQuality.value = String(location.min_fix_quality);
        }

        if (this._uartPath) {
            this._uartPath.value = location.uart_path || '/dev/ttyAMA0';
        }
        if (this._uartBaud) {
            this._uartBaud.value = location.uart_baud || 9600;
        }
        if (this._uartInterval && location.update_interval_seconds) {
            this._uartInterval.value = location.update_interval_seconds;
        }
        if (this._uartQuality && location.min_fix_quality) {
            this._uartQuality.value = String(location.min_fix_quality);
        }

        this._restartPolling(source);
    }

    destroy() {
        this._stopPolling();
    }

    _onSourceChange(value) {
        this._showFieldsetForSource(value);
        this._updateSourceHint(value);
    }

    _showFieldsetForSource(source) {
        if (!this._staticFields || !this._gpsdFields) return;
        const isStatic = source === 'static';
        const isGpsd = source === 'gpsd';
        const isUart = source === 'uart';
        this._staticFields.hidden = !isStatic;
        this._gpsdFields.hidden = !isGpsd;
        if (this._uartFields) this._uartFields.hidden = !isUart;
    }

    _updateSourceHint(source) {
        if (!this._sourceHint) return;
        if (source === 'gpsd') {
            this._sourceHint.textContent =
                'Live fixes from a running gpsd daemon. Switching to gpsd '
                + 'requires a service restart so the Meshpoint can attach '
                + 'to the daemon.';
        } else if (source === 'uart') {
            this._sourceHint.textContent =
                'Live NMEA from the on-board RAK Pi HAT GPS (/dev/ttyAMA0). '
                + 'Switching source requires a service restart.';
        } else {
            this._sourceHint.textContent =
                'Coordinates are entered manually and stay fixed until '
                + 'you change them.';
        }
    }

    _restartPolling(source) {
        this._stopPolling();
        const interval = (source === 'gpsd' || source === 'uart') ? 2000 : 30000;
        this._pollOnce();
        this._timer = window.setInterval(() => this._pollOnce(), interval);
    }

    _stopPolling() {
        if (this._timer) {
            window.clearInterval(this._timer);
            this._timer = null;
        }
    }

    async _pollOnce() {
        try {
            const status = await this._api.get('/api/device/gps-status');
            if (!status) return;
            this._stats.render(status);
            const sats = (status.satellites && status.satellites.list) || [];
            this._skyplot.render(sats);
        } catch (e) {
            // Network blip; let the next tick recover.
        }
    }

    async _onSubmit(event) {
        event.preventDefault();
        const source = this._selectedSource();
        this._setStatus('pending', 'Saving…');

        const payload = { source };
        if (source === 'static') {
            const lat = Number(this._lat.value);
            const lng = Number(this._lng.value);
            if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
                this._setStatus('error', 'Latitude and longitude are required.');
                return;
            }
            payload.latitude = lat;
            payload.longitude = lng;
            const altRaw = this._alt.value.trim();
            if (altRaw !== '') {
                const alt = Number(altRaw);
                if (Number.isFinite(alt)) payload.altitude = alt;
            }
        } else if (source === 'gpsd') {
            const host = this._gpsdHost.value.trim();
            if (host) payload.gpsd_host = host;
            const portRaw = this._gpsdPort.value.trim();
            if (portRaw) payload.gpsd_port = Number(portRaw);
            const intervalRaw = this._gpsdInterval.value.trim();
            if (intervalRaw) payload.update_interval_seconds = Number(intervalRaw);
            const qualityRaw = this._gpsdQuality.value;
            if (qualityRaw) payload.min_fix_quality = Number(qualityRaw);
        } else if (source === 'uart') {
            const path = this._uartPath.value.trim();
            if (path) payload.uart_path = path;
            const baudRaw = this._uartBaud.value.trim();
            if (baudRaw) payload.uart_baud = Number(baudRaw);
            const intervalRaw = this._uartInterval.value.trim();
            if (intervalRaw) payload.update_interval_seconds = Number(intervalRaw);
            const qualityRaw = this._uartQuality.value;
            if (qualityRaw) payload.min_fix_quality = Number(qualityRaw);
        }

        const gpsResult = await this._api.put('/api/config/gps', payload);
        if (!gpsResult) {
            this._setStatus('error', 'GPS settings save failed.');
            return;
        }

        if (source === 'static' && this._hwDesc) {
            const hwDesc = this._hwDesc.value.trim();
            const devResult = await this._api.put('/api/config/device', {
                hardware_description: hwDesc,
            });
            if (!devResult) {
                this._setStatus('error', 'Hardware description save failed.');
                return;
            }
        }

        this._setStatus('success', 'Saved.');
        if (gpsResult.restart_required) {
            this._api.signalRestart('GPS source changed.');
        }
        this._restartPolling(source);
    }

    _selectedSource() {
        const checked = this._root.querySelector('input[name="gps-source"]:checked');
        return checked ? checked.value : 'static';
    }

    _setStatus(kind, message) {
        if (!this._statusEl) return;
        this._statusEl.dataset.kind = kind;
        this._statusEl.textContent = message;
    }
}

window.GpsConfigCard = GpsConfigCard;
