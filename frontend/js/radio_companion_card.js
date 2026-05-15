/**
 * Radio tab — MeshCore Companion card.
 *
 * Renders companion radio status and a channel management table when a
 * USB MeshCore companion is connected. Channel keys are stored and
 * displayed as hex to match the MeshCore native app format.
 */
class RadioCompanionCard {
    constructor(api) {
        this._api = api;
        this._root = null;
        this._focusedRow = null;
    }

    mount(rootEl) {
        this._root = rootEl;
        rootEl.classList.add('r-card');
    }

    render(config) {
        const mc = config.meshcore || {};
        if (!mc.connected) {
            this._renderOffline();
            return;
        }
        this._renderOnline(mc);
    }

    _renderOffline() {
        this._root.innerHTML = `
            <div class="r-card__header">
                <h3 class="r-card__title">MeshCore Companion</h3>
                <span class="status-lamp status-lamp--off">
                    <span class="status-lamp__dot"></span>
                    <span class="status-lamp__label">NONE</span>
                </span>
            </div>
            <div class="companion-empty">
                Plug in a MeshCore USB companion (Heltec V3/V4, T-Beam, ...)
                and restart to enable MC messaging.
            </div>
        `;
    }

    _renderOnline(mc) {
        const radio = mc.radio || {};
        const name = this._api.escape(mc.companion_name || 'Connected');
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
                            <th>Key (Hex)</th>
                        </tr>
                    </thead>
                    <tbody id="r-mc-ch-body">
                        <tr class="ch-table__row ch-table__row--locked" data-index="0">
                            <td class="ch-table__idx">0</td>
                            <td>Public</td>
                            <td class="ch-table__psk-cell">&mdash;</td>
                        </tr>
                        ${channelRows}
                    </tbody>
                </table>
                <div class="r-card__actions">
                    <button class="r-btn r-btn--warn" id="r-mc-ch-delete"
                            style="display:none">Delete Channel</button>
                    <button class="r-btn r-btn--secondary" id="r-mc-ch-add">
                        + Add Channel
                    </button>
                    <button class="r-btn r-btn--primary" id="r-mc-ch-save">
                        Save Channels
                    </button>
                </div>
            </div>
            <div class="r-card__actions">
                <button class="r-btn r-btn--secondary" id="r-mc-advert">
                    Send Advert
                </button>
                <button class="r-btn r-btn--secondary" id="r-mc-refresh">
                    Refresh
                </button>
            </div>
        `;

        this._focusedRow = null;
        this._wire();
    }

    _buildChannelRows(channelKeys) {
        return channelKeys.map((ch, i) => {
            const idx = i + 1;
            const name = this._esc(ch.name || '');
            const keyHex = this._esc(ch.key_hex || '');
            return `
                <tr class="ch-table__row" data-index="${idx}">
                    <td class="ch-table__idx">${idx}</td>
                    <td>
                        <input class="ch-table__name-input" data-field="name"
                               value="${name}" placeholder="Channel name" />
                    </td>
                    <td class="ch-table__psk-cell">
                        <input class="ch-table__name-input" data-field="key_hex"
                               type="password" value="${keyHex}"
                               placeholder="32-char hex key" />
                        <button class="ch-table__reveal"
                                title="Show/hide key">&#128065;</button>
                    </td>
                </tr>
            `;
        }).join('');
    }

    _wire() {
        this._wireChannelHandlers(this._root);

        const addBtn = this._root.querySelector('#r-mc-ch-add');
        if (addBtn) addBtn.addEventListener('click', () => this._addEmptyRow());
        this._updateAddBtn();

        const saveBtn = this._root.querySelector('#r-mc-ch-save');
        if (saveBtn) saveBtn.addEventListener('click', () => this._saveChannels());

        const delBtn = this._root.querySelector('#r-mc-ch-delete');
        if (delBtn) {
            delBtn.addEventListener('mousedown', (e) => e.preventDefault());
            delBtn.addEventListener('click', () => this._deleteRow());
        }

        const advert = this._root.querySelector('#r-mc-advert');
        if (advert) {
            advert.addEventListener('click', async () => {
                advert.disabled = true;
                try {
                    const result = await this._api.post('/api/messages/advert', {});
                    if (result && result.success) {
                        this._api.toast('Advert sent');
                    } else if (result) {
                        this._api.toast(
                            'Advert failed' + (result.error ? `: ${result.error}` : ''),
                        );
                    }
                } finally {
                    advert.disabled = false;
                }
            });
        }

        const refresh = this._root.querySelector('#r-mc-refresh');
        if (refresh) refresh.addEventListener('click', () => this._api.refresh());
    }

    _wireChannelHandlers(scope) {
        scope.querySelectorAll('.ch-table__reveal').forEach((btn) => {
            btn.addEventListener('click', () => {
                const input = btn.closest('tr').querySelector('[data-field="key_hex"]');
                if (input) input.type = input.type === 'password' ? 'text' : 'password';
            });
        });

        scope.querySelectorAll(
            '.ch-table__row:not(.ch-table__row--locked) input',
        ).forEach((input) => {
            input.addEventListener('focus', () => {
                this._focusedRow = input.closest('tr');
                this._syncDeleteBtn();
            });
            input.addEventListener('blur', () => {
                setTimeout(() => {
                    const body = this._root.querySelector('#r-mc-ch-body');
                    if (body && !body.querySelector('input:focus')) {
                        this._focusedRow = null;
                        this._syncDeleteBtn();
                    }
                }, 0);
            });
        });
    }

    _syncDeleteBtn() {
        const btn = this._root.querySelector('#r-mc-ch-delete');
        if (btn) btn.style.display = this._focusedRow ? '' : 'none';
    }

    _MC_MAX_CHANNELS = 8;

    _updateAddBtn() {
        const btn = this._root.querySelector('#r-mc-ch-add');
        if (!btn) return;
        const tbody = this._root.querySelector('#r-mc-ch-body');
        const count = tbody
            ? tbody.querySelectorAll('tr:not(.ch-table__row--locked)').length
            : 0;
        const atLimit = count >= this._MC_MAX_CHANNELS;
        btn.disabled = atLimit;
        btn.title = atLimit ? 'Only 8 Channels Allowed' : '';
    }

    _addEmptyRow() {
        const tbody = this._root.querySelector('#r-mc-ch-body');
        const idx = tbody.querySelectorAll('tr').length;
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
                <input class="ch-table__name-input" data-field="key_hex"
                       type="password" value="" placeholder="32-char hex key" />
                <button class="ch-table__reveal"
                        title="Show/hide key">&#128065;</button>
            </td>
        `;
        this._wireChannelHandlers(tr);
        tbody.appendChild(tr);
        this._updateAddBtn();
    }

    _deleteRow() {
        if (!this._focusedRow) return;
        if (!confirm('Delete this channel?')) return;
        this._focusedRow.remove();
        this._focusedRow = null;
        this._syncDeleteBtn();
        this._updateAddBtn();
    }

    async _saveChannels() {
        const rows = this._root.querySelectorAll(
            '#r-mc-ch-body tr:not(.ch-table__row--locked)',
        );
        const channels = [];
        rows.forEach((row) => {
            const name = (row.querySelector('[data-field="name"]')?.value || '').trim();
            const keyHex = (row.querySelector('[data-field="key_hex"]')?.value || '').trim();
            if (name || keyHex) channels.push({ name, key_hex: keyHex });
        });

        const res = await this._api.put('/api/config/meshcore/channels', { channels });
        if (res) this._api.toast('MeshCore channels saved');
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
