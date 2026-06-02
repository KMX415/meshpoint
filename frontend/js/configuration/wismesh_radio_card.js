/**
 * Configuration → Transmit on WisMesh Node: WisBlock module + meshtasticd LoRa.
 */

const WISMESH_MODEM_PRESETS = [
    'LONG_FAST',
    'LONG_TURBO',
    'LONG_MODERATE',
    'LONG_SLOW',
    'VERY_LONG_SLOW',
    'MEDIUM_FAST',
    'MEDIUM_SLOW',
    'SHORT_FAST',
    'SHORT_SLOW',
    'SHORT_TURBO',
];

class WismeshRadioCard {
    constructor(api) {
        this._api = api;
        this._root = null;
        this._initial = {};
        this._activeModuleId = '';
    }

    mount(root) {
        this._root = root;
        this._root.innerHTML = `
            <article class="cfg-card cfg-card--hero">
                <header class="cfg-card__head">
                    <h3 class="cfg-card__title">WisBlock module</h3>
                    <p class="cfg-card__hint">
                        Pick the LoRa module seated in WisBlock Slot 1 on the RAK6421 HAT.
                        Switching modules installs the matching meshtasticd hardware profile,
                        restarts meshtasticd, then restart Meshpoint so the bridge reconnects.
                    </p>
                </header>
                <form class="cfg-form" data-wismesh-module-form>
                    <label class="cfg-field">
                        <span class="cfg-field__label">Module in Slot 1</span>
                        <select class="cfg-field__input" data-wismesh-module></select>
                        <span class="cfg-field__hint" data-wismesh-module-tagline></span>
                    </label>
                    <div class="cfg-card__actions">
                        <button class="terminal-button terminal-button--primary"
                                type="submit" data-wismesh-module-apply>Apply module preset</button>
                    </div>
                    <p class="cfg-status" data-wismesh-module-status aria-live="polite"></p>
                </form>
            </article>
            <article class="cfg-card">
                <header class="cfg-card__head">
                    <h3 class="cfg-card__title">Meshtastic radio</h3>
                    <p class="cfg-card__hint">
                        Live LoRa settings (region, modem preset, TX power) via meshtasticd
                        writeConfig. Use after the correct WisBlock module is active above.
                    </p>
                </header>
                <form class="cfg-form" data-wismesh-radio-form>
                    <label class="cfg-field cfg-field--toggle">
                        <input type="checkbox" data-wismesh-tx-enabled>
                        <span class="cfg-field__label">TX enabled</span>
                    </label>
                    <label class="cfg-field">
                        <span class="cfg-field__label">TX power (dBm)</span>
                        <input class="cfg-field__input" type="number" min="0" max="30"
                               step="1" data-wismesh-tx-power>
                    </label>
                    <label class="cfg-field">
                        <span class="cfg-field__label">Region</span>
                        <select class="cfg-field__input" data-wismesh-region></select>
                    </label>
                    <label class="cfg-field">
                        <span class="cfg-field__label">Modem preset</span>
                        <select class="cfg-field__input" data-wismesh-preset></select>
                    </label>
                    <div class="cfg-card__actions">
                        <button class="terminal-button terminal-button--primary"
                                type="submit" data-wismesh-save>Save radio</button>
                    </div>
                    <p class="cfg-status" data-wismesh-status aria-live="polite"></p>
                </form>
            </article>
        `;
        this._moduleForm = this._root.querySelector('[data-wismesh-module-form]');
        this._moduleSelect = this._root.querySelector('[data-wismesh-module]');
        this._moduleTagline = this._root.querySelector('[data-wismesh-module-tagline]');
        this._moduleStatus = this._root.querySelector('[data-wismesh-module-status]');
        this._moduleApplyBtn = this._root.querySelector('[data-wismesh-module-apply]');
        this._moduleForm.addEventListener('submit', (e) => this._onModuleSubmit(e));
        this._moduleSelect.addEventListener('change', () => this._updateModuleTagline());

        this._form = this._root.querySelector('[data-wismesh-radio-form]');
        this._txEnabled = this._root.querySelector('[data-wismesh-tx-enabled]');
        this._txPower = this._root.querySelector('[data-wismesh-tx-power]');
        this._regionEl = this._root.querySelector('[data-wismesh-region]');
        this._presetEl = this._root.querySelector('[data-wismesh-preset]');
        this._statusEl = this._root.querySelector('[data-wismesh-status]');
        this._saveBtn = this._root.querySelector('[data-wismesh-save]');
        this._form.addEventListener('submit', (e) => this._onSubmit(e));
    }

    render(config) {
        const md = window.PlatformContext.meshtasticdRuntime(config);
        const captureMd = window.PlatformContext.meshtasticdConfig(config);
        const connected = Boolean(md.bridge_connected);
        this._activeModuleId = captureMd.active_module_id
            || (captureMd.module_presets || []).find((p) => p.active)?.module_id
            || '';

        this._fillModulePresets(captureMd.module_presets || []);
        if (this._moduleSelect.value !== this._activeModuleId && this._activeModuleId) {
            this._moduleSelect.value = this._activeModuleId;
        }
        this._updateModuleTagline();
        const moduleDirty = this._moduleSelect.value !== this._activeModuleId;
        this._moduleApplyBtn.disabled = !moduleDirty;

        this._initial = {
            tx_enabled: md.tx_enabled !== false,
            tx_power_dbm: md.tx_power_dbm != null ? Number(md.tx_power_dbm) : 0,
            region: md.region || (config.radio && config.radio.region) || 'US',
            modem_preset: md.modem_preset || '',
        };

        this._txEnabled.checked = this._initial.tx_enabled;
        this._txPower.value = String(this._initial.tx_power_dbm);
        this._fillRegions(config.regions || []);
        this._fillModemPresets();
        this._regionEl.value = this._initial.region;
        if (this._initial.modem_preset) {
            this._presetEl.value = this._initial.modem_preset;
        }

        const radioDisabled = !connected;
        this._saveBtn.disabled = radioDisabled;
        this._txEnabled.disabled = radioDisabled;
        this._txPower.disabled = radioDisabled;
        this._regionEl.disabled = radioDisabled;
        this._presetEl.disabled = radioDisabled;
        this._setStatus(
            this._statusEl,
            connected ? '' : 'Bridge disconnected. Apply module or restart meshtasticd, then Meshpoint.',
            connected ? '' : 'error',
        );
    }

    _fillModulePresets(presets) {
        this._moduleSelect.innerHTML = '';
        const list = presets.length ? presets : [
            { module_id: '13302', label: 'RAK13302 1W', tagline: '', active: true },
            { module_id: '13300', label: 'RAK13300', tagline: '', active: false },
        ];
        list.forEach((p) => {
            const opt = document.createElement('option');
            opt.value = p.module_id;
            const activeMark = p.active ? ' (active)' : '';
            opt.textContent = `${p.label}${activeMark}`;
            opt.dataset.tagline = p.tagline || '';
            this._moduleSelect.appendChild(opt);
        });
    }

    _updateModuleTagline() {
        const opt = this._moduleSelect.selectedOptions[0];
        const text = opt ? (opt.dataset.tagline || '') : '';
        this._moduleTagline.textContent = text;
        const dirty = this._moduleSelect.value !== this._activeModuleId;
        this._moduleApplyBtn.disabled = !dirty;
    }

    _fillRegions(regions) {
        this._regionEl.innerHTML = '';
        const list = regions.length ? regions : [{ id: 'US', name: 'US' }];
        list.forEach((r) => {
            const opt = document.createElement('option');
            opt.value = r.id;
            opt.textContent = r.name || r.id;
            this._regionEl.appendChild(opt);
        });
    }

    _fillModemPresets() {
        this._presetEl.innerHTML = '';
        WISMESH_MODEM_PRESETS.forEach((name) => {
            const opt = document.createElement('option');
            opt.value = name;
            opt.textContent = name.replace(/_/g, '');
            this._presetEl.appendChild(opt);
        });
    }

    async _onModuleSubmit(event) {
        event.preventDefault();
        const moduleId = this._moduleSelect.value;
        if (!moduleId || moduleId === this._activeModuleId) {
            this._setStatus(this._moduleStatus, 'No module change.', '');
            return;
        }
        const label = this._moduleSelect.selectedOptions[0]?.textContent || moduleId;
        const ok = window.confirm(
            `Apply ${label}?\n\n`
            + 'This restarts meshtasticd (~30s RF pause). '
            + 'Then restart Meshpoint from Settings → System so the dashboard bridge reconnects.',
        );
        if (!ok) return;

        this._setStatus(this._moduleStatus, 'Applying module preset…', 'pending');
        const result = await this._api.put('/api/meshtasticd/module-preset', {
            module_id: moduleId,
        });
        if (!result) {
            this._setStatus(this._moduleStatus, 'Module apply failed.', 'error');
            return;
        }
        if (result.already_active) {
            this._setStatus(this._moduleStatus, 'Already on this module.', 'success');
        } else {
            this._setStatus(
                this._moduleStatus,
                `Active: ${result.label}. Restart Meshpoint when convenient.`,
                'success',
            );
            this._api.signalRestart(
                `${result.label} preset applied. Restart Meshpoint to refresh the bridge.`,
            );
        }
        this._api.toast(result.label ? `${result.label} module active` : 'Module updated');
        await this._api.refresh();
    }

    async _onSubmit(event) {
        event.preventDefault();
        const body = {};
        const txOn = this._txEnabled.checked;
        if (txOn !== this._initial.tx_enabled) body.tx_enabled = txOn;

        const power = parseInt(this._txPower.value, 10);
        if (Number.isFinite(power) && power !== this._initial.tx_power_dbm) {
            body.tx_power_dbm = power;
        }

        const region = this._regionEl.value;
        if (region && region !== this._initial.region) body.region = region;

        const preset = this._presetEl.value;
        if (preset && preset !== this._initial.modem_preset) {
            body.modem_preset = preset;
        }

        if (Object.keys(body).length === 0) {
            this._setStatus(this._statusEl, 'No changes.', '');
            return;
        }

        this._setStatus(this._statusEl, 'Saving…', 'pending');
        const result = await this._api.put('/api/meshtasticd/radio', body);
        if (!result) {
            this._setStatus(this._statusEl, 'Save failed.', 'error');
            return;
        }
        this._setStatus(this._statusEl, 'Saved to meshtasticd.', 'success');
        this._api.toast('Meshtastic radio saved');
        await this._api.refresh();
    }

    _setStatus(el, message, kind) {
        if (!el) return;
        el.dataset.kind = kind;
        el.textContent = message;
    }
}

window.WismeshRadioCard = WismeshRadioCard;
