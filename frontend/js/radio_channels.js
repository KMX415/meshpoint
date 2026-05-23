/**
 * Channel configuration card for the Radio tab (observational, v0.7.4).
 *
 * Renders the Meshtastic channel table (name, masked PSK, computed
 * hash, enabled state) as a read-only telemetry view. Editing,
 * adding, and removing channels moved to Configuration → Channels
 * in v0.7.4; this card surfaces a deep-link there for muscle memory.
 */
class RadioChannels {
    constructor(containerEl) {
        this._container = containerEl;
        this._channels = [];
    }

    render(channels) {
        this._channels = channels || [];

        const rows = this._channels.map((ch) => {
            const name = ch.name && ch.name.trim()
                ? this._esc(ch.name)
                : '<span class="ch-table__name--empty">(unnamed)</span>';
            const enabledClass = ch.enabled
                ? 'ch-table__pill ch-table__pill--on'
                : 'ch-table__pill ch-table__pill--off';
            const enabledLabel = ch.enabled ? 'On' : 'Off';
            return `
                <tr class="ch-table__row">
                    <td class="ch-table__idx">${ch.index}</td>
                    <td class="ch-table__name">${name}</td>
                    <td class="ch-table__psk">${this._maskPsk(ch.psk_b64)}</td>
                    <td class="ch-table__hash">${ch.hash || '--'}</td>
                    <td><span class="${enabledClass}">${enabledLabel}</span></td>
                </tr>
            `;
        }).join('');

        const enabledCount = this._channels.filter((c) => c.enabled).length;

        this._container.classList.add('r-card', 'r-card--readout');
        this._container.innerHTML = `
            <div class="r-card__header">
                <h3 class="r-card__title">Channels</h3>
                <span class="r-card__subtitle">
                    ${this._channels.length} configured · ${enabledCount} on
                </span>
            </div>
            <table class="ch-table ch-table--readout">
                <thead>
                    <tr>
                        <th>#</th>
                        <th>Name</th>
                        <th>PSK</th>
                        <th>Hash</th>
                        <th>State</th>
                    </tr>
                </thead>
                <tbody>${rows || this._emptyRow()}</tbody>
            </table>
            <a class="r-config-link" href="#/configuration/channels">
                <span>Edit channels &amp; PSKs</span>
                <span aria-hidden="true">→</span>
            </a>
        `;
    }

    _emptyRow() {
        return `
            <tr class="ch-table__row ch-table__row--empty">
                <td colspan="5">No channels configured.</td>
            </tr>
        `;
    }

    _maskPsk(b64) {
        if (!b64) return '<span class="ch-table__psk--empty">none</span>';
        // Show length only; never reveal a stored key in an
        // observational view. The Configuration screen handles reveal.
        const len = b64.length;
        return `<span class="ch-table__psk--masked">•••••• <span>${len} chars</span></span>`;
    }

    _esc(str) {
        const el = document.createElement('span');
        el.textContent = str || '';
        return el.innerHTML;
    }
}
