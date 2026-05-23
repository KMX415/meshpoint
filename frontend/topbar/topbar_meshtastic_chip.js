/**
 * Topbar — Meshtastic chip.
 *
 * Cyan-grouped readout: dashboard WebSocket lamp, short name (no CALL
 * label), region, frequency, and preset. Replaces the separate lamp,
 * identity badge, and radio chip.
 */
class TopbarMeshtasticChip {
    constructor(chipEl) {
        this._root = chipEl;
        this._lampEl = chipEl.querySelector('.topbar-meshtastic__lamp');
        this._callEl = chipEl.querySelector('.topbar-meshtastic__call');
        this._regionEl = chipEl.querySelector('.topbar-meshtastic__region');
        this._freqEl = chipEl.querySelector('.topbar-meshtastic__freq');
        this._presetEl = chipEl.querySelector('.topbar-meshtastic__preset');
        this._lastCall = null;
        this._connState = 'connecting';
    }

    setConnectionState(state) {
        if (state === this._connState) return;
        this._connState = state;
        this._lampEl.classList.remove(
            'topbar-meshtastic__lamp--online',
            'topbar-meshtastic__lamp--offline',
            'topbar-meshtastic__lamp--reconnecting',
        );
        this._root.classList.remove(
            'topbar-meshtastic--online',
            'topbar-meshtastic--offline',
            'topbar-meshtastic--reconnecting',
        );

        if (state === 'online') {
            this._lampEl.classList.add('topbar-meshtastic__lamp--online');
            this._root.classList.add('topbar-meshtastic--online');
            this._lampEl.setAttribute('aria-label', 'Dashboard connected');
        } else if (state === 'offline') {
            this._lampEl.classList.add('topbar-meshtastic__lamp--offline');
            this._root.classList.add('topbar-meshtastic--offline');
            this._lampEl.setAttribute('aria-label', 'Dashboard offline');
        } else {
            this._lampEl.classList.add('topbar-meshtastic__lamp--reconnecting');
            this._root.classList.add('topbar-meshtastic--reconnecting');
            this._lampEl.setAttribute('aria-label', 'Dashboard reconnecting');
        }
    }

    setMeshtastic({ shortName, radio }) {
        const next = (shortName && String(shortName).trim())
            ? String(shortName).trim().toUpperCase()
            : '----';
        if (next !== this._lastCall) {
            this._lastCall = next;
            this._callEl.textContent = next;
            this._callEl.classList.remove('topbar-meshtastic__call--flicker');
            void this._callEl.offsetWidth;
            this._callEl.classList.add('topbar-meshtastic__call--flicker');
        }

        const r = radio || {};
        const region = r.region ? r.region : '--';
        const freq = r.frequency_mhz
            ? `${Number(r.frequency_mhz).toFixed(3)} MHz`
            : '--';
        const preset = this._formatPresetLabel(r.current_preset);

        this._regionEl.textContent = region;
        this._freqEl.textContent = freq;
        this._presetEl.textContent = preset;
        this._root.classList.toggle(
            'topbar-meshtastic--unknown',
            !radio || !radio.region,
        );
    }

    _formatPresetLabel(presetName) {
        if (!presetName) return 'Custom';
        const key = String(presetName);
        const labels = {
            LONG_FAST: 'LongFast',
            LONG_TURBO: 'LongTurbo',
            LONG_MODERATE: 'LongModerate',
            LONG_SLOW: 'LongSlow',
            VERY_LONG_SLOW: 'VeryLongSlow',
            MEDIUM_FAST: 'MediumFast',
            MEDIUM_SLOW: 'MediumSlow',
            SHORT_FAST: 'ShortFast',
            SHORT_SLOW: 'ShortSlow',
            SHORT_TURBO: 'ShortTurbo',
        };
        return labels[key] || key;
    }
}

window.TopbarMeshtasticChip = TopbarMeshtasticChip;
