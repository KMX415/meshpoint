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
        this._unsubDisplayUnits = null;
    }

    mount(root) {
        this._root = root;
        this._root.innerHTML = `
            <article class="cfg-card gps-card">
                <header class="cfg-card__head">
                    <h3 class="cfg-card__title">GPS and placement</h3>
                    <p class="cfg-card__hint">
                        Registered coordinates go to Meshradar. Choose whether
                        the LoRa mesh hears your registered pin or a live GPS
                        fix, with optional privacy rounding on live.
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
                        <legend class="cfg-fieldset__legend">Registered coordinates</legend>
                        <p class="cfg-field__hint">
                            Meshradar fleet pin. Also used on the mesh when
                            mesh position source is Registered below.
                        </p>
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

                    <fieldset class="cfg-fieldset" data-mesh-position-fields>
                        <legend class="cfg-fieldset__legend">Mesh position broadcasts</legend>
                        <p class="cfg-field__hint">
                            Coordinates sent as Meshtastic POSITION packets on
                            the LoRa mesh (Meshtastic app map).
                        </p>
                        <div class="gps-source-switch" role="radiogroup">
                            <label class="gps-source-chip">
                                <input type="radio" name="mesh-coord-source"
                                       value="static" checked>
                                <span>Registered pin</span>
                            </label>
                            <label class="gps-source-chip" data-mesh-live-chip>
                                <input type="radio" name="mesh-coord-source"
                                       value="live">
                                <span>Live GPS</span>
                            </label>
                        </div>
                        <label class="cfg-field" data-mesh-precision-wrap hidden>
                            <span class="cfg-field__label">Live GPS privacy</span>
                            <select class="cfg-field__input" data-mesh-precision>
                                <option value="approximate" data-approximate-option>Approximate</option>
                                <option value="exact">Precise</option>
                                <option value="none">Hidden (no position on mesh)</option>
                            </select>
                        </label>
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
        this._meshLiveChip = this._root.querySelector('[data-mesh-live-chip]');
        this._meshPrecisionWrap = this._root.querySelector('[data-mesh-precision-wrap]');
        this._meshPrecision = this._root.querySelector('[data-mesh-precision]');

        this._form.addEventListener('submit', (e) => this._onSubmit(e));
        this._root.querySelectorAll('input[name="gps-source"]').forEach((radio) => {
            radio.addEventListener('change', () => this._onSourceChange(radio.value));
        });
        this._root.querySelectorAll('input[name="mesh-coord-source"]').forEach((radio) => {
            radio.addEventListener('change', () => this._onMeshSourceChange(radio.value));
        });
        this._refreshApproximateOptionLabels();
        if (window.MeshpointDisplayUnits) {
            this._unsubDisplayUnits = window.MeshpointDisplayUnits.onChange(
                () => this._refreshApproximateOptionLabels(),
            );
        }
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

        const position = (config && config.transmit && config.transmit.position) || {};
        const meshSource = (position.coordinate_source || 'static').toLowerCase();
        const meshRadio = this._root.querySelector(
            `input[name="mesh-coord-source"][value="${meshSource}"]`,
        );
        if (meshRadio) meshRadio.checked = true;
        if (this._meshPrecision && position.location_precision) {
            this._meshPrecision.value = position.location_precision;
        }
        this._updateMeshControls(source, meshSource);

        this._restartPolling(source);
    }

    destroy() {
        this._stopPolling();
        if (this._unsubDisplayUnits) {
            this._unsubDisplayUnits();
            this._unsubDisplayUnits = null;
        }
    }

    _refreshApproximateOptionLabels() {
        const Units = window.MeshpointDisplayUnits;
        if (!Units || !this._meshPrecision) return;
        const opt = this._meshPrecision.querySelector('option[value="approximate"]');
        if (opt) opt.textContent = Units.approximateLocationOptionLabel();
    }

    _onSourceChange(value) {
        this._showFieldsetForSource(value);
        this._updateSourceHint(value);
        this._updateMeshControls(value, this._selectedMeshSource());
    }

    _onMeshSourceChange(value) {
        this._updateMeshControls(this._selectedSource(), value);
    }

    _selectedMeshSource() {
        const checked = this._root.querySelector('input[name="mesh-coord-source"]:checked');
        return checked ? checked.value : 'static';
    }

    _updateMeshControls(gpsSource, meshSource) {
        const liveAvailable = gpsSource === 'gpsd' || gpsSource === 'uart';
        if (this._meshLiveChip) {
            this._meshLiveChip.classList.toggle('gps-source-chip--disabled', !liveAvailable);
            const liveInput = this._meshLiveChip.querySelector('input');
            if (liveInput) liveInput.disabled = !liveAvailable;
        }
        if (!liveAvailable && meshSource === 'live') {
            const staticRadio = this._root.querySelector(
                'input[name="mesh-coord-source"][value="static"]',
            );
            if (staticRadio) staticRadio.checked = true;
            meshSource = 'static';
        }
        if (this._meshPrecisionWrap) {
            this._meshPrecisionWrap.hidden = meshSource !== 'live';
        }
    }

    _showFieldsetForSource(source) {
        if (!this._staticFields || !this._gpsdFields) return;
        const isGpsd = source === 'gpsd';
        this._staticFields.hidden = false;
        this._gpsdFields.hidden = !isGpsd;
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
                'Reserved for the on-board RAK Pi HAT GPS module. Not yet '
                + 'wired in v0.7.5; falls back to the static coordinates '
                + 'on save.';
        } else {
            this._sourceHint.textContent =
                'Coordinates are entered manually and stay fixed until '
                + 'you change them.';
        }
    }

    _restartPolling(source) {
        this._stopPolling();
        const interval = source === 'gpsd' ? 2000 : 30000;
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
        const lat = Number(this._lat.value);
        const lng = Number(this._lng.value);
        if (Number.isFinite(lat) && Number.isFinite(lng)) {
            payload.latitude = lat;
            payload.longitude = lng;
        } else if (source === 'static') {
            this._setStatus('error', 'Latitude and longitude are required.');
            return;
        }
        const altRaw = this._alt.value.trim();
        if (altRaw !== '') {
            const alt = Number(altRaw);
            if (Number.isFinite(alt)) payload.altitude = alt;
        }

        payload.mesh_coordinate_source = this._selectedMeshSource();
        if (this._meshPrecision) {
            payload.mesh_location_precision = this._meshPrecision.value;
        }

        if (source === 'gpsd') {
            const host = this._gpsdHost.value.trim();
            if (host) payload.gpsd_host = host;
            const portRaw = this._gpsdPort.value.trim();
            if (portRaw) payload.gpsd_port = Number(portRaw);
            const intervalRaw = this._gpsdInterval.value.trim();
            if (intervalRaw) payload.update_interval_seconds = Number(intervalRaw);
            const qualityRaw = this._gpsdQuality.value;
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
