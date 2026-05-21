/**
 * Configuration → Radio card.
 *
 * Single responsibility: edit the radio block of local.yaml — region,
 * Meshtastic preset, explicit frequency (MHz or slot), and hop limit.
 * Region or frequency changes require a service restart; preset and
 * hop-limit changes hot-reload where possible.
 *
 * Slot ↔ MHz conversion uses the Meshtastic firmware formula
 * ``freq = band.start + (slot - 1) * (bw/1000) + (bw/2000)``. Hop
 * limit lives under ``/api/config/transmit`` server-side, so we
 * dual-dispatch when it changes.
 */

class RadioConfigEditCard {
    constructor(api) {
        this._api = api;
        this._root = null;
        this._regions = [];
        this._presets = [];
        this._initial = {};
    }

    mount(root) {
        this._root = root;
        this._root.innerHTML = `
            <article class="cfg-card" data-radio-card>
                <header class="cfg-card__head">
                    <h3 class="cfg-card__title">Radio</h3>
                    <p class="cfg-card__hint">
                        Region, modem preset, frequency, and hop limit.
                        Region and frequency changes require a service
                        restart; preset and hop-limit changes
                        hot-reload where possible.
                    </p>
                </header>
                <form class="cfg-form" data-radio-form>
                    <label class="cfg-field">
                        <span class="cfg-field__label">Region</span>
                        <select class="cfg-field__input" data-radio-region></select>
                    </label>
                    <div class="cfg-field">
                        <span class="cfg-field__label">Modem preset</span>
                        <div class="cfg-chip-row" data-radio-presets></div>
                    </div>
                    <fieldset class="cfg-field cfg-field--inline">
                        <legend class="cfg-field__label">Frequency</legend>
                        <label class="cfg-radio">
                            <input type="radio" name="freq-mode"
                                   value="mhz" data-freq-mode="mhz" checked />
                            <span>Explicit MHz</span>
                        </label>
                        <label class="cfg-radio">
                            <input type="radio" name="freq-mode"
                                   value="slot" data-freq-mode="slot" />
                            <span>Channel slot</span>
                        </label>
                    </fieldset>
                    <label class="cfg-field" data-freq-mhz-wrap>
                        <span class="cfg-field__label">Frequency (MHz)</span>
                        <input class="cfg-field__input" type="number"
                               step="0.001" data-radio-freq>
                    </label>
                    <label class="cfg-field" data-freq-slot-wrap style="display:none">
                        <span class="cfg-field__label">Slot (1 = lowest)</span>
                        <input class="cfg-field__input" type="number"
                               step="1" min="1" data-radio-slot>
                    </label>
                    <label class="cfg-field">
                        <span class="cfg-field__label">Hop limit (0-7)</span>
                        <select class="cfg-field__input" data-radio-hop></select>
                    </label>
                    <div class="cfg-card__actions">
                        <button class="terminal-button terminal-button--primary"
                                type="submit">Save</button>
                    </div>
                    <p class="cfg-status" data-radio-status aria-live="polite"></p>
                </form>
            </article>
        `;
        this._form = this._root.querySelector('[data-radio-form]');
        this._regionEl = this._root.querySelector('[data-radio-region]');
        this._presetsEl = this._root.querySelector('[data-radio-presets]');
        this._freqEl = this._root.querySelector('[data-radio-freq]');
        this._slotEl = this._root.querySelector('[data-radio-slot]');
        this._hopEl = this._root.querySelector('[data-radio-hop]');
        this._statusEl = this._root.querySelector('[data-radio-status]');
        this._freqMhzWrap = this._root.querySelector('[data-freq-mhz-wrap]');
        this._freqSlotWrap = this._root.querySelector('[data-freq-slot-wrap]');
        this._modeInputs = this._root.querySelectorAll('[data-freq-mode]');

        this._form.addEventListener('submit', (e) => this._onSubmit(e));
        this._modeInputs.forEach((input) => {
            input.addEventListener('change', () => this._onModeChange());
        });
        this._regionEl.addEventListener('change', () => this._onRegionChange());
        this._slotEl.addEventListener('input', () => this._onSlotChange());
        this._freqEl.addEventListener('input', () => this._onFreqChange());
    }

    render(config) {
        this._regions = config.regions || [];
        this._presets = config.presets || [];
        const radio = config.radio || {};
        const tx = config.transmit || {};

        this._initial = {
            region: radio.region || '',
            preset: radio.current_preset || '',
            frequency_mhz: radio.frequency_mhz != null ? Number(radio.frequency_mhz) : null,
            bandwidth_khz: radio.bandwidth_khz != null ? Number(radio.bandwidth_khz) : null,
            hop_limit: tx.hop_limit != null ? Number(tx.hop_limit) : 3,
        };

        this._renderRegions();
        this._renderPresets();
        this._renderHopLimit();
        this._regionEl.value = this._initial.region;
        if (this._initial.frequency_mhz != null) {
            this._freqEl.value = this._initial.frequency_mhz;
        }
        this._hopEl.value = String(this._initial.hop_limit);
        this._setSelectedPreset(this._initial.preset);
        this._syncSlotFromFreq();
    }

    _renderRegions() {
        this._regionEl.innerHTML = this._regions.map((r) => {
            const safe = this._esc(r.id);
            const label = this._esc(`${r.name} (${r.frequency_mhz} MHz)`);
            return `<option value="${safe}">${label}</option>`;
        }).join('');
    }

    _renderHopLimit() {
        this._hopEl.innerHTML = Array.from({ length: 8 }, (_, n) => {
            const label = n === 0 ? '0 (direct only)' : String(n);
            return `<option value="${n}">${this._esc(label)}</option>`;
        }).join('');
    }

    _renderPresets() {
        this._presetsEl.innerHTML = this._presets.map((p) => {
            const safe = this._esc(p.name);
            const label = this._esc(p.display_name);
            const cap = p.tx_capable ? '' : ' <span class="cfg-chip__hint">RX</span>';
            return `
                <button type="button" class="cfg-chip"
                        data-preset="${safe}">
                    ${label}${cap}
                </button>
            `;
        }).join('');
        this._presetsEl.querySelectorAll('[data-preset]').forEach((chip) => {
            chip.addEventListener('click', () => this._onPresetChip(chip.dataset.preset));
        });
    }

    _setSelectedPreset(name) {
        this._presetsEl.querySelectorAll('[data-preset]').forEach((chip) => {
            chip.classList.toggle('cfg-chip--selected', chip.dataset.preset === name);
        });
    }

    _onPresetChip(name) {
        this._setSelectedPreset(name);
        const preset = this._presets.find((p) => p.name === name);
        if (preset && preset.bandwidth_khz) {
            this._initial.bandwidth_khz = Number(preset.bandwidth_khz);
            this._syncSlotFromFreq();
        }
    }

    _onRegionChange() {
        const region = this._regionEl.value;
        const r = this._regions.find((x) => x.id === region);
        if (r && r.frequency_mhz != null) {
            this._freqEl.value = r.frequency_mhz;
            this._syncSlotFromFreq();
        }
    }

    _onModeChange() {
        const mode = this._currentMode();
        this._freqMhzWrap.style.display = mode === 'mhz' ? '' : 'none';
        this._freqSlotWrap.style.display = mode === 'slot' ? '' : 'none';
        if (mode === 'slot') this._syncSlotFromFreq();
    }

    _currentMode() {
        const checked = Array.from(this._modeInputs).find((i) => i.checked);
        return checked ? checked.value : 'mhz';
    }

    _onFreqChange() {
        if (this._currentMode() === 'mhz') this._syncSlotFromFreq();
    }

    _onSlotChange() {
        const slot = parseInt(this._slotEl.value, 10);
        if (!Number.isFinite(slot) || slot < 1) return;
        const freq = this._slotToFreq(slot);
        if (freq != null) this._freqEl.value = freq.toFixed(4);
    }

    _syncSlotFromFreq() {
        const freq = parseFloat(this._freqEl.value);
        if (!Number.isFinite(freq)) return;
        const slot = this._freqToSlot(freq);
        if (slot != null) this._slotEl.value = slot;
        else this._slotEl.value = '';
    }

    _slotToFreq(slot) {
        const band = this._regionBand(this._regionEl.value);
        const bw = this._initial.bandwidth_khz;
        if (!band || !bw) return null;
        const spacing = bw / 1000;
        const start = band.start + (slot - 1) * spacing + spacing / 2;
        return start;
    }

    _freqToSlot(freq) {
        const band = this._regionBand(this._regionEl.value);
        const bw = this._initial.bandwidth_khz;
        if (!band || !bw || ![125, 250, 500].includes(bw)) return null;
        const spacing = bw / 1000;
        const numSlots = Math.floor((band.end - band.start) / spacing);
        const raw = (freq - band.start - spacing / 2) / spacing + 1;
        const n = Math.round(raw);
        if (n >= 1 && n <= numSlots && Math.abs(raw - n) < 0.001) return n;
        return null;
    }

    _regionBand(regionId) {
        const bands = {
            US:     { start: 902.0, end: 928.0 },
            EU_868: { start: 863.0, end: 870.0 },
            ANZ:    { start: 915.0, end: 928.0 },
            IN:     { start: 865.0, end: 867.0 },
            KR:     { start: 920.0, end: 923.0 },
            SG_923: { start: 917.0, end: 925.0 },
        };
        return bands[regionId] || null;
    }

    async _onSubmit(event) {
        event.preventDefault();

        const region = this._regionEl.value;
        const preset = this._selectedPreset();
        const freq = parseFloat(this._freqEl.value);
        const hop = parseInt(this._hopEl.value, 10);

        const radioBody = {};
        if (region && region !== this._initial.region) radioBody.region = region;
        if (preset && preset !== this._initial.preset) radioBody.preset = preset;
        if (Number.isFinite(freq) && freq !== this._initial.frequency_mhz) {
            radioBody.frequency_mhz = freq;
        }

        const txBody = {};
        if (Number.isFinite(hop) && hop !== this._initial.hop_limit) {
            if (hop < 0 || hop > 7) {
                this._setStatus('error', 'Hop limit must be 0-7.');
                return;
            }
            txBody.hop_limit = hop;
        }

        if (Object.keys(radioBody).length === 0 && Object.keys(txBody).length === 0) {
            this._setStatus('', 'No changes.');
            return;
        }

        this._setStatus('pending', 'Saving…');
        let restartRequired = false;
        if (Object.keys(radioBody).length > 0) {
            const res = await this._api.put('/api/config/radio', radioBody);
            if (!res) {
                this._setStatus('error', 'Save failed.');
                return;
            }
            restartRequired = restartRequired || !!res.restart_required;
        }
        if (Object.keys(txBody).length > 0) {
            const res = await this._api.put('/api/config/transmit', txBody);
            if (!res) {
                this._setStatus('error', 'Save failed.');
                return;
            }
            restartRequired = restartRequired || !!res.restart_required;
        }

        this._setStatus('success', 'Saved.');
        if (restartRequired) {
            this._api.signalRestart('Radio settings updated.');
        } else {
            this._api.toast('Radio settings saved');
        }
        await this._api.refresh();
    }

    _selectedPreset() {
        const sel = this._presetsEl.querySelector('.cfg-chip--selected');
        return sel ? sel.dataset.preset : '';
    }

    _setStatus(kind, message) {
        if (!this._statusEl) return;
        this._statusEl.dataset.kind = kind;
        this._statusEl.textContent = message;
    }

    _esc(str) {
        const el = document.createElement('span');
        el.textContent = str || '';
        return el.innerHTML;
    }
}

window.RadioConfigEditCard = RadioConfigEditCard;
