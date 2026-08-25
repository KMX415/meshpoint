/**
 * Live Modem / Other settings for one Meshtastic USB node.
 * Credit: javastraat/meshpoint 9bfbe56 / 9e06352 / 4a6055c / ec0c410
 */

class SerialRadioControls {
    static _REGION_CODES = [
        'US', 'EU_433', 'EU_868', 'CN', 'JP', 'ANZ', 'KR', 'TW', 'RU', 'IN',
        'NZ_865', 'TH', 'LORA_24', 'UA_433', 'MY_433', 'MY_919', 'SG_923',
        'PH_433', 'PH_868', 'PH_915', 'ANZ_433', 'KZ_433', 'KZ_863', 'NP_865',
        'BR_902', 'ITU1_2M', 'ITU2_2M', 'EU_866', 'EU_874', 'EU_917', 'EU_N_868',
        'ITU3_2M', 'ITU1_70CM', 'ITU2_70CM', 'ITU3_70CM', 'ITU2_125CM',
    ];

    static _MODEM_PRESETS = [
        { value: 'LONG_FAST', label: 'LongFast' },
        { value: 'LONG_TURBO', label: 'LongTurbo' },
        { value: 'LONG_MODERATE', label: 'LongModerate' },
        { value: 'LONG_SLOW', label: 'LongSlow' },
        { value: 'VERY_LONG_SLOW', label: 'VeryLongSlow' },
        { value: 'MEDIUM_FAST', label: 'MediumFast' },
        { value: 'MEDIUM_SLOW', label: 'MediumSlow' },
        { value: 'SHORT_FAST', label: 'ShortFast' },
        { value: 'SHORT_SLOW', label: 'ShortSlow' },
        { value: 'SHORT_TURBO', label: 'ShortTurbo' },
    ];

    static _INTERVAL_PRESETS = [
        { minutes: 0, label: 'Off', off: true },
        { minutes: 5, label: '5m' },
        { minutes: 30, label: '30m' },
        { minutes: 60, label: '1h' },
        { minutes: 180, label: '3h' },
        { minutes: 360, label: '6h' },
        { minutes: 720, label: '12h' },
        { minutes: 1440, label: '24h' },
    ];

    constructor(api) {
        this._api = api;
    }

    mount(host, label, live) {
        if (!host) return;
        if (!live || !live.connected) {
            host.innerHTML = '';
            return;
        }
        host.innerHTML = this._html(label, live);
        this._wire(host, label, live);
    }

    _html(label, live) {
        const region = live.region || '';
        const regionOptions = SerialRadioControls._REGION_CODES.map((r) => (
            `<option value="${r}" ${r === region ? 'selected' : ''}>${r.replace(/_/g, ' ')}</option>`
        )).join('');
        const btEnabled = live.bluetooth_enabled !== false;
        const btMode = live.bluetooth_mode || 'RANDOM_PIN';
        const btModeOptions = [
            ['RANDOM_PIN', 'Random PIN (shown on device)'],
            ['FIXED_PIN', 'Fixed PIN (set your own)'],
            ['NO_PIN', 'No PIN'],
        ].map(([value, text]) => (
            `<option value="${value}" ${value === btMode ? 'selected' : ''}>${text}</option>`
        )).join('');
        const unsetHint = (!region || region === 'UNSET')
            ? `<p class="cfg-field__hint">Region is UNSET: node will not TX until set.</p>`
            : '';

        return `
            <div class="cfg-card" data-serial-modem>
                <header class="cfg-card__head">
                    <h3 class="cfg-card__title">Modem settings</h3>
                    <p class="cfg-card__hint">
                        Region and modem preset for this node, over its live serial connection.
                    </p>
                </header>
                <div class="cfg-form">
                    <label class="cfg-field cfg-field--narrow">
                        <span class="cfg-field__label">Region</span>
                        <select class="cfg-field__input" data-serial-region>
                            <option value="" disabled ${region ? '' : 'selected'}>-- select --</option>
                            ${regionOptions}
                        </select>
                        ${unsetHint}
                    </label>
                    <div class="cfg-card__actions">
                        <button class="terminal-button terminal-button--primary"
                                type="button" data-serial-region-save>Set Region</button>
                    </div>
                    <p class="cfg-status" data-serial-region-status aria-live="polite"></p>
                    <label class="cfg-field">
                        <span class="cfg-field__label">Modem preset</span>
                        <div class="cfg-chip-row" data-serial-preset-chips></div>
                    </label>
                    <div class="cfg-card__actions">
                        <button class="terminal-button terminal-button--primary"
                                type="button" data-serial-preset-save>Set Preset</button>
                    </div>
                    <p class="cfg-status" data-serial-preset-status aria-live="polite"></p>
                </div>
            </div>
            <div class="cfg-card" data-serial-other>
                <header class="cfg-card__head">
                    <h3 class="cfg-card__title">Other settings</h3>
                    <p class="cfg-card__hint">
                        NodeInfo / telemetry cadence and Bluetooth for this USB node. Device NVS only.
                    </p>
                </header>
                <div class="cfg-form">
                    <label class="cfg-field">
                        <span class="cfg-field__label">NodeInfo interval</span>
                        <div class="cfg-chip-row" data-serial-ni-chips></div>
                        <input class="cfg-field__input cfg-field__input--narrow" type="number"
                               min="0" max="1440" placeholder="minutes"
                               data-serial-ni-input>
                    </label>
                    <label class="cfg-field">
                        <span class="cfg-field__label">Telemetry interval</span>
                        <div class="cfg-chip-row" data-serial-tel-chips></div>
                        <input class="cfg-field__input cfg-field__input--narrow" type="number"
                               min="0" max="1440" placeholder="minutes"
                               data-serial-tel-input>
                    </label>
                    <div class="cfg-card__actions">
                        <button class="terminal-button terminal-button--primary"
                                type="button" data-serial-intervals-save>Set Intervals</button>
                    </div>
                    <p class="cfg-status" data-serial-intervals-status aria-live="polite"></p>
                    <label class="cfg-field cfg-field--toggle">
                        <input type="checkbox" data-serial-bt-enable ${btEnabled ? 'checked' : ''}>
                        <span class="cfg-field__label">Bluetooth enabled</span>
                    </label>
                    <label class="cfg-field">
                        <span class="cfg-field__label">Pairing mode</span>
                        <select class="cfg-field__input" data-serial-bt-mode>
                            ${btModeOptions}
                        </select>
                    </label>
                    <label class="cfg-field cfg-field--narrow">
                        <span class="cfg-field__label">Fixed PIN</span>
                        <input class="cfg-field__input" type="number" min="0" max="999999"
                               placeholder="000000" data-serial-bt-pin>
                    </label>
                    <div class="cfg-card__actions">
                        <button class="terminal-button terminal-button--primary"
                                type="button" data-serial-bt-save>Set Bluetooth</button>
                    </div>
                    <p class="cfg-status" data-serial-bt-status aria-live="polite"></p>
                </div>
            </div>
        `;
    }

    _wire(host, label, live) {
        this._wirePresetChips(host, live && live.modem_preset);
        this._wireIntervalChips(
            host, '[data-serial-ni-chips]', '[data-serial-ni-input]',
            live && live.node_info_broadcast_secs,
        );
        this._wireIntervalChips(
            host, '[data-serial-tel-chips]', '[data-serial-tel-input]',
            live && live.telemetry_device_update_interval,
        );

        host.querySelector('[data-serial-region-save]')
            .addEventListener('click', () => this._saveRegion(host, label));
        host.querySelector('[data-serial-preset-save]')
            .addEventListener('click', () => this._savePreset(host, label));
        host.querySelector('[data-serial-intervals-save]')
            .addEventListener('click', () => this._saveIntervals(host, label));
        host.querySelector('[data-serial-bt-save]')
            .addEventListener('click', () => this._saveBluetooth(host, label));
    }

    _wirePresetChips(host, current) {
        const chips = host.querySelector('[data-serial-preset-chips]');
        chips.innerHTML = SerialRadioControls._MODEM_PRESETS.map((p) => (
            `<button type="button" class="cfg-chip" data-preset="${p.value}">${p.label}</button>`
        )).join('');
        chips.querySelectorAll('[data-preset]').forEach((chip) => {
            chip.classList.toggle('cfg-chip--selected', chip.dataset.preset === current);
            chip.addEventListener('click', () => {
                chips.querySelectorAll('[data-preset]').forEach((c) => (
                    c.classList.toggle('cfg-chip--selected', c === chip)
                ));
            });
        });
    }

    _wireIntervalChips(host, chipsSel, inputSel, currentSecs) {
        const chipsEl = host.querySelector(chipsSel);
        const inputEl = host.querySelector(inputSel);
        chipsEl.innerHTML = SerialRadioControls._INTERVAL_PRESETS.map((p) => {
            const offCls = p.off ? ' cfg-chip--off' : '';
            return `<button type="button" class="cfg-chip${offCls}"
                    data-minutes="${p.minutes}">${p.label}</button>`;
        }).join('');
        const currentMinutes = currentSecs != null
            ? Math.round(Number(currentSecs) / 60) : null;
        if (currentMinutes != null) inputEl.value = String(currentMinutes);

        const setActive = (minutes) => {
            chipsEl.querySelectorAll('[data-minutes]').forEach((chip) => {
                chip.classList.toggle(
                    'cfg-chip--selected',
                    parseInt(chip.dataset.minutes, 10) === minutes,
                );
            });
        };
        setActive(currentMinutes);
        chipsEl.querySelectorAll('[data-minutes]').forEach((chip) => {
            chip.addEventListener('click', () => {
                const minutes = parseInt(chip.dataset.minutes, 10);
                inputEl.value = String(minutes);
                setActive(minutes);
            });
        });
        inputEl.addEventListener('input', () => {
            const minutes = parseInt(inputEl.value, 10);
            setActive(Number.isFinite(minutes) ? minutes : null);
        });
    }

    async _saveRegion(host, label) {
        const status = host.querySelector('[data-serial-region-status]');
        const region = (host.querySelector('[data-serial-region]').value || '').trim();
        if (!region) {
            status.dataset.kind = 'error';
            status.textContent = 'Pick a region.';
            return;
        }
        status.dataset.kind = 'pending';
        status.textContent = 'Setting region…';
        const result = await this._api.put('/api/config/serial/region', { label, region });
        if (result && result.success) {
            status.dataset.kind = 'success';
            status.textContent = `Region set to ${result.region}.`;
            this._api.toast(`Serial region → ${result.region}`);
            await this._api.refresh();
        } else {
            status.dataset.kind = 'error';
            status.textContent = 'Region update failed.';
        }
    }

    async _savePreset(host, label) {
        const status = host.querySelector('[data-serial-preset-status]');
        const selected = host.querySelector(
            '[data-serial-preset-chips] .cfg-chip--selected',
        );
        if (!selected) {
            status.dataset.kind = 'error';
            status.textContent = 'Pick a modem preset.';
            return;
        }
        const modem_preset = selected.dataset.preset;
        status.dataset.kind = 'pending';
        status.textContent = 'Setting preset…';
        const result = await this._api.put('/api/config/serial/modem-preset', {
            label, modem_preset,
        });
        if (result && result.success) {
            status.dataset.kind = 'success';
            status.textContent = `Preset set to ${result.modem_preset}.`;
            this._api.toast(`Serial preset → ${result.modem_preset}`);
            await this._api.refresh();
        } else {
            status.dataset.kind = 'error';
            status.textContent = 'Preset update failed.';
        }
    }

    async _saveIntervals(host, label) {
        const status = host.querySelector('[data-serial-intervals-status]');
        const niMin = parseInt(host.querySelector('[data-serial-ni-input]').value, 10);
        const telMin = parseInt(host.querySelector('[data-serial-tel-input]').value, 10);
        const body = { label };
        if (Number.isFinite(niMin)) body.node_info_broadcast_secs = niMin * 60;
        if (Number.isFinite(telMin)) body.telemetry_device_update_interval = telMin * 60;
        if (
            body.node_info_broadcast_secs == null
            && body.telemetry_device_update_interval == null
        ) {
            status.dataset.kind = 'error';
            status.textContent = 'Enter at least one interval.';
            return;
        }
        status.dataset.kind = 'pending';
        status.textContent = 'Setting intervals…';
        const result = await this._api.put(
            '/api/config/serial/broadcast-intervals', body,
        );
        if (result && result.success) {
            status.dataset.kind = 'success';
            status.textContent = 'Intervals updated.';
            this._api.toast('Serial broadcast intervals updated');
            await this._api.refresh();
        } else {
            status.dataset.kind = 'error';
            status.textContent = 'Interval update failed.';
        }
    }

    async _saveBluetooth(host, label) {
        const status = host.querySelector('[data-serial-bt-status]');
        const enabled = host.querySelector('[data-serial-bt-enable]').checked;
        const mode = host.querySelector('[data-serial-bt-mode]').value;
        const pinRaw = host.querySelector('[data-serial-bt-pin]').value;
        const body = { label, enabled, mode };
        if (pinRaw !== '') {
            const pin = parseInt(pinRaw, 10);
            if (!Number.isFinite(pin)) {
                status.dataset.kind = 'error';
                status.textContent = 'PIN must be a number.';
                return;
            }
            body.fixed_pin = pin;
        }
        status.dataset.kind = 'pending';
        status.textContent = 'Setting Bluetooth…';
        const result = await this._api.put('/api/config/serial/bluetooth', body);
        if (result && result.success) {
            status.dataset.kind = 'success';
            status.textContent = 'Bluetooth updated.';
            this._api.toast('Serial Bluetooth updated');
            await this._api.refresh();
        } else {
            status.dataset.kind = 'error';
            status.textContent = 'Bluetooth update failed.';
        }
    }
}

window.SerialRadioControls = SerialRadioControls;
