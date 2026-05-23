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
        this._nameEl = chipEl.querySelector('.topbar-meshcore__name');
        this._freqEl = chipEl.querySelector('.topbar-meshcore__freq');
        this._channelEl = chipEl.querySelector('.topbar-meshcore__channel');
        this._lampEl = chipEl.querySelector('.topbar-meshcore__lamp');
        this._lastMc = null;
        this._dashboardReachable = false;
    }

    setMeshcore(meshcore) {
        this._lastMc = meshcore || {};
        this._paint();
    }

    /** When false, lamp shows reconnecting (API down); do not imply USB is up. */
    setDashboardReachable(reachable) {
        this._dashboardReachable = Boolean(reachable);
        this._paint();
    }

    _paint() {
        const mc = this._lastMc || {};
        const expected = Boolean(mc.companion_expected);
        this._group.hidden = !expected;
        if (!expected) return;

        const radio = mc.radio || {};
        const connected = Boolean(mc.connected);
        const showCompanion = this._dashboardReachable && connected;

        if (!this._dashboardReachable) {
            this._setLamp('reconnecting');
        } else {
            this._setLamp(connected ? 'online' : 'offline');
        }

        if (!this._dashboardReachable) {
            this._nameEl.textContent = 'Reconnecting…';
            this._freqEl.textContent = '--';
            this._channelEl.textContent = '--';
        } else {
            this._nameEl.textContent = this._formatName(mc, showCompanion);
            this._freqEl.textContent = this._formatFreq(radio.frequency_mhz);
            this._channelEl.textContent = this._formatChannel(mc.channel_keys);
        }

        this._root.classList.remove(
            'topbar-meshcore--online',
            'topbar-meshcore--offline',
            'topbar-meshcore--reconnecting',
        );
        if (!this._dashboardReachable) {
            this._root.classList.add('topbar-meshcore--reconnecting');
        } else if (connected) {
            this._root.classList.add('topbar-meshcore--online');
        } else {
            this._root.classList.add('topbar-meshcore--offline');
        }
    }

    _setLamp(state) {
        this._lampEl.classList.remove(
            'topbar-meshcore__lamp--online',
            'topbar-meshcore__lamp--offline',
            'topbar-meshcore__lamp--reconnecting',
        );
        const cls = `topbar-meshcore__lamp--${state}`;
        this._lampEl.classList.add(cls);
        const labels = {
            online: 'MeshCore companion connected',
            offline: 'MeshCore companion offline',
            reconnecting: 'MeshCore status unknown (dashboard reconnecting)',
        };
        this._lampEl.setAttribute('aria-label', labels[state] || labels.reconnecting);
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
