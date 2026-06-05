/**
 * Radio tab — MeshCore Companion readout (observational only).
 *
 * Per the v0.7.4 IA refactor (see docs/plans/v0.7.4-tests/foundation.md
 * Section 5), the top-level Radio page is now strictly observational.
 * All editable MeshCore controls (channel keys, Send Advert, manual
 * Refresh) live under Configuration > MeshCore. This card renders the
 * companion radio readouts plus a read-only list of channel names and
 * deep-links to the Configuration editor for any change the user wants
 * to make.
 */
class RadioCompanionCard {
    constructor(api) {
        this._api = api;
        this._root = null;
    }

    mount(rootEl) {
        this._root = rootEl;
        rootEl.classList.add('r-card', 'r-card--readout');
    }

    render(config) {
        const mc = config.meshcore || {};
        if (!mc.connected) {
            this._renderOffline(config);
            return;
        }
        this._renderOnline(mc);
    }

    _renderOffline(config) {
        const tx = (config && config.transmit) || {};
        const mc = (config && config.meshcore) || {};
        const transmitOff = !tx.enabled || mc.status_note === 'transmit_disabled';
        const body = transmitOff
            ? `Native TX is disabled under
                <a class="r-config-link" href="#/configuration/transmit">Configuration → Transmit</a>.
                Enable it and restart to show companion status here. USB capture may
                still be receiving MeshCore packets in the background.`
            : `Plug in a MeshCore USB companion (Heltec V3/V4, T-Beam, ...)
                and restart to enable MC messaging.`;
        this._root.innerHTML = `
            <div class="r-card__header">
                <h3 class="r-card__title">MeshCore Companion</h3>
                <span class="status-lamp status-lamp--off">
                    <span class="status-lamp__dot"></span>
                    <span class="status-lamp__label">NONE</span>
                </span>
            </div>
            <div class="companion-empty">${body}</div>
        `;
    }

    _renderOnline(mc) {
        const radio = mc.radio || {};
        const name = this._esc(mc.companion_name || 'Connected');
        const channelRows = this._buildChannelRows(mc.channel_keys || []);

        this._root.innerHTML = `
            <div class="r-card__header">
                <h3 class="r-card__title">MeshCore Companion</h3>
                <span class="status-lamp status-lamp--ready">
                    <span class="status-lamp__dot"></span>
                    <span class="status-lamp__label">${name}</span>
                </span>
            </div>
            <div class="companion-grid">
                <div class="r-readout">
                    <span class="r-readout__label">Frequency</span>
                    <span class="r-readout__value">
                        ${this._fmtFreq(radio.frequency_mhz)}
                    </span>
                </div>
                <div class="r-readout">
                    <span class="r-readout__label">Bandwidth</span>
                    <span class="r-readout__value">
                        ${this._fmtBw(radio.bandwidth_khz)}
                    </span>
                </div>
                <div class="r-readout">
                    <span class="r-readout__label">SF</span>
                    <span class="r-readout__value">
                        ${this._fmtSf(radio.spreading_factor)}
                    </span>
                </div>
                <div class="r-readout">
                    <span class="r-readout__label">TX Power</span>
                    <span class="r-readout__value">
                        ${this._fmtTxPower(radio.tx_power)}
                    </span>
                </div>
            </div>
            <div class="companion-channels">
                <table class="ch-table">
                    <thead>
                        <tr>
                            <th>#</th>
                            <th>Name</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr class="ch-table__row ch-table__row--locked">
                            <td class="ch-table__idx">0</td>
                            <td>Public</td>
                        </tr>
                        ${channelRows}
                    </tbody>
                </table>
                <a class="r-config-link" href="#/configuration/meshcore">
                    <span>Configure MeshCore channels</span>
                    <span aria-hidden="true">&rarr;</span>
                </a>
            </div>
        `;
    }

    _buildChannelRows(channelKeys) {
        return channelKeys.map((ch, i) => {
            const idx = i + 1;
            const displayName = (ch.name || '').trim() || '(unnamed)';
            const name = this._esc(displayName);
            return `
                <tr class="ch-table__row ch-table__row--locked">
                    <td class="ch-table__idx">${idx}</td>
                    <td>${name}</td>
                </tr>
            `;
        }).join('');
    }

    _fmtFreq(v)    { return v ? `${v} MHz` : '--'; }
    _fmtBw(v)      { return v ? `${v} kHz` : '--'; }
    _fmtSf(v)      { return v ? `SF${v}` : '--'; }
    _fmtTxPower(v) { return v != null ? `${v} dBm` : '--'; }

    _esc(str) {
        const el = document.createElement('span');
        el.textContent = str || '';
        return el.innerHTML;
    }
}

window.RadioCompanionCard = RadioCompanionCard;
