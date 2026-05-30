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
    /** Sentinel preset value. Will not collide with real preset names because
     *  presets.py uses ALL-CAPS without leading underscores. */
    static CUSTOM_VALUE = '__CUSTOM__';

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
                    <fieldset class="cfg-fieldset" data-radio-custom-wrap style="display:none">
                        <legend class="cfg-fieldset__legend">Custom modem</legend>
                        <p class="cfg-card__hint">
                            For non-standard SF / BW / CR combinations. Off-spec
                            choices may be silently dropped by neighboring nodes.
                            Restart required after save.
                        </p>
                        <label class="cfg-field">
                            <span class="cfg-field__label">Spreading factor (5-12)</span>
                            <input class="cfg-field__input" type="number"
                                   min="5" max="12" step="1" data-radio-sf>
                        </label>
                        <label class="cfg-field">
                            <span class="cfg-field__label">Bandwidth</span>
                            <select class="cfg-field__input" data-radio-bw>
                                <option value="125">125 kHz</option>
                                <option value="250">250 kHz</option>
                                <option value="500">500 kHz</option>
                            </select>
                        </label>
                        <label class="cfg-field">
                            <span class="cfg-field__label">Coding rate</span>
                            <select class="cfg-field__input" data-radio-cr>
                                <option value="4/5">4/5</option>
                                <option value="4/6">4/6</option>
                                <option value="4/7">4/7</option>
                                <option value="4/8">4/8</option>
                            </select>
                        </label>
                    </fieldset>
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
        this._customWrap = this._root.querySelector('[data-radio-custom-wrap]');
        this._sfEl = this._root.querySelector('[data-radio-sf]');
        this._bwEl = this._root.querySelector('[data-radio-bw]');
        this._crEl = this._root.querySelector('[data-radio-cr]');

        this._form.addEventListener('submit', (e) => this._onSubmit(e));
        this._modeInputs.forEach((input) => {
            input.addEventListener('change', () => this._onModeChange());
        });
        this._regionEl.addEventListener('change', () => this._onRegionChange());
        this._slotEl.addEventListener('input', () => this._onSlotChange());
        this._freqEl.addEventListener('input', () => this._onFreqChange());
        this._bwEl.addEventListener('change', () => this._onCustomBwChange());
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
            spreading_factor: radio.spreading_factor != null ? Number(radio.spreading_factor) : null,
            bandwidth_khz: radio.bandwidth_khz != null ? Number(radio.bandwidth_khz) : null,
            coding_rate: radio.coding_rate || '',
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
        this._fillCustomInputs();
        // Empty current_preset means SF/BW/CR did not match a named preset:
        // open the card on Custom so the user sees what they're actually on.
        this._setSelectedPreset(this._initial.preset || RadioConfigEditCard.CUSTOM_VALUE);
        this._syncSlotFromFreq();
    }

    _fillCustomInputs() {
        if (this._initial.spreading_factor != null) {
            this._sfEl.value = String(this._initial.spreading_factor);
        }
        if (this._initial.bandwidth_khz != null) {
            const bw = String(this._initial.bandwidth_khz);
            // Snap unsupported BW values (rare; pre-v0.7.0 yaml could carry them)
            // back to 125 so the <select> shows a sensible default.
            const opt = Array.from(this._bwEl.options).find((o) => o.value === bw);
            this._bwEl.value = opt ? bw : '125';
        }
        if (this._initial.coding_rate) {
            this._crEl.value = this._initial.coding_rate;
        }
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
        const named = this._presets.map((p) => {
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
        // Custom chip lives at the end of the named list so users see the
        // standard menu first; selecting it reveals the SF/BW/CR fieldset.
        const custom = `
            <button type="button" class="cfg-chip cfg-chip--custom"
                    data-preset="${RadioConfigEditCard.CUSTOM_VALUE}"
                    title="Edit spreading factor, bandwidth, and coding rate by hand.">
                Custom
            </button>
        `;
        this._presetsEl.innerHTML = named + custom;
        this._presetsEl.querySelectorAll('[data-preset]').forEach((chip) => {
            chip.addEventListener('click', () => this._onPresetChip(chip.dataset.preset));
        });
    }

    _setSelectedPreset(name) {
        const target = name || RadioConfigEditCard.CUSTOM_VALUE;
        this._presetsEl.querySelectorAll('[data-preset]').forEach((chip) => {
            chip.classList.toggle('cfg-chip--selected', chip.dataset.preset === target);
        });
        this._customWrap.style.display =
            target === RadioConfigEditCard.CUSTOM_VALUE ? '' : 'none';
    }

    _onPresetChip(name) {
        this._setSelectedPreset(name);
        if (name === RadioConfigEditCard.CUSTOM_VALUE) {
            // Switching to Custom: keep whatever SF/BW/CR are already on the
            // form (initial fill or user edits). Resync slot off the current BW.
            this._syncSlotFromFreq();
            return;
        }
        const preset = this._presets.find((p) => p.name === name);
        if (preset && preset.bandwidth_khz) {
            this._initial.bandwidth_khz = Number(preset.bandwidth_khz);
            this._syncSlotFromFreq();
        }
    }

    _onCustomBwChange() {
        const bw = parseInt(this._bwEl.value, 10);
        if (Number.isFinite(bw)) {
            // Slot ↔ MHz math depends on bandwidth; the slot field needs to
            // re-render whenever BW changes while Custom is active.
            this._initial.bandwidth_khz = bw;
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
        const presetSel = this._selectedPreset();
        const isCustom = presetSel === RadioConfigEditCard.CUSTOM_VALUE;
        const freq = parseFloat(this._freqEl.value);
        const hop = parseInt(this._hopEl.value, 10);

        const radioBody = {};
        if (region && region !== this._initial.region) radioBody.region = region;

        if (isCustom) {
            const sf = parseInt(this._sfEl.value, 10);
            const bw = parseInt(this._bwEl.value, 10);
            const cr = (this._crEl.value || '').trim();
            if (!Number.isFinite(sf) || sf < 5 || sf > 12) {
                this._setStatus('error', 'Spreading factor must be 5-12.');
                return;
            }
            if (![125, 250, 500].includes(bw)) {
                this._setStatus('error', 'Bandwidth must be 125, 250, or 500 kHz.');
                return;
            }
            if (!['4/5', '4/6', '4/7', '4/8'].includes(cr)) {
                this._setStatus('error', 'Coding rate must be 4/5, 4/6, 4/7, or 4/8.');
                return;
            }
            if (sf !== this._initial.spreading_factor) radioBody.spreading_factor = sf;
            if (bw !== this._initial.bandwidth_khz) radioBody.bandwidth_khz = bw;
            if (cr !== this._initial.coding_rate) radioBody.coding_rate = cr;
        } else if (presetSel && presetSel !== this._initial.preset) {
            radioBody.preset = presetSel;
        }

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
