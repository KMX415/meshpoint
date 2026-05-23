/**
 * Radio tab — Identity card (observational, v0.7.4).
 *
 * Renders the Meshpoint's broadcast identity (long name, short name,
 * Meshtastic node ID) plus a hint explaining where the node ID came
 * from (pinned in local.yaml, auto-derived from device_id, or random
 * fallback).
 *
 * Editing moved to Configuration → Identity in v0.7.4. This card is
 * a status display only: read-only rows + a deep-link to the
 * Configuration screen so muscle memory still finds the editor.
 */
class RadioIdentityCard {
    constructor(api) {
        this._api = api;
        this._root = null;
    }

    mount(rootEl) {
        this._root = rootEl;
        rootEl.classList.add('r-card', 'r-card--readout');
        rootEl.innerHTML = `
            <div class="r-card__header">
                <h3 class="r-card__title">Identity</h3>
                <span class="r-badge r-badge--mono"
                      id="r-ident-source">--</span>
            </div>
            <div class="r-readout-grid">
                <div class="r-readout-row">
                    <span class="r-readout-row__label">Long</span>
                    <span class="r-readout-row__value r-readout-row__value--mono"
                          id="r-long-name">--</span>
                </div>
                <div class="r-readout-row">
                    <span class="r-readout-row__label">Short</span>
                    <span class="r-readout-row__value r-readout-row__value--mono"
                          id="r-short-name">--</span>
                </div>
                <div class="r-readout-row">
                    <span class="r-readout-row__label">Node ID</span>
                    <span class="r-readout-row__value r-readout-row__value--mono"
                          id="r-node-id">--</span>
                </div>
            </div>
            <p class="r-hint" id="r-ident-hint"></p>
            <a class="r-config-link" href="#/configuration/identity">
                <span>Edit identity</span>
                <span aria-hidden="true">→</span>
            </a>
        `;
    }

    render(config) {
        const tx = config.transmit || {};
        this._setText('#r-long-name', tx.long_name);
        this._setText('#r-short-name', tx.short_name);
        this._setText('#r-node-id', tx.node_id_hex);

        const source = tx.node_id_source;
        const badge = this._root.querySelector('#r-ident-source');
        badge.textContent = this._sourceLabel(source);

        const hint = this._root.querySelector('#r-ident-hint');
        hint.textContent = this._sourceHint(source);
    }

    _setText(selector, value) {
        const el = this._root.querySelector(selector);
        if (!el) return;
        if (value == null || value === '') {
            el.textContent = '--';
            el.classList.add('r-readout-row__value--empty');
        } else {
            el.textContent = value;
            el.classList.remove('r-readout-row__value--empty');
        }
    }

    _sourceLabel(source) {
        if (source === 'config') return 'PINNED';
        if (source === 'derived') return 'AUTO';
        if (source === 'random') return 'RANDOM';
        return 'UNSET';
    }

    _sourceHint(source) {
        if (source === 'config') {
            return 'Pinned in local.yaml.';
        }
        if (source === 'derived') {
            return 'Auto-derived from device ID. Stable across reboots.';
        }
        if (source === 'random') {
            return 'Random fallback (no device ID configured).';
        }
        return '';
    }
}

window.RadioIdentityCard = RadioIdentityCard;
