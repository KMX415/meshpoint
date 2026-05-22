/**
 * Configuration → Channels card.
 *
 * Single responsibility: edit the Meshtastic channel list (primary
 * channel name plus up to seven additional channels with name,
 * base64 PSK, and enabled flag). Channel hashes are computed
 * server-side and shown read-only after save.
 *
 * Encryption keys are masked with type=password by default; an
 * eye-icon button reveals one row at a time. PUTs /api/config/channels
 * which applies at runtime with no service restart.
 */

class ChannelsConfigCard {
    constructor(api) {
        this._api = api;
        this._root = null;
        this._focusedRow = null;
        this._channels = [];
    }

    mount(root) {
        this._root = root;
        this._root.innerHTML = `
            <article class="cfg-card" data-ch-card>
                <header class="cfg-card__head">
                    <h3 class="cfg-card__title">Channels</h3>
                    <p class="cfg-card__hint">
                        Channel 0 is your primary channel; only its
                        name is editable. Additional channels are
                        decryption keys: paste the base64 PSK from
                        the Meshtastic mobile app and the hash will
                        recompute server-side. Save applies at
                        runtime with no service restart.
                    </p>
                </header>
                <div class="cfg-mc-channels">
                    <table class="ch-table">
                        <colgroup>
                            <col class="ch-table__col-idx" />
                            <col class="ch-table__col-name" />
                            <col class="ch-table__col-psk" />
                            <col class="ch-table__col-hash" />
                            <col class="ch-table__col-state" />
                        </colgroup>
                        <thead>
                            <tr>
                                <th>#</th>
                                <th>Name</th>
                                <th>PSK (base64)</th>
                                <th>Hash</th>
                                <th>State</th>
                            </tr>
                        </thead>
                        <tbody data-ch-body></tbody>
                    </table>
                </div>
                <div class="cfg-card__actions">
                    <button class="terminal-button terminal-button--danger"
                            type="button" data-ch-delete style="display:none">
                        Delete Channel
                    </button>
                    <button class="terminal-button" type="button" data-ch-add>
                        + Add Channel
                    </button>
                    <button class="terminal-button terminal-button--primary"
                            type="button" data-ch-save>
                        Save Channels
                    </button>
                </div>
                <p class="cfg-status" data-ch-status aria-live="polite"></p>
            </article>
        `;
        this._tbody = this._root.querySelector('[data-ch-body]');
        this._statusEl = this._root.querySelector('[data-ch-status]');
        this._wireToolbar();
    }

    render(config) {
        const channels = (config && config.channels) || [];
        this._channels = channels;
        this._renderRows();
    }

    _renderRows() {
        const rows = this._channels.map((ch) => this._rowHtml(ch)).join('');
        this._tbody.innerHTML = rows || this._emptyRow();
        this._focusedRow = null;
        this._wireRowHandlers(this._tbody);
        this._syncDeleteBtn();
        this._updateAddBtn();
    }

    _rowHtml(ch) {
        const idx = ch.index;
        const isPrimary = idx === 0;
        const name = this._esc(ch.name || '');
        const psk = this._esc(ch.psk_b64 || '');
        const hash = ch.hash || '--';
        const enabled = ch.enabled !== false;
        const checked = enabled ? 'checked' : '';
        const lockedClass = isPrimary ? ' ch-table__row--locked' : '';
        const pskCell = isPrimary
            ? `
                <td class="ch-table__psk-cell">
                    <div class="ch-table__psk-inner">
                        <span class="ch-table__psk-label">primary</span>
                    </div>
                </td>
            `
            : `
                <td class="ch-table__psk-cell">
                    <div class="ch-table__psk-inner">
                        <input class="ch-table__name-input" data-field="psk_b64"
                               type="password" value="${psk}"
                               placeholder="base64 PSK" />
                        <button class="ch-table__reveal" type="button"
                                title="Show/hide key">&#128065;</button>
                    </div>
                </td>
            `;
        const enabledCell = isPrimary
            ? '<td><span class="ch-table__pill ch-table__pill--on">On</span></td>'
            : `
                <td>
                    <label class="ch-table__toggle">
                        <input type="checkbox" data-field="enabled" ${checked} />
                        <span>${enabled ? 'On' : 'Off'}</span>
                    </label>
                </td>
            `;
        return `
            <tr class="ch-table__row${lockedClass}" data-index="${idx}">
                <td class="ch-table__idx">${idx}</td>
                <td>
                    <input class="ch-table__name-input" data-field="name"
                           value="${name}" placeholder="Channel name" />
                </td>
                ${pskCell}
                <td class="ch-table__hash">${hash}</td>
                ${enabledCell}
            </tr>
        `;
    }

    _emptyRow() {
        return `
            <tr class="ch-table__row ch-table__row--empty">
                <td colspan="5">No channels configured.</td>
            </tr>
        `;
    }

    _wireToolbar() {
        const addBtn = this._root.querySelector('[data-ch-add]');
        if (addBtn) addBtn.addEventListener('click', () => this._addEmptyRow());

        const saveBtn = this._root.querySelector('[data-ch-save]');
        if (saveBtn) saveBtn.addEventListener('click', () => this._saveChannels());

        const delBtn = this._root.querySelector('[data-ch-delete]');
        if (delBtn) {
            delBtn.addEventListener('mousedown', (e) => e.preventDefault());
            delBtn.addEventListener('click', () => this._deleteRow());
        }
    }

    _wireRowHandlers(scope) {
        scope.querySelectorAll('.ch-table__reveal').forEach((btn) => {
            btn.addEventListener('click', () => {
                const input = btn.closest('tr').querySelector('[data-field="psk_b64"]');
                if (input) input.type = input.type === 'password' ? 'text' : 'password';
            });
        });

        scope.querySelectorAll('.ch-table__toggle input[type="checkbox"]').forEach((cb) => {
            cb.addEventListener('change', () => {
                const label = cb.closest('label')?.querySelector('span');
                if (label) label.textContent = cb.checked ? 'On' : 'Off';
            });
        });

        scope.querySelectorAll('.ch-table__row:not(.ch-table__row--locked) input').forEach((input) => {
            input.addEventListener('focus', () => {
                this._focusedRow = input.closest('tr');
                this._syncDeleteBtn();
            });
            input.addEventListener('blur', () => {
                setTimeout(() => {
                    if (!this._tbody.querySelector('input:focus')) {
                        this._focusedRow = null;
                        this._syncDeleteBtn();
                    }
                }, 0);
            });
        });
    }

    _syncDeleteBtn() {
        const btn = this._root.querySelector('[data-ch-delete]');
        if (btn) btn.style.display = this._focusedRow ? '' : 'none';
    }

    _MT_MAX_CHANNELS = 8;

    _updateAddBtn() {
        const btn = this._root.querySelector('[data-ch-add]');
        if (!btn) return;
        const count = this._tbody.querySelectorAll('tr.ch-table__row:not(.ch-table__row--empty)').length;
        const atLimit = count >= this._MT_MAX_CHANNELS;
        btn.disabled = atLimit;
        btn.title = atLimit ? `Only ${this._MT_MAX_CHANNELS} channels allowed` : '';
    }

    _addEmptyRow() {
        const empty = this._tbody.querySelector('tr.ch-table__row--empty');
        if (empty) empty.remove();
        const idx = this._tbody.querySelectorAll('tr').length;
        if (idx >= this._MT_MAX_CHANNELS) return;
        const tr = document.createElement('tr');
        tr.className = 'ch-table__row';
        tr.dataset.index = idx;
        tr.innerHTML = `
            <td class="ch-table__idx">${idx}</td>
            <td>
                <input class="ch-table__name-input" data-field="name"
                       value="" placeholder="Channel name" />
            </td>
            <td class="ch-table__psk-cell">
                <div class="ch-table__psk-inner">
                    <input class="ch-table__name-input" data-field="psk_b64"
                           type="password" value="" placeholder="base64 PSK" />
                    <button class="ch-table__reveal" type="button"
                            title="Show/hide key">&#128065;</button>
                </div>
            </td>
            <td class="ch-table__hash">--</td>
            <td>
                <label class="ch-table__toggle">
                    <input type="checkbox" data-field="enabled" checked />
                    <span>On</span>
                </label>
            </td>
        `;
        this._wireRowHandlers(tr);
        this._tbody.appendChild(tr);
        this._updateAddBtn();
    }

    _deleteRow() {
        if (!this._focusedRow) return;
        if (!confirm('Delete this channel?')) return;
        this._focusedRow.remove();
        this._focusedRow = null;
        this._reindexRows();
        this._syncDeleteBtn();
        this._updateAddBtn();
    }

    _reindexRows() {
        const rows = this._tbody.querySelectorAll('tr.ch-table__row:not(.ch-table__row--empty)');
        rows.forEach((row, i) => {
            row.dataset.index = i;
            const idxCell = row.querySelector('.ch-table__idx');
            if (idxCell) idxCell.textContent = i;
        });
    }

    async _saveChannels() {
        const rows = this._tbody.querySelectorAll('tr.ch-table__row:not(.ch-table__row--empty)');
        const channels = [];
        rows.forEach((row) => {
            const idx = Number(row.dataset.index);
            const name = (row.querySelector('[data-field="name"]')?.value || '').trim();
            const pskInput = row.querySelector('[data-field="psk_b64"]');
            const enabledInput = row.querySelector('[data-field="enabled"]');
            const psk = pskInput ? (pskInput.value || '').trim() : '';
            const enabled = enabledInput ? !!enabledInput.checked : true;
            channels.push({ index: idx, name, psk_b64: psk, enabled });
        });

        this._setStatus('pending', 'Saving…');
        const res = await this._api.put('/api/config/channels', { channels });
        if (res) {
            this._setStatus('success', 'Channels saved.');
            this._api.toast('Channels saved');
            await this._api.refresh();
        } else {
            this._setStatus('error', 'Save failed.');
        }
    }

    _setStatus(kind, message) {
        if (!this._statusEl) return;
        this._statusEl.dataset.kind = kind;
        this._statusEl.textContent = message;
    }

    _esc(str) {
        const el = document.createElement('span');
        el.textContent = str || '';
        return el.innerHTML;
    }
}

window.ChannelsConfigCard = ChannelsConfigCard;
