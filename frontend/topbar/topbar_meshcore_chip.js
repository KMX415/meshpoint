/**
 * Topbar — MeshCore USB companion chip.
 *
 * Purple-grouped readout: companion online/offline lamp, device name,
 * frequency, and primary channel. Visible when meshcore_usb is in the
 * capture source list (from /api/config meshcore.companion_expected).
 *
 * Single responsibility: format meshcore status into the topbar DOM.
 */
class TopbarMeshcoreChip {
    constructor(groupEl, chipEl) {
        this._group = groupEl;
        this._root = chipEl;
        this._statusEl = chipEl.querySelector('.topbar-meshcore__status');
        this._nameEl = chipEl.querySelector('.topbar-meshcore__name');
        this._freqEl = chipEl.querySelector('.topbar-meshcore__freq');
        this._channelEl = chipEl.querySelector('.topbar-meshcore__channel');
        this._lampEl = chipEl.querySelector('.topbar-meshcore__lamp');
    }

    setMeshcore(meshcore) {
        const mc = meshcore || {};
        const expected = Boolean(mc.companion_expected);
        this._group.hidden = !expected;
        if (!expected) return;

        const connected = Boolean(mc.connected);
        this._setLamp(connected);

        const radio = mc.radio || {};
        this._nameEl.textContent = this._formatName(mc, connected);
        this._freqEl.textContent = this._formatFreq(radio.frequency_mhz);
        this._channelEl.textContent = this._formatChannel(mc.channel_keys);

        this._root.classList.toggle('topbar-meshcore--online', connected);
        this._root.classList.toggle('topbar-meshcore--offline', !connected);
    }

    _setLamp(connected) {
        this._lampEl.classList.remove(
            'topbar-meshcore__lamp--online',
            'topbar-meshcore__lamp--offline',
        );
        if (connected) {
            this._lampEl.classList.add('topbar-meshcore__lamp--online');
            this._statusEl.textContent = 'ONLINE';
        } else {
            this._lampEl.classList.add('topbar-meshcore__lamp--offline');
            this._statusEl.textContent = 'OFFLINE';
        }
    }

    _formatName(mc, connected) {
        const raw = (mc.companion_name || '').trim();
        if (raw) return raw;
        if (connected) return 'Companion';
        return 'No companion';
    }

    _formatFreq(mhz) {
        const n = Number(mhz);
        if (!n || Number.isNaN(n)) return '--';
        return `${n.toFixed(3)} MHz`;
    }

    _formatChannel(channelKeys) {
        const keys = Array.isArray(channelKeys) ? channelKeys : [];
        const names = keys
            .map((ch) => (ch && ch.name ? String(ch.name).trim() : ''))
            .filter(Boolean);
        if (names.length === 0) return 'Public';
        if (names.length === 1) return names[0];
        return `${names[0]} +${names.length - 1}`;
    }
}

window.TopbarMeshcoreChip = TopbarMeshcoreChip;
