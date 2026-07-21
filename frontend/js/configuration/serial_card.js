/**
 * Configuration → Serial (Meshtastic USB) card.
 *
 * Edits capture.serial (multi-stick list). Empty serial_port means
 * meshtastic-python auto-detect. Credit: javastraat/meshpoint
 * ``9af5625`` + ``d6adb1e`` / ``a0b2679`` port picker.
 */

class SerialConfigCard {
    constructor(api) {
        this._api = api;
        this._root = null;
        this._portsByStable = new Map();
    }

    _MAX_DEVICES = 4;

    mount(root) {
        this._root = root;
        this._root.innerHTML = `
            <div class="cfg-section" data-serial-root>
                <article class="cfg-card">
                    <header class="cfg-card__head">
                        <h3 class="cfg-card__title">USB capture sources</h3>
                        <p class="cfg-card__hint">
                            One entry per Meshtastic USB stick (Heltec, T-Beam, etc.).
                            Use a label like 433 or 868 so packets tag as serial_433.
                            Up to ${this._MAX_DEVICES}. Requires a service restart after changes.
                        </p>
                    </header>
                    <label class="cfg-field cfg-field--toggle">
                        <input type="checkbox" data-serial-enable>
                        <span class="cfg-field__label">Include serial capture source</span>
                    </label>
                    <div class="cfg-companions" data-serial-devices></div>
                    <datalist id="serial-ports-list"></datalist>
                    <div class="cfg-companions__add-row">
                        <button class="terminal-button" type="button" data-serial-add-device>
                            + Add device
                        </button>
                        <button class="terminal-button" type="button" data-serial-rescan-usb
                                title="Re-scan connected USB devices">
                            Rescan USB
                        </button>
                    </div>
                    <div class="cfg-card__actions">
                        <button class="terminal-button terminal-button--primary"
                                type="button" data-serial-save>
                            Save USB sources
                        </button>
                    </div>
                    <p class="cfg-status" data-serial-status aria-live="polite"></p>
                </article>
            </div>
        `;
        this._devicesEl = this._root.querySelector('[data-serial-devices]');

        this._root.querySelector('[data-serial-add-device]')
            .addEventListener('click', () => this._addDeviceRow());
        this._root.querySelector('[data-serial-save]')
            .addEventListener('click', () => this._saveDevices());
        this._root.querySelector('[data-serial-rescan-usb]')
            .addEventListener('click', (e) => this._rescanUsb(e.currentTarget));
        this._refreshSerialPortsList();
    }

    render(config) {
        const cap = config.capture || {};
        const devices = Array.isArray(cap.serial) ? cap.serial : [];
        const sources = cap.sources || [];

        const enableEl = this._root.querySelector('[data-serial-enable]');
        if (enableEl) enableEl.checked = sources.includes('serial');

        this._devicesEl.innerHTML = '';
        const list = devices.length > 0
            ? devices
            : [{
                label: '',
                serial_port: cap.serial_port || '',
                serial_baud: cap.serial_baud || 115200,
            }];
        list.forEach((d) => this._addDeviceRow(d));
        this._syncAddBtn();
    }

    async _rescanUsb(button) {
        const original = button.textContent;
        button.disabled = true;
        button.textContent = 'Scanning…';
        try {
            await this._refreshSerialPortsList();
            this._devicesEl.querySelectorAll('[data-device-port]').forEach((input) => {
                this._updateResolvedPort(input);
            });
        } finally {
            button.disabled = false;
            button.textContent = original;
        }
    }

    async _refreshSerialPortsList() {
        const list = this._root.querySelector('#serial-ports-list');
        if (!list) return;
        const result = await this._api.get('/api/config/serial-ports');
        const ports = (result && result.ports) || [];
        this._portsByStable = new Map(
            ports.map((p) => [p.stable_path, p]),
        );
        list.innerHTML = ports.map((p) => {
            const label = this._esc(p.description || p.device);
            const value = this._esc(p.stable_path);
            return `<option value="${value}">${label}</option>`;
        }).join('');
    }

    _addDeviceRow(data = {}) {
        const idx = this._devicesEl.children.length;
        if (idx >= this._MAX_DEVICES) return;

        const label = this._esc(data.label || '');
        const port = this._esc(data.serial_port || '');
        const baud = data.serial_baud != null ? data.serial_baud : 115200;

        const div = document.createElement('div');
        div.className = 'cfg-companion';
        div.dataset.deviceIdx = idx;
        div.innerHTML = `
            <div class="cfg-companion__header">
                <span class="cfg-companion__num">Device ${idx + 1}</span>
                <label class="cfg-companion__label-wrap">
                    <span class="cfg-field__label">Label</span>
                    <input class="cfg-field__input cfg-companion__label-input"
                           type="text" maxlength="16"
                           placeholder="e.g. 433 or 868"
                           value="${label}" data-device-label>
                </label>
                <button class="cfg-companion__remove terminal-button terminal-button--danger"
                        type="button" title="Remove device">✕</button>
            </div>
            <label class="cfg-field">
                <span class="cfg-field__label">Pinned serial port</span>
                <input class="cfg-field__input" type="text" list="serial-ports-list"
                       placeholder="/dev/serial/by-path/… (blank = auto-detect)"
                       value="${port}" data-device-port>
                <span class="cfg-field__resolved" data-device-resolved hidden></span>
            </label>
            <label class="cfg-field cfg-field--narrow">
                <span class="cfg-field__label">Baud rate</span>
                <input class="cfg-field__input" type="number"
                       value="${baud}" data-device-baud>
            </label>
        `;

        div.querySelector('.cfg-companion__remove').addEventListener('click', () => {
            div.remove();
            this._reindexDevices();
            this._syncAddBtn();
        });

        const portInput = div.querySelector('[data-device-port]');
        portInput.addEventListener('input', () => this._updateResolvedPort(portInput));
        portInput.addEventListener('change', () => this._updateResolvedPort(portInput));
        this._updateResolvedPort(portInput);

        this._devicesEl.appendChild(div);
        this._syncAddBtn();
    }

    _updateResolvedPort(input) {
        const hint = input.parentElement.querySelector('[data-device-resolved]');
        if (!hint) return;
        const value = (input.value || '').trim();
        const info = this._portsByStable.get(value);
        if (info && info.device && info.device !== value) {
            hint.hidden = false;
            hint.textContent = `→ ${info.device}`;
        } else {
            hint.hidden = true;
            hint.textContent = '';
        }
    }

    _reindexDevices() {
        this._devicesEl.querySelectorAll('.cfg-companion').forEach((el, i) => {
            el.dataset.deviceIdx = i;
            const num = el.querySelector('.cfg-companion__num');
            if (num) num.textContent = `Device ${i + 1}`;
        });
    }

    _syncAddBtn() {
        const btn = this._root.querySelector('[data-serial-add-device]');
        if (!btn) return;
        const count = this._devicesEl.children.length;
        btn.disabled = count >= this._MAX_DEVICES;
        btn.title = count >= this._MAX_DEVICES
            ? `Maximum ${this._MAX_DEVICES} devices`
            : '';
    }

    async _saveDevices() {
        const status = this._root.querySelector('[data-serial-status]');
        status.dataset.kind = 'pending';
        status.textContent = 'Saving…';

        const devices = [];
        this._devicesEl.querySelectorAll('.cfg-companion').forEach((div) => {
            devices.push({
                label: (div.querySelector('[data-device-label]')?.value || '').trim(),
                serial_port: (div.querySelector('[data-device-port]')?.value || '').trim() || null,
                serial_baud: Number(div.querySelector('[data-device-baud]')?.value) || 115200,
            });
        });

        const result = await this._api.put('/api/config/capture/serial-devices', {
            enable_source: this._root.querySelector('[data-serial-enable]').checked,
            devices,
        });

        if (result) {
            status.dataset.kind = 'success';
            status.textContent = 'Saved.';
            this._api.signalRestart('Serial USB devices updated.');
            await this._api.refresh();
        } else {
            status.dataset.kind = 'error';
            status.textContent = 'Save failed.';
        }
    }

    _esc(str) {
        const el = document.createElement('span');
        el.textContent = str || '';
        return el.innerHTML;
    }
}

window.SerialConfigCard = SerialConfigCard;
