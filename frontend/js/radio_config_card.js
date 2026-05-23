/**
 * Radio tab — Radio Configuration card (observational, v0.7.4).
 *
 * Read-only telemetry view of the live radio config:
 *   - Region + active modem preset (or Custom)
 *   - Frequency, slot, TX power, hop limit
 *   - Computed SF / BW / CR / Sync / Preamble strip
 *
 * Editing moved to Configuration → Radio (frequency / preset /
 * region) and Configuration → Transmit (TX power / hop limit) in
 * v0.7.4. This card surfaces a deep-link to the editing surface so
 * muscle memory still lands somewhere useful.
 */
class RadioConfigCard {
    constructor(api) {
        this._api = api;
        this._root = null;
        this._presets = [];
        this._regions = [];
    }

    mount(rootEl) {
        this._root = rootEl;
        rootEl.classList.add('r-card', 'r-card--readout');
        rootEl.innerHTML = `
            <div class="r-card__header">
                <h3 class="r-card__title">Radio Configuration</h3>
                <span class="r-card__subtitle" id="r-config-subtitle">--</span>
            </div>
            <div class="r-readout-grid r-readout-grid--two-col">
                <div class="r-readout-row">
                    <span class="r-readout-row__label">Region</span>
                    <span class="r-readout-row__value" id="r-rd-region">--</span>
                </div>
                <div class="r-readout-row">
                    <span class="r-readout-row__label">Modem preset</span>
                    <span class="r-readout-row__value" id="r-rd-preset">--</span>
                </div>
                <div class="r-readout-row">
                    <span class="r-readout-row__label">Frequency</span>
                    <span class="r-readout-row__value r-readout-row__value--mono"
                          id="r-rd-freq">--</span>
                </div>
                <div class="r-readout-row">
                    <span class="r-readout-row__label">Slot</span>
                    <span class="r-readout-row__value r-readout-row__value--mono"
                          id="r-rd-slot">--</span>
                </div>
                <div class="r-readout-row">
                    <span class="r-readout-row__label">TX power</span>
                    <span class="r-readout-row__value r-readout-row__value--mono"
                          id="r-rd-tx-power">--</span>
                </div>
                <div class="r-readout-row">
                    <span class="r-readout-row__label">Hop limit</span>
                    <span class="r-readout-row__value r-readout-row__value--mono"
                          id="r-rd-hop">--</span>
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
            <a class="r-config-link" href="#/configuration/radio">
                <span>Edit radio settings</span>
                <span aria-hidden="true">→</span>
            </a>
        `;
    }

    render(config) {
        this._presets = config.presets || [];
        this._regions = config.regions || [];
        const radio = config.radio || {};
        const tx = config.transmit || {};

        this._renderRow('#r-rd-region', this._regionDisplay(radio.region));
        this._renderRow('#r-rd-preset', this._presetDisplay(radio.current_preset));
        this._renderRow('#r-rd-freq', radio.frequency_mhz ? `${radio.frequency_mhz} MHz` : null);
        this._renderRow('#r-rd-slot', this._slotFor(radio));
        this._renderRow('#r-rd-tx-power', tx.tx_power_dbm != null ? `${tx.tx_power_dbm} dBm` : null);
        this._renderRow('#r-rd-hop', tx.hop_limit != null ? String(tx.hop_limit) : null);

        this._renderReadouts(radio);
        this._renderSubtitle(radio);
    }

    _renderRow(selector, value) {
        const el = this._root.querySelector(selector);
        if (!el) return;
        if (!value) {
            el.textContent = '--';
            el.classList.add('r-readout-row__value--empty');
        } else {
            el.textContent = value;
            el.classList.remove('r-readout-row__value--empty');
        }
    }

    _regionDisplay(regionId) {
        if (!regionId) return null;
        const r = this._regions.find((x) => x.id === regionId);
        if (!r) return regionId;
        return `${r.name} (${r.frequency_mhz} MHz)`;
    }

    _presetDisplay(presetName) {
        if (!presetName) return 'Custom';
        const p = this._presets.find((x) => x.name === presetName);
        if (!p) return presetName;
        return p.tx_capable ? p.display_name : `${p.display_name} (RX only)`;
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
        sub.textContent = freq ? `${preset} — ${freq}` : preset;
    }

    _slotFor(radio) {
        const band = this._regionBand(radio.region);
        const bw = radio.bandwidth_khz;
        const freq = radio.frequency_mhz;
        if (!band || !bw || !freq || ![125, 250, 500].includes(bw)) return null;
        const spacing = bw / 1000;
        const numSlots = Math.floor((band.end - band.start) / spacing);
        const raw = (freq - band.start - spacing / 2) / spacing + 1;
        const n = Math.round(raw);
        if (n >= 1 && n <= numSlots && Math.abs(raw - n) < 0.001) return String(n);
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
}

window.RadioConfigCard = RadioConfigCard;
