/**
 * Map SF + BW (and protocol) to a short preset key.
 * Keep in lockstep with PRESET_DISPLAY_NAMES in src/transmit/tx_service.py.
 */
class ModemPresetLabel {
    static KEYS = Object.freeze(['all', 'lf', 'mf', 'lt', 'mc']);

    static _SF_BW = Object.freeze({
        '11:250': { key: 'lf', chip: 'LF', name: 'LongFast' },
        '9:250': { key: 'mf', chip: 'MF', name: 'MediumFast' },
        '11:500': { key: 'lt', chip: 'LT', name: 'LongTurbo' },
    });

    static fromProtocolAndModem(protocol, spreadingFactor, bandwidthKhz) {
        if ((protocol || 'meshtastic') === 'meshcore') {
            return { key: 'mc', chip: 'MC', name: 'MeshCore' };
        }
        const sf = Number(spreadingFactor);
        const bw = Math.round(Number(bandwidthKhz));
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
        const key = preset ? preset.key : 'unknown';
        const badge = chip
            ? `<span class="node-marker__preset packet-chip packet-chip--${key}">${chip}</span>`
            : '';
        if (isMeshtastic) {
            return `<div class="node-marker-wrap${extraClass}">`
                + `<div class="node-marker__dot"></div>${badge}</div>`;
        }
        return `<div class="node-marker-wrap${extraClass}">`
            + `<div class="node-marker__diamond"></div>${badge}</div>`;
    }
}

window.ModemPresetLabel = ModemPresetLabel;
