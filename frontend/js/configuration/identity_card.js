/**
 * Configuration → Identity card.
 *
 * Single responsibility: edit the broadcast identity in local.yaml's
 * ``transmit`` block — long name (max 36), short name (max 4), and
 * an optional pinned Meshtastic node ID (hex). Surfaces the
 * ``node_id_source`` hint returned by /api/config so the user knows
 * whether the current ID is pinned, auto-derived, or random.
 *
 * Long and short name updates hot-reload on save. Node ID changes
 * require a service restart and trigger ``signalRestart``.
 */

class IdentityConfigCard {
    constructor(api) {
        this._api = api;
        this._root = null;
        this._initial = {};
    }

    mount(root) {
        this._root = root;
        this._root.innerHTML = `
            <article class="cfg-card" data-ident-card>
                <header class="cfg-card__head">
                    <h3 class="cfg-card__title">Identity</h3>
                    <p class="cfg-card__hint">
                        Long and short names hot-reload on save.
                        Pinning a node ID requires a service restart;
                        leave it blank to keep the current value
                        (auto-derived from the device ID by default).
                    </p>
                </header>
                <form class="cfg-form" data-ident-form>
                    <label class="cfg-field">
                        <span class="cfg-field__label">Long name</span>
                        <input class="cfg-field__input" type="text"
                               maxlength="36" data-ident-long
                               placeholder="Up to 36 characters">
                    </label>
                    <label class="cfg-field">
                        <span class="cfg-field__label">Short name</span>
                        <input class="cfg-field__input" type="text"
                               maxlength="4" data-ident-short
                               placeholder="Up to 4 characters">
                    </label>
                    <label class="cfg-field">
                        <span class="cfg-field__label">Pinned node ID (hex)</span>
                        <input class="cfg-field__input" type="text"
                               data-ident-node-id
                               placeholder="0xdeadbeef or deadbeef">
                    </label>
                    <p class="cfg-field__hint" data-ident-source-hint></p>
                    <div class="cfg-card__actions">
                        <button class="terminal-button terminal-button--primary"
                                type="submit">Save</button>
                    </div>
                    <p class="cfg-status" data-ident-status aria-live="polite"></p>
                </form>
            </article>
        `;
        this._form = this._root.querySelector('[data-ident-form]');
        this._longEl = this._root.querySelector('[data-ident-long]');
        this._shortEl = this._root.querySelector('[data-ident-short]');
        this._nodeIdEl = this._root.querySelector('[data-ident-node-id]');
        this._sourceHintEl = this._root.querySelector('[data-ident-source-hint]');
        this._statusEl = this._root.querySelector('[data-ident-status]');
        this._form.addEventListener('submit', (e) => this._onSubmit(e));
    }

    render(config) {
        const tx = (config && config.transmit) || {};
        const rawHex = tx.node_id_hex || '';
        const displayHex = rawHex.startsWith('!') ? `0x${rawHex.slice(1)}` : rawHex;
        this._initial = {
            long_name: tx.long_name || '',
            short_name: tx.short_name || '',
            node_id: tx.node_id != null ? Number(tx.node_id) : null,
            node_id_hex: displayHex,
            node_id_source: tx.node_id_source || '',
        };
        this._longEl.value = this._initial.long_name;
        this._shortEl.value = this._initial.short_name;
        this._nodeIdEl.value = this._initial.node_id_hex;
        this._sourceHintEl.textContent = this._sourceHint(this._initial.node_id_source);
    }

    _sourceHint(source) {
        if (source === 'config')  return 'Currently pinned in local.yaml.';
        if (source === 'derived') return 'Currently auto-derived from device ID. Pin a value here to override.';
        if (source === 'random')  return 'Currently random fallback (no device ID configured).';
        return '';
    }

    async _onSubmit(event) {
        event.preventDefault();

        const longName = this._longEl.value.trim();
        const shortName = this._shortEl.value.trim();
        const nodeIdRaw = this._nodeIdEl.value.trim();

        const body = {};
        if (longName !== this._initial.long_name) {
            if (longName.length > 36) {
                this._setStatus('error', 'Long name max 36 characters.');
                return;
            }
            body.long_name = longName;
        }
        if (shortName !== this._initial.short_name) {
            if (shortName.length > 4) {
                this._setStatus('error', 'Short name max 4 characters.');
                return;
            }
            body.short_name = shortName;
        }

        let nodeIdChanged = false;
        if (nodeIdRaw && nodeIdRaw !== this._initial.node_id_hex) {
            const parsed = this._parseHex(nodeIdRaw);
            if (parsed == null) {
                this._setStatus('error', 'Node ID must be hex (e.g. 0xdeadbeef).');
                return;
            }
            body.node_id = parsed;
            nodeIdChanged = parsed !== this._initial.node_id;
        }

        if (Object.keys(body).length === 0) {
            this._setStatus('', 'No changes.');
            return;
        }

        this._setStatus('pending', 'Saving…');
        const result = await this._api.put('/api/config/identity', body);
        if (!result) {
            this._setStatus('error', 'Save failed.');
            return;
        }

        this._setStatus('success', 'Saved.');
        if (nodeIdChanged || result.restart_required) {
            this._api.signalRestart('Identity updated.');
        } else {
            this._api.toast('Identity saved');
        }
        await this._api.refresh();
    }

    _parseHex(raw) {
        const cleaned = raw.replace(/^0x/i, '').trim();
        if (!/^[0-9a-fA-F]+$/.test(cleaned)) return null;
        const n = parseInt(cleaned, 16);
        if (!Number.isFinite(n) || n < 0 || n > 0xFFFFFFFF) return null;
        return n;
    }

    _setStatus(kind, message) {
        if (!this._statusEl) return;
        this._statusEl.dataset.kind = kind;
        this._statusEl.textContent = message;
    }
}

window.IdentityConfigCard = IdentityConfigCard;
