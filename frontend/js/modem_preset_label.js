/**
 * Map SF + BW (and protocol) to a short preset key.
 * Keep in lockstep with PRESET_DISPLAY_NAMES in src/transmit/tx_service.py.
 */
class ModemPresetLabel {
    static CATALOG = Object.freeze([
        { key: 'sf', chip: 'SF', name: 'ShortFast', sf: 7, bw: 250, tone: 'short' },
        { key: 'st', chip: 'ST', name: 'ShortTurbo', sf: 7, bw: 500, tone: 'short' },
        { key: 'ss', chip: 'SS', name: 'ShortSlow', sf: 8, bw: 250, tone: 'short' },
        { key: 'mf', chip: 'MF', name: 'MediumFast', sf: 9, bw: 250, tone: 'medium' },
        { key: 'ms', chip: 'MS', name: 'MediumSlow', sf: 10, bw: 250, tone: 'medium' },
        { key: 'lf', chip: 'LF', name: 'LongFast', sf: 11, bw: 250, tone: 'long' },
        { key: 'lt', chip: 'LT', name: 'LongTurbo', sf: 11, bw: 500, tone: 'turbo' },
        { key: 'lm', chip: 'LM', name: 'LongMod', sf: 11, bw: 125, tone: 'long' },
        { key: 'ls', chip: 'LS', name: 'LongSlow', sf: 12, bw: 125, tone: 'long' },
        { key: 'vl', chip: 'VL', name: 'VeryLongSlow', sf: 12, bw: 62, tone: 'vlong' },
        { key: 'mc', chip: 'MC', name: 'MeshCore', sf: null, bw: null, tone: 'mc' },
    ]);

    static _BY_KEY = Object.freeze(Object.fromEntries(
        ModemPresetLabel.CATALOG.map((row) => [row.key, row]),
    ));

    static _SF_BW = Object.freeze(Object.fromEntries(
        ModemPresetLabel.CATALOG
            .filter((row) => row.sf != null)
            .map((row) => [`${row.sf}:${row.bw}`, row]),
    ));

    static FILTER_KEYS = Object.freeze([
        'all',
        ...ModemPresetLabel.CATALOG.map((row) => row.key),
    ]);

    static chipForKey(key) {
        if (key === 'all') return 'All';
        const row = ModemPresetLabel._BY_KEY[key];
        return row ? row.chip : '--';
    }

    static isFilterKey(key) {
        return ModemPresetLabel.FILTER_KEYS.includes(key);
    }

    static _bwKey(bandwidthKhz) {
        const bw = Number(bandwidthKhz);
        if (!Number.isFinite(bw)) return NaN;
        if (bw >= 62 && bw < 63.5) return 62;
        return Math.round(bw);
    }

    static fromProtocolAndModem(protocol, spreadingFactor, bandwidthKhz) {
        if ((protocol || 'meshtastic') === 'meshcore') {
            return ModemPresetLabel._BY_KEY.mc;
        }
        const sf = Number(spreadingFactor);
        const bw = ModemPresetLabel._bwKey(bandwidthKhz);
        if (!Number.isFinite(sf) || !Number.isFinite(bw)) return null;
        return ModemPresetLabel._SF_BW[`${sf}:${bw}`] || null;
    }

    static fromPacket(packet) {
        if (!packet) return null;
        const sig = packet.signal || {};
        return ModemPresetLabel.fromProtocolAndModem(
            packet.protocol,
            sig.spreading_factor ?? packet.spreading_factor,
            sig.bandwidth_khz ?? packet.bandwidth_khz,
        );
    }

    static fromNode(node) {
        if (!node) return null;
        return ModemPresetLabel.fromProtocolAndModem(
            node.protocol,
            node.latest_spreading_factor,
            node.latest_bandwidth_khz,
        );
    }

    static markerMarkup(preset, isMeshtastic, extraClass) {
        const chip = preset ? preset.chip : '';
        const tone = preset ? preset.tone : 'unknown';
        const badge = chip
            ? `<span class="node-marker__preset packet-chip packet-chip--${tone}">${chip}</span>`
            : '';
        const shape = isMeshtastic ? 'node-marker__dot' : 'node-marker__diamond';
        return `<div class="node-marker-wrap${extraClass}">`
            + `<div class="${shape}"></div>${badge}</div>`;
    }
}

window.ModemPresetLabel = ModemPresetLabel;
