/**
 * Topbar — radio status chip.
 *
 * Renders the current region · frequency · preset as a compact pill
 * group. Updates on /api/config refreshes (which radio_settings.js
 * already drives). When values are unknown, the chip shows muted
 * placeholders instead of vanishing so the chrome layout stays
 * stable.
 *
 * Single responsibility: format radio config into a compact chip
 * row and update DOM in place. No network awareness.
 */
class TopbarRadioChip {
    constructor(rootEl) {
        this._root = rootEl;
        this._regionEl = rootEl.querySelector('.topbar-radio__region');
        this._freqEl = rootEl.querySelector('.topbar-radio__freq');
        this._presetEl = rootEl.querySelector('.topbar-radio__preset');
    }

    setRadio(radio) {
        const region = radio && radio.region ? radio.region : '--';
        const freq = radio && radio.frequency_mhz
            ? `${Number(radio.frequency_mhz).toFixed(3)} MHz`
            : '--';
        const preset = radio && radio.current_preset
            ? radio.current_preset
            : 'CUSTOM';

        this._regionEl.textContent = region;
        this._freqEl.textContent = freq;
        this._presetEl.textContent = preset;
        this._root.classList.toggle(
            'topbar-radio--unknown',
            !radio || !radio.region,
        );
    }
}

window.TopbarRadioChip = TopbarRadioChip;
