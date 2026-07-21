/**
 * Topbar — Meshtastic USB serial device chip(s).
 *
 * One cyan badge per live serial capture source. Credit:
 * javastraat/meshpoint ``77cdaa2`` / ``7e0b863`` / ``0039adb``.
 */
class TopbarSerialChip {
    constructor(groupEl) {
        this._group = groupEl;
        this._lastDevices = [];
        this._dashboardReachable = false;
    }

    setSerial(devices) {
        this._lastDevices = Array.isArray(devices) ? devices : [];
        this._paint();
    }

    setDashboardReachable(reachable) {
        this._dashboardReachable = Boolean(reachable);
        this._paint();
    }

    _paint() {
        const list = this._lastDevices;
        this._group.hidden = list.length === 0;
        this._group.textContent = '';
        list.forEach((dev) => this._group.appendChild(this._buildBadge(dev)));
    }

    _buildBadge(dev) {
        const reachable = this._dashboardReachable;
        const connected = reachable && Boolean(dev.connected);
        const ownId = this._shortNodeId(dev.own_node_id_hex);
        const callText = !reachable ? '----' : (ownId || '----');

        const root = document.createElement('span');
        root.className = 'topbar-serial';
        if (!reachable) {
            root.classList.add('topbar-serial--reconnecting');
        } else if (!connected) {
            root.classList.add('topbar-serial--offline');
        }
        root.setAttribute(
            'aria-label',
            `Meshtastic USB ${ownId || 'device'} `
                + `${!reachable ? 'reconnecting' : (connected ? 'connected' : 'offline')}`,
        );

        const brand = document.createElement('span');
        brand.className = 'topbar-serial__brand';
        brand.textContent = 'Meshtastic';
        root.appendChild(brand);

        const lampState = !reachable ? 'reconnecting' : (connected ? 'online' : 'offline');
        const lamp = document.createElement('span');
        lamp.className = `topbar-serial__lamp topbar-serial__lamp--${lampState}`;
        lamp.setAttribute('role', 'status');
        const dot = document.createElement('span');
        dot.className = 'topbar-serial__dot';
        dot.setAttribute('aria-hidden', 'true');
        lamp.appendChild(dot);
        root.appendChild(lamp);

        const call = document.createElement('span');
        call.className = 'topbar-serial__call';
        call.textContent = ownId ? `!${ownId}` : callText;
        root.appendChild(call);

        root.appendChild(this._sep());
        const region = document.createElement('span');
        region.className = 'topbar-serial__region';
        region.textContent = (reachable && dev.region) ? String(dev.region) : '--';
        root.appendChild(region);

        root.appendChild(this._sep());
        const freq = document.createElement('span');
        freq.className = 'topbar-serial__freq';
        const mhz = Number(dev.frequency_mhz);
        freq.textContent = (reachable && mhz > 0)
            ? `${mhz.toFixed(3)} MHz`
            : '--';
        root.appendChild(freq);

        const sepBar = this._sep();
        sepBar.classList.add('topbar-serial__sep--bar');
        root.appendChild(sepBar);

        const preset = document.createElement('span');
        preset.className = 'topbar-serial__preset';
        preset.textContent = this._formatPreset(reachable ? dev.modem_preset : null);
        root.appendChild(preset);

        return root;
    }

    _sep() {
        const el = document.createElement('span');
        el.className = 'topbar-serial__sep';
        el.setAttribute('aria-hidden', 'true');
        el.textContent = '·';
        return el;
    }

    _shortNodeId(hex) {
        if (!hex) return null;
        const clean = String(hex).replace(/^!/, '').toLowerCase();
        if (!/^[0-9a-f]{8}$/.test(clean)) return null;
        return clean.slice(-4);
    }

    _formatPreset(name) {
        if (!name || name === 'CUSTOM') return 'Custom';
        const labels = {
            LONG_FAST: 'LongFast',
            LONG_SLOW: 'LongSlow',
            LONG_MODERATE: 'LongMod',
            LONG_TURBO: 'LongTurbo',
            MEDIUM_FAST: 'MediumFast',
            MEDIUM_SLOW: 'MediumSlow',
            SHORT_FAST: 'ShortFast',
            SHORT_SLOW: 'ShortSlow',
            SHORT_TURBO: 'ShortTurbo',
        };
        return labels[String(name)] || String(name);
    }
}

window.TopbarSerialChip = TopbarSerialChip;
