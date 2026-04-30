/**
 * Radio tab — Radio Configuration card.
 *
 * Two stacked panes:
 *   - PRESET: region + Meshtastic preset selector. Choosing a preset
 *     auto-fills the SF/BW/CR readouts. The wider region selector
 *     also auto-fills the frequency input.
 *   - TUNING: explicit frequency, TX power, hop limit. Power/hop
 *     apply at runtime; freq/preset/region require a service restart.
 * A horizontal readout strip shows the computed sync word, preamble,
 * and effective SF/BW/CR for the current selection.
 *
 * The Slot field (left of Frequency) translates between the Meshtastic
 * 1-indexed slot number and MHz using the general formula from the
 * firmware: freq = freqStart + (BW/2000) + ((slot-1) * (BW/1000)).
 * Supported for BW 125/250/500 across all regions. Entering a slot
 * fills the frequency; entering a frequency fills the slot (or shows
 * "--" if no match).
 */
class RadioConfigCard {
    constructor(api) {
        this._api = api;
        this._root = null;
        this._presets = [];
        this._regions = [];
        this._currentRadio = null;
        this._currentTx = null;
        this._effectiveBw = null;
    }

    mount(rootEl) {
        this._root = rootEl;
        rootEl.classList.add('r-card');
        rootEl.innerHTML = `
            <div class="r-card__header">
                <h3 class="r-card__title">Radio Configuration</h3>
                <span class="r-card__subtitle" id="r-config-subtitle">--</span>
            </div>
            <div class="config-stack">
                <div class="config-pane">
                    <div class="config-pane__label">Preset</div>
                    <div class="config-pane__inputs">
                        <div class="r-field">
                            <label class="r-field__label" for="r-region">Region</label>
                            <select class="r-select" id="r-region"></select>
                        </div>
                        <div class="r-field">
                            <label class="r-field__label" for="r-preset">Modem preset</label>
                            <select class="r-select" id="r-preset"></select>
                        </div>
                    </div>
                </div>
                <div class="config-pane">
                    <div class="config-pane__label">Tuning</div>
                    <div class="config-pane__inputs">
                        <div class="r-field r-field--slot">
                            <label class="r-field__label" for="r-slot">Slot</label>
                            <input type="text" class="r-input r-input--mono r-input--narrow"
                                   id="r-slot" placeholder="--" />
                        </div>
                        <div class="r-field">
                            <label class="r-field__label" for="r-freq">Frequency (MHz)</label>
                            <input type="number" class="r-input r-input--mono r-input--narrow"
                                   id="r-freq" step="0.001" min="100" max="1000" />
                        </div>
                        <div class="r-field">
                            <label class="r-field__label" for="r-tx-power">TX power (dBm)</label>
                            <input type="number" class="r-input r-input--mono r-input--narrow"
                                   id="r-tx-power" min="0" max="30" />
                        </div>
                        <div class="r-field">
                            <label class="r-field__label" for="r-hop-limit">Hop limit</label>
                            <input type="number" class="r-input r-input--mono r-input--narrow"
                                   id="r-hop-limit" min="0" max="7" />
                        </div>
                    </div>
                </div>
            </div>
            <div class="readout-strip">
                <div class="readout-strip__label">Computed</div>
                <div class="r-readout">
                    <span class="r-readout__label">SF</span>
                    <span class="r-readout__value" id="r-sf">--</span>
                </div>
                <div class="r-readout">
                    <span class="r-readout__label">BW</span>
                    <span class="r-readout__value" id="r-bw">--</span>
                </div>
                <div class="r-readout">
                    <span class="r-readout__label">CR</span>
                    <span class="r-readout__value" id="r-cr">--</span>
                </div>
                <div class="r-readout">
                    <span class="r-readout__label">Sync</span>
                    <span class="r-readout__value" id="r-sync">--</span>
                </div>
                <div class="r-readout">
                    <span class="r-readout__label">Preamble</span>
                    <span class="r-readout__value" id="r-preamble">--</span>
                </div>
            </div>
            <div class="r-card__actions">
                <button class="r-btn r-btn--primary"
                        id="r-save-config">Save Radio Settings</button>
            </div>
        `;
    }

    render(config) {
        this._presets = config.presets || [];
        this._regions = config.regions || [];
        this._currentRadio = config.radio || {};
        this._currentTx = config.transmit || {};

        this._renderRegionOptions();
        this._renderPresetOptions();
        this._renderInputs();
        this._renderReadouts(this._currentRadio);
        this._renderSubtitle(this._currentRadio);
        this._wire();
    }

    _renderRegionOptions() {
        const sel = this._root.querySelector('#r-region');
        sel.innerHTML = this._regions.map((r) => {
            const selected = r.id === this._currentRadio.region ? 'selected' : '';
            return `<option value="${r.id}" ${selected}>`
                + `${this._api.escape(r.name)} (${r.frequency_mhz} MHz)`
                + `</option>`;
        }).join('');
    }

    _renderPresetOptions() {
        const sel = this._root.querySelector('#r-preset');
        const opts = this._presets.map((p) => {
            const selected = p.name === this._currentRadio.current_preset ? 'selected' : '';
            const rxOnly = p.tx_capable ? '' : ' (RX only)';
            return `<option value="${p.name}" ${selected}>`
                + `${this._api.escape(p.display_name)}${rxOnly}</option>`;
        });
        const customSelected = !this._currentRadio.current_preset ? 'selected' : '';
        opts.push(`<option value="CUSTOM" ${customSelected}>Custom</option>`);
        sel.innerHTML = opts.join('');
    }

    _renderInputs() {
        this._root.querySelector('#r-freq').value = this._currentRadio.frequency_mhz || '';
        this._root.querySelector('#r-tx-power').value = this._currentTx.tx_power_dbm || '';
        this._root.querySelector('#r-hop-limit').value = this._currentTx.hop_limit || '';
        this._effectiveBw = this._currentRadio.bandwidth_khz || null;
        this._updateSlotFromFreq();
    }

    _renderReadouts(radio) {
        this._root.querySelector('#r-sf').textContent =
            radio.spreading_factor ? `SF${radio.spreading_factor}` : '--';
        this._root.querySelector('#r-bw').textContent =
            radio.bandwidth_khz ? `${radio.bandwidth_khz} kHz` : '--';
        this._root.querySelector('#r-cr').textContent = radio.coding_rate || '--';
        this._root.querySelector('#r-sync').textContent = radio.sync_word || '--';
        this._root.querySelector('#r-preamble').textContent =
            radio.preamble_length ? `${radio.preamble_length} sym` : '--';
    }

    _renderSubtitle(radio) {
        const sub = this._root.querySelector('#r-config-subtitle');
        const preset = radio.current_preset || 'Custom';
        const freq = radio.frequency_mhz ? `${radio.frequency_mhz} MHz` : '';
        sub.textContent = freq ? `${preset} -- ${freq}` : preset;
    }

    // Meshtastic band limits (freqStart, freqEnd) per region in MHz.
    // freqStart is the lower ISM band boundary used in the slot formula:
    //   freq = freqStart + (BW/2000) + ((slot-1) * (BW/1000))
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

    // Returns the center frequency (MHz) for a 1-indexed slot at the given
    // BW (kHz) in the given region. Returns null for unsupported inputs.
    _slotToFreq(slot, bw, regionId) {
        const band = this._regionBand(regionId);
        if (!band || ![125, 250, 500].includes(bw)) return null;
        const spacing = bw / 1000;
        const numSlots = Math.floor((band.end - band.start) / spacing);
        if (slot < 1 || slot > numSlots) return null;
        return parseFloat((band.start + spacing / 2 + (slot - 1) * spacing).toFixed(4));
    }

    // Returns the 1-indexed slot number for a frequency at the given BW in
    // the given region, or null if the frequency does not land on a slot.
    _freqToSlot(freq, bw, regionId) {
        const band = this._regionBand(regionId);
        if (!band || ![125, 250, 500].includes(bw)) return null;
        const spacing = bw / 1000;
        const numSlots = Math.floor((band.end - band.start) / spacing);
        const raw = (freq - band.start - spacing / 2) / spacing + 1;
        const n = Math.round(raw);
        if (n >= 1 && n <= numSlots && Math.abs(raw - n) < 0.001) return n;
        return null;
    }

    _updateSlotFromFreq() {
        const freqVal = parseFloat(this._root.querySelector('#r-freq').value);
        const slotEl = this._root.querySelector('#r-slot');
        if (isNaN(freqVal) || !this._effectiveBw) {
            slotEl.value = '';
            return;
        }
        const region = this._root.querySelector('#r-region').value;
        const slot = this._freqToSlot(freqVal, this._effectiveBw, region);
        slotEl.value = slot !== null ? String(slot) : '--';
    }

    _wire() {
        const presetSel = this._root.querySelector('#r-preset');
        presetSel.onchange = () => {
            const name = presetSel.value;
            if (name === 'CUSTOM') return;
            const p = this._presets.find((x) => x.name === name);
            if (!p) return;
            this._effectiveBw = p.bw_khz;
            this._renderReadouts({
                spreading_factor: p.sf,
                bandwidth_khz: p.bw_khz,
                coding_rate: p.cr,
                sync_word: this._currentRadio.sync_word,
                preamble_length: this._currentRadio.preamble_length,
            });
            this._updateSlotFromFreq();
        };

        const regionSel = this._root.querySelector('#r-region');
        regionSel.onchange = () => {
            const r = this._regions.find((x) => x.id === regionSel.value);
            if (!r) return;
            this._root.querySelector('#r-freq').value = r.frequency_mhz;
            this._updateSlotFromFreq();
        };

        const freqEl = this._root.querySelector('#r-freq');
        freqEl.onchange = () => this._updateSlotFromFreq();

        const slotEl = this._root.querySelector('#r-slot');
        slotEl.onchange = () => {
            const slotVal = parseInt(slotEl.value, 10);
            if (isNaN(slotVal) || !this._effectiveBw) return;
            const region = this._root.querySelector('#r-region').value;
            const freq = this._slotToFreq(slotVal, this._effectiveBw, region);
            if (freq !== null) freqEl.value = freq;
        };

        this._root.querySelector('#r-save-config').onclick = () => this._save();
    }

    async _save() {
        const radio = this._currentRadio;
        const tx = this._currentTx;
        const radioPayload = {};
        const txPayload = {};

        const region = this._root.querySelector('#r-region').value;
        if (region !== radio.region) radioPayload.region = region;

        const preset = this._root.querySelector('#r-preset').value;
        if (preset !== 'CUSTOM' && preset !== radio.current_preset) {
            radioPayload.preset = preset;
        }

        const freq = parseFloat(this._root.querySelector('#r-freq').value);
        if (!isNaN(freq) && freq !== radio.frequency_mhz) {
            radioPayload.frequency_mhz = freq;
        }

        const txPower = parseInt(this._root.querySelector('#r-tx-power').value, 10);
        if (!isNaN(txPower) && txPower !== tx.tx_power_dbm) {
            txPayload.tx_power_dbm = txPower;
        }

        const hopLimit = parseInt(this._root.querySelector('#r-hop-limit').value, 10);
        if (!isNaN(hopLimit) && hopLimit !== tx.hop_limit) {
            txPayload.hop_limit = hopLimit;
        }

        let restartNeeded = false;
        if (Object.keys(radioPayload).length > 0) {
            const result = await this._api.put('/api/config/radio', radioPayload);
            if (result && result.restart_required) restartNeeded = true;
        }
        if (Object.keys(txPayload).length > 0) {
            await this._api.put('/api/config/transmit', txPayload);
        }

        this._api.toast('Radio settings saved');
        if (restartNeeded) {
            this._api.signalRestart(
                'Radio changes take effect on next service restart.',
            );
        }
        await this._api.refresh();
    }
}

window.RadioConfigCard = RadioConfigCard;
