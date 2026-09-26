/**
 * Configuration → MeshCore radio preset picker.
 *
 * Applies community presets over the live USB connection
 * (PUT /api/config/meshcore/companion-radio). Credit: javastraat 471d572.
 */

class MeshcoreRadioSettings {
    /** Keep in sync with REGION_PRESETS in meshcore_radio_config.py */
    static _RADIO_PRESETS = [
        { value: 'AUSTRALIA', label: 'Australia (915.800 MHz / BW250 / SF10 / CR5)' },
        { value: 'AUSTRALIA_NARROW', label: 'Australia (Narrow) (916.575 MHz / BW62.5 / SF7 / CR8)' },
        { value: 'AUSTRALIA_MID', label: 'Australia (Mid) (915.075 MHz / BW125 / SF9 / CR5)' },
        { value: 'AUSTRALIA_SA_WA', label: 'Australia: SA, WA (923.125 MHz / BW62.5 / SF8 / CR8)' },
        { value: 'AUSTRALIA_QLD', label: 'Australia: QLD (923.125 MHz / BW62.5 / SF8 / CR5)' },
        { value: 'BRAZIL', label: 'Brazil (923.125 MHz / BW62.5 / SF8 / CR8)' },
        { value: 'CZECH_NARROW', label: 'Czech Republic (Narrow) (869.432 MHz / BW62.5 / SF7 / CR5)' },
        { value: 'EU_433_LONG_RANGE', label: 'EU 433MHz (Long Range) (433.650 MHz / BW250 / SF11 / CR5)' },
        { value: 'EU_433_NARROW', label: 'EU 433MHz (Narrow) (433.650 MHz / BW62.5 / SF8 / CR8)' },
        { value: 'EU_UK_NARROW', label: 'EU/UK (Narrow) (869.618 MHz / BW62.5 / SF8 / CR8)' },
        { value: 'EU_UK_DEPRECATED', label: 'EU/UK (Deprecated) (869.525 MHz / BW250 / SF11 / CR5)' },
        { value: 'NETHERLANDS', label: 'Netherlands (869.618 MHz / BW62.5 / SF7 / CR5)' },
        { value: 'NEW_ZEALAND', label: 'New Zealand (917.375 MHz / BW250 / SF11 / CR5)' },
        { value: 'NEW_ZEALAND_NARROW', label: 'New Zealand (Narrow) (917.375 MHz / BW62.5 / SF7 / CR5)' },
        { value: 'PORTUGAL_433', label: 'Portugal 433 (433.375 MHz / BW62.5 / SF9 / CR6)' },
        { value: 'PORTUGAL_868', label: 'Portugal 868 (869.618 MHz / BW62.5 / SF7 / CR6)' },
        { value: 'SWITZERLAND', label: 'Switzerland (869.618 MHz / BW62.5 / SF8 / CR8)' },
        { value: 'USA_CANADA', label: 'USA/Canada (Recommended) (910.525 MHz / BW62.5 / SF7 / CR5)' },
        { value: 'VIETNAM_NARROW', label: 'Vietnam (Narrow) (920.250 MHz / BW62.5 / SF8 / CR5)' },
        { value: 'VIETNAM_DEPRECATED', label: 'Vietnam (Deprecated) (920.250 MHz / BW250 / SF11 / CR5)' },
    ];

    constructor(api) {
        this._api = api;
        this._root = null;
    }

    mount(root) {
        this._root = root;
    }

    clear() {
        if (this._root) this._root.innerHTML = '';
    }

    render(mc, config) {
        if (!this._root) return;
        this._pimesh = window.PlatformContext?.isPimesh(config);
        const radio = (mc && mc.radio) || {};
        this._radio = radio;
        this._txEnabled = mc.tx_enabled !== false;
        const region = config?.radio?.region;
        const range = {US: [902, 928], EU_868: [863, 870], ANZ: [915, 928]}[region];
        const presets = MeshcoreRadioSettings._RADIO_PRESETS.filter(p => {
            if (!this._pimesh || !range) return true;
            const freq = Number(p.label.match(/([\d.]+) MHz/)?.[1]);
            return freq > range[0] && freq < range[1];
        });
        const freq = radio.frequency_mhz;
        const hint = (freq != null && Number(freq) > 0)
            ? `<span class="cfg-field__hint">Currently ${this._fmtFreq(freq)} / ${this._fmtBw(radio.bandwidth_khz)} / ${this._fmtSf(radio.spreading_factor)}</span>`
            : '';

        this._root.innerHTML = `
            <article class="cfg-card" data-mc-radio-card>
                <header class="cfg-card__head">
                    <h3 class="cfg-card__title">Radio settings</h3>
                    <p class="cfg-card__hint">
                        Community frequency/BW/SF/CR presets, applied over the
                        live companion connection. ${this._pimesh
                            ? 'PiMesh verifies the hardware settings after applying them.'
                            : 'Applying reboots the companion; it briefly shows disconnected while reconnecting.'}
                    </p>
                </header>
                <label class="cfg-field">
                    <span class="cfg-field__label">Preset</span>
                    <select class="cfg-field__input" data-mc-radio-input>
                        <option value="" disabled selected>-- select --</option>
                        ${presets.map((p) => `
                            <option value="${p.value}">${this._esc(p.label)}</option>
                        `).join('')}
                    </select>
                    ${hint}
                </label>
                ${this._pimesh ? `<label class="cfg-field cfg-field--toggle">
                    <input type="checkbox" data-mc-tx-enabled ${this._txEnabled ? 'checked' : ''}>
                    <span class="cfg-field__label">Send messages and adverts from Meshpoint</span></label>
                    <p class="cfg-field__hint">Radio protocol acknowledgements are managed by MeshCore.</p>
                    <label class="cfg-field"><span class="cfg-field__label">TX power (dBm)</span>
                    <input class="cfg-field__input" data-mc-tx-power type="number" min="2" max="22"
                        step="1" value="${Number(radio.tx_power) || 18}"></label>` : ''}
                <div class="cfg-card__actions">
                    <button class="terminal-button terminal-button--primary"
                            type="button" data-mc-radio-save>
                        Set Radio
                    </button>
                </div>
                <p class="cfg-status" data-mc-radio-status aria-live="polite"></p>
            </article>
        `;
        const btn = this._root.querySelector('[data-mc-radio-save]');
        if (btn) {
            btn.addEventListener('click', () => this._save());
        }
    }

    async _save() {
        const input = this._root.querySelector('[data-mc-radio-input]');
        const status = this._root.querySelector('[data-mc-radio-status]');
        const button = this._root.querySelector('[data-mc-radio-save]');
        if (!input || !status) return;

        const preset = input.value;
        if (!preset && !this._pimesh) {
            status.dataset.kind = 'error';
            status.textContent = 'Pick a preset.';
            return;
        }

        if (button) button.disabled = true;
        const body = preset ? {preset} : {};
        if (this._pimesh) {
            const power = Number(this._root.querySelector('[data-mc-tx-power]').value);
            if (!Number.isInteger(power) || power < 2 || power > 22) {
                status.dataset.kind = 'error';
                status.textContent = 'TX power must be between 2 and 22 dBm.';
                button.disabled = false;
                return;
            }
            if (power !== this._radio.tx_power) body.tx_power_dbm = power;
            body.tx_enabled = this._root.querySelector('[data-mc-tx-enabled]').checked;
        }
        status.dataset.kind = 'pending';
        status.textContent =
            'Setting radio… (cross-band changes can take up to a minute)';

        const result = await this._api.put(
            '/api/config/meshcore/companion-radio',
            body,
        );

        if (result) {
            status.dataset.kind = 'success';
            status.textContent =
                this._pimesh ? 'Saved and verified on PiMesh.' : 'Applied: companion is rebooting; this can take up to a minute.';
            this._api.toast(this._pimesh ? 'MeshCore radio saved' : 'MeshCore radio updated, companion rebooting');
            await this._api.refresh();
        } else {
            // _api.put toasts Save failed: <detail>; keep it on the card too.
            const detail = (this._api.lastError && this._api.lastError()) || '';
            status.dataset.kind = 'error';
            status.textContent = detail
                ? `Set radio failed: ${detail}`
                : 'Set radio failed.';
        }
        if (button) button.disabled = false;
    }

    _esc(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    _fmtFreq(v) {
        const n = Number(v);
        return Number.isFinite(n) && n > 0 ? `${n.toFixed(3)} MHz` : '—';
    }

    _fmtBw(v) {
        const n = Number(v);
        return Number.isFinite(n) && n > 0 ? `BW${n}` : '—';
    }

    _fmtSf(v) {
        const n = Number(v);
        return Number.isFinite(n) && n > 0 ? `SF${n}` : '—';
    }
}

window.MeshcoreRadioSettings = MeshcoreRadioSettings;
