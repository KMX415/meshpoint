/**
 * Configuration → MeshCore card.
 *
 * Single responsibility: edit the MeshCore companion channel keys
 * (stored as hex to match the MeshCore native app format) and
 * surface the two on-demand companion actions, Send Advert and
 * Refresh. Companion radio readouts (frequency / bandwidth / SF /
 * TX power) are shown for context but are read-only here.
 *
 * The top-level Radio page renders the same readouts plus a
 * deep-link to this card per the v0.7.4 IA refactor.
 */

class MeshcoreConfigCard {
    constructor(api) {
        this._api = api;
        this._root = null;
        this._focusedRow = null;
    }

    mount(root) {
        this._root = root;
        this._root.innerHTML = `
            <div class="cfg-section" data-mc-root>
                <article class="cfg-card">
                    <header class="cfg-card__head">
                        <h3 class="cfg-card__title">USB capture source</h3>
                        <p class="cfg-card__hint">
                            Enable the MeshCore USB companion serial source (Heltec, T-Beam, etc.).
                            Requires a service restart after changes.
                        </p>
                    </header>
                    <form class="cfg-form" data-mc-usb-form>
                        <label class="cfg-field cfg-field--toggle">
                            <input type="checkbox" data-mc-usb-enable>
                            <span class="cfg-field__label">Include meshcore_usb capture source</span>
                        </label>
                        <label class="cfg-field cfg-field--toggle">
                            <input type="checkbox" data-mc-usb-autodetect checked>
                            <span class="cfg-field__label">Auto-detect serial port</span>
                        </label>
                        <label class="cfg-field">
                            <span class="cfg-field__label">Pinned serial port</span>
                            <input class="cfg-field__input" type="text"
                                   placeholder="/dev/ttyACM0" data-mc-usb-port>
                        </label>
                        <label class="cfg-field cfg-field--narrow">
                            <span class="cfg-field__label">Baud rate</span>
                            <input class="cfg-field__input" type="number" data-mc-usb-baud>
                        </label>
                        <div class="cfg-card__actions">
                            <button class="terminal-button terminal-button--primary"
                                    type="submit">Save USB source</button>
                        </div>
                        <p class="cfg-status" data-mc-usb-status aria-live="polite"></p>
                    </form>
                </article>
                <article class="cfg-card" data-mc-card>
                    <header class="cfg-card__head">
                        <h3 class="cfg-card__title">MeshCore Companion</h3>
                        <p class="cfg-card__hint">
                            Channel keys for the USB companion. Keys are hex to match the
                            MeshCore native app. Channel save applies at runtime.
                        </p>
                    </header>
                    <div data-mc-body></div>
                    <p class="cfg-status" data-mc-status aria-live="polite"></p>
                </article>
            </div>
        `;
        this._body = this._root.querySelector('[data-mc-body]');
        this._statusEl = this._root.querySelector('[data-mc-status]');
        this._usbForm = this._root.querySelector('[data-mc-usb-form]');
        this._usbForm.addEventListener('submit', (e) => this._saveUsbSource(e));
    }

    render(config) {
        const cap = config.capture || {};
        const mcUsb = cap.meshcore_usb || {};
        const sources = cap.sources || [];
        const enableEl = this._root.querySelector('[data-mc-usb-enable]');
        const autodetectEl = this._root.querySelector('[data-mc-usb-autodetect]');
        const portEl = this._root.querySelector('[data-mc-usb-port]');
        const baudEl = this._root.querySelector('[data-mc-usb-baud]');
        if (enableEl) enableEl.checked = sources.includes('meshcore_usb');
        if (autodetectEl) autodetectEl.checked = mcUsb.auto_detect !== false;
        if (portEl) portEl.value = mcUsb.serial_port || '';
        if (baudEl && mcUsb.baud_rate != null) baudEl.value = mcUsb.baud_rate;

        const mc = (config && config.meshcore) || {};
        if (!mc.connected) {
            this._renderOffline(config);
            return;
        }
        this._renderOnline(mc);
    }

    async _saveUsbSource(event) {
        event.preventDefault();
        const status = this._root.querySelector('[data-mc-usb-status]');
        status.dataset.kind = 'pending';
        status.textContent = 'Saving…';
        const result = await this._api.put('/api/config/capture/meshcore-usb', {
            enable_source: this._root.querySelector('[data-mc-usb-enable]').checked,
            auto_detect: this._root.querySelector('[data-mc-usb-autodetect]').checked,
            serial_port: this._root.querySelector('[data-mc-usb-port]').value.trim(),
            baud_rate: Number(this._root.querySelector('[data-mc-usb-baud]').value),
        });
        if (result) {
            status.dataset.kind = 'success';
            status.textContent = 'Saved.';
            if (result.restart_required) {
                this._api.signalRestart('MeshCore USB source updated.');
            } else {
                this._api.toast('MeshCore USB source updated');
            }
            await this._api.refresh();
        } else {
            status.dataset.kind = 'error';
            status.textContent = 'Save failed.';
        }
    }

    _renderOffline(config) {
        const tx = (config && config.transmit) || {};
        const mc = (config && config.meshcore) || {};
        const transmitOff = !tx.enabled || mc.status_note === 'transmit_disabled';
        const transmitCallout = transmitOff ? `
            <p class="cfg-callout">
                <strong>Native TX is disabled.</strong>
                Enable it under
                <a class="cfg-inline-link" href="#/configuration/transmit">Configuration → Transmit</a>,
                then restart the service. Until then this card cannot query the
                USB companion, even if USB capture is already receiving packets.
            </p>
        ` : '';
        this._body.innerHTML = `
            ${transmitCallout}
            <div class="cfg-empty">
                <div class="cfg-empty__title">No companion connected</div>
                <p class="cfg-empty__body">
                    Enable the USB capture source above, plug in a companion
                    (Heltec V3/V4, T-Beam, ...), then restart the service.
                </p>
            </div>
        `;
        this._setStatus('', '');
    }

    _renderOnline(mc) {
        const radio = mc.radio || {};
        const name = this._esc(mc.companion_name || 'Connected');
        const nameValue = this._esc(mc.companion_name || '');
        const channelRows = this._buildChannelRows(mc.channel_keys || []);

        this._body.innerHTML = `
            <div class="cfg-mc-status">
                <span class="cfg-mc-status__lamp" aria-hidden="true"></span>
                <span class="cfg-mc-status__name">${name}</span>
            </div>
            <div class="cfg-mc-identity" data-mc-identity>
                <label class="cfg-field cfg-field--inline">
                    <span class="cfg-field__label">Companion name</span>
                    <input class="cfg-field__input" type="text"
                           data-mc-name maxlength="32"
                           value="${nameValue}"
                           placeholder="My Meshpoint"
                           aria-describedby="mc-name-hint">
                </label>
                <p class="cfg-field__hint" id="mc-name-hint">
                    Identity on the mesh is advert packets, so renaming
                    only updates neighbors after the next advert. Send one
                    automatically after save with the checkbox below.
                </p>
                <label class="cfg-field cfg-field--toggle">
                    <input type="checkbox" data-mc-name-advert checked>
                    <span class="cfg-field__label">
                        Send advert after save
                    </span>
                </label>
                <div class="cfg-card__actions">
                    <button class="terminal-button terminal-button--primary"
                            type="button" data-mc-name-save>
                        Save Name
                    </button>
                </div>
                <p class="cfg-status" data-mc-name-status aria-live="polite"></p>
            </div>
            <div class="cfg-mc-readouts">
                <div class="cfg-mc-readout">
                    <span class="cfg-mc-readout__label">Frequency</span>
                    <span class="cfg-mc-readout__value">${this._fmtFreq(radio.frequency_mhz)}</span>
                </div>
                <div class="cfg-mc-readout">
                    <span class="cfg-mc-readout__label">Bandwidth</span>
                    <span class="cfg-mc-readout__value">${this._fmtBw(radio.bandwidth_khz)}</span>
                </div>
                <div class="cfg-mc-readout">
                    <span class="cfg-mc-readout__label">SF</span>
                    <span class="cfg-mc-readout__value">${this._fmtSf(radio.spreading_factor)}</span>
                </div>
                <div class="cfg-mc-readout">
                    <span class="cfg-mc-readout__label">TX Power</span>
                    <span class="cfg-mc-readout__value">${this._fmtTxPower(radio.tx_power)}</span>
                </div>
            </div>
            <div class="cfg-mc-channels">
                <table class="ch-table">
                    <thead>
                        <tr>
                            <th>#</th>
                            <th>Name</th>
                            <th>Key (Hex)</th>
                        </tr>
                    </thead>
                    <tbody data-mc-channels-body>
                        <tr class="ch-table__row ch-table__row--locked" data-index="0">
                            <td class="ch-table__idx">0</td>
                            <td>Public</td>
                            <td class="ch-table__psk-cell">&mdash;</td>
                        </tr>
                        ${channelRows}
                    </tbody>
                </table>
            </div>
            <div class="cfg-card__actions cfg-mc-toolbar">
                <button class="terminal-button terminal-button--danger"
                        type="button" data-mc-delete style="display:none">
                    Delete Channel
                </button>
                <button class="terminal-button" type="button" data-mc-add>
                    + Add Channel
                </button>
                <button class="terminal-button terminal-button--primary"
                        type="button" data-mc-save>
                    Save Channels
                </button>
                <button class="terminal-button" type="button" data-mc-advert>
                    Send Advert
                </button>
                <button class="terminal-button" type="button" data-mc-refresh>
                    Refresh
                </button>
            </div>
        `;
        this._focusedRow = null;
        this._wire();
        this._updateAddBtn();
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
                               placeholder="32-char hex (empty = hashtag)" />
                        <button class="ch-table__reveal" type="button"
                                title="Show/hide key">&#128065;</button>
                    </td>
                </tr>
            `;
        }).join('');
    }

    _wire() {
        this._wireChannelHandlers(this._body);

        const addBtn = this._body.querySelector('[data-mc-add]');
        if (addBtn) addBtn.addEventListener('click', () => this._addEmptyRow());

        const saveBtn = this._body.querySelector('[data-mc-save]');
        if (saveBtn) saveBtn.addEventListener('click', () => this._saveChannels());

        const delBtn = this._body.querySelector('[data-mc-delete]');
        if (delBtn) {
            delBtn.addEventListener('mousedown', (e) => e.preventDefault());
            delBtn.addEventListener('click', () => this._deleteRow());
        }

        const advert = this._body.querySelector('[data-mc-advert]');
        if (advert) advert.addEventListener('click', () => this._sendAdvert(advert));

        const refresh = this._body.querySelector('[data-mc-refresh]');
        if (refresh) refresh.addEventListener('click', () => this._api.refresh());

        const saveName = this._body.querySelector('[data-mc-name-save]');
        if (saveName) {
            saveName.addEventListener('click', () => this._saveCompanionName(saveName));
        }
    }

    _wireChannelHandlers(scope) {
        scope.querySelectorAll('.ch-table__reveal').forEach((btn) => {
            btn.addEventListener('click', () => {
                const input = btn.closest('tr').querySelector('[data-field="key_hex"]');
                if (input) input.type = input.type === 'password' ? 'text' : 'password';
            });
        });

        scope.querySelectorAll('.ch-table__row:not(.ch-table__row--locked) input').forEach((input) => {
            input.addEventListener('focus', () => {
                this._focusedRow = input.closest('tr');
                this._syncDeleteBtn();
            });
            input.addEventListener('blur', () => {
                setTimeout(() => {
                    const tbody = this._body.querySelector('[data-mc-channels-body]');
                    if (tbody && !tbody.querySelector('input:focus')) {
                        this._focusedRow = null;
                        this._syncDeleteBtn();
                    }
                }, 0);
            });
        });
    }

    _syncDeleteBtn() {
        const btn = this._body.querySelector('[data-mc-delete]');
        if (btn) btn.style.display = this._focusedRow ? '' : 'none';
    }

    // Device has 8 slots: 0 = Public (locked row), 1–7 = user channels.
    _MC_MAX_USER_CHANNELS = 7;

    _updateAddBtn() {
        const btn = this._body.querySelector('[data-mc-add]');
        if (!btn) return;
        const tbody = this._body.querySelector('[data-mc-channels-body]');
        const count = tbody
            ? tbody.querySelectorAll('tr:not(.ch-table__row--locked)').length
            : 0;
        const atLimit = count >= this._MC_MAX_USER_CHANNELS;
        btn.disabled = atLimit;
        btn.title = atLimit
            ? `Only ${this._MC_MAX_USER_CHANNELS} user channels (slots 1–7)`
            : '';
    }

    _addEmptyRow() {
        const tbody = this._body.querySelector('[data-mc-channels-body]');
        if (!tbody) return;
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
                       type="password" value="" placeholder="32-char hex (empty = hashtag)" />
                <button class="ch-table__reveal" type="button"
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
        const rows = this._body.querySelectorAll(
            '[data-mc-channels-body] tr:not(.ch-table__row--locked)',
        );
        const channels = [];
        rows.forEach((row) => {
            const name = (row.querySelector('[data-field="name"]')?.value || '').trim();
            const keyHex = (row.querySelector('[data-field="key_hex"]')?.value || '').trim();
            if (name || keyHex) channels.push({ name, key_hex: keyHex });
        });

        this._setStatus('pending', 'Saving…');
        const res = await this._api.put('/api/config/meshcore/channels', { channels });
        if (res) {
            this._setStatus('success', 'Channels saved.');
            this._api.toast('MeshCore channels saved');
        } else {
            this._setStatus('error', 'Save failed.');
        }
    }

    async _sendAdvert(button) {
        button.disabled = true;
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
            button.disabled = false;
        }
    }

    async _saveCompanionName(button) {
        const input = this._body.querySelector('[data-mc-name]');
        const advertEl = this._body.querySelector('[data-mc-name-advert]');
        const status = this._body.querySelector('[data-mc-name-status]');
        if (!input || !status) return;

        const value = (input.value || '').trim();
        if (!value) {
            status.dataset.kind = 'error';
            status.textContent = 'Name must not be empty.';
            return;
        }

        button.disabled = true;
        status.dataset.kind = 'pending';
        status.textContent = 'Renaming companion…';

        const result = await this._api.put(
            '/api/config/meshcore/companion-name',
            { name: value },
        );

        if (!result) {
            // _api.put toasts the server detail on non-2xx; we just
            // clear the inline status so the toast is the user's
            // canonical signal.
            status.dataset.kind = 'error';
            status.textContent = 'Save failed.';
            button.disabled = false;
            return;
        }

        status.dataset.kind = 'success';
        status.textContent = `Renamed to "${result.name || value}".`;
        this._api.toast('Companion renamed');

        // Default-on per the v0.7.5 spec: identity on the mesh is the
        // advert packet, so a rename without a follow-up advert leaves
        // every neighbor seeing the old name until the next periodic
        // beacon (which on MeshCore is operator-driven, not automatic).
        if (advertEl && advertEl.checked) {
            try {
                const advertRes = await this._api.post(
                    '/api/messages/advert',
                    {},
                );
                if (advertRes && advertRes.success) {
                    this._api.toast('Advert sent');
                } else if (advertRes) {
                    this._api.toast(
                        'Advert failed' +
                            (advertRes.error ? `: ${advertRes.error}` : ''),
                    );
                }
            } catch (_e) {
                // Rename already stuck on flash; advert failure is a
                // soft error. Rely on the toast to surface it.
            }
        }

        await this._api.refresh();
        button.disabled = false;
    }

    _setStatus(kind, message) {
        if (!this._statusEl) return;
        this._statusEl.dataset.kind = kind;
        this._statusEl.textContent = message;
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

window.MeshcoreConfigCard = MeshcoreConfigCard;
