
class MeshtasticFirmwareConfigCard {
    constructor(api) {
        this._api = api;
        this._root = null;
        this._enumeratedPorts = [];
        this._portUsage = {};
    }

    mount(root) {
        this._root = root;
        this._root.innerHTML = `
            <div class="cfg-section" data-mt-firmware-root>
                <article class="cfg-card">
                    <header class="cfg-card__head">
                        <h3 class="cfg-card__title">Meshtastic firmware</h3>
                        <p class="cfg-card__hint">
                            Flash official Meshtastic firmware from GitHub.
                            Leave erase off for upgrades; turn it on for a blank board.
                        </p>
                        <div class="cfg-firmware-installed" data-mt-firmware-installed aria-live="polite">
                            <span class="cfg-firmware-installed__label">Installed</span>
                            <span class="cfg-firmware-installed__version">Checking…</span>
                            <span class="cfg-firmware-installed__meta"></span>
                        </div>
                    </header>
                    <label class="cfg-field cfg-firmware-field">
                        <span class="cfg-field__label">Version</span>
                        <select class="cfg-field__input" data-mt-firmware-tag></select>
                        <button class="terminal-button cfg-firmware-rescan" type="button" data-mt-rescan-releases
                                title="Re-check Meshtastic's GitHub releases for a newly-published version">
                            ↻ Refresh
                        </button>
                    </label>
                    <label class="cfg-field cfg-firmware-field">
                        <span class="cfg-field__label">Board</span>
                        <select class="cfg-field__input" data-mt-firmware-board>
                            <option value="">Loading boards…</option>
                        </select>
                    </label>
                    <label class="cfg-field cfg-firmware-field">
                        <span class="cfg-field__label">Device to flash</span>
                        <select class="cfg-field__input" data-mt-firmware-device></select>
                        <button class="terminal-button cfg-firmware-rescan" type="button" data-mt-rescan-usb
                                title="Re-scan connected USB devices">
                            ↻ Rescan USB
                        </button>
                    </label>
                    <label class="cfg-field cfg-field--toggle cfg-firmware-board-field" data-mt-erase-all-wrap>
                        <input type="checkbox" data-mt-erase-all>
                        <span class="cfg-field__label">Erase everything (wipes board settings)</span>
                    </label>
                    <div data-mt-nrf-host hidden></div>
                    <div class="cfg-card__actions">
                        <button class="terminal-button terminal-button--primary"
                                type="button" data-mt-firmware-flash>
                            Flash
                        </button>
                        <button class="terminal-button" type="button" data-mt-firmware-toggle-output>
                            Show output
                        </button>
                    </div>
                    <pre class="cfg-firmware-output" data-mt-firmware-output hidden></pre>
                    <p class="cfg-status" data-mt-firmware-status aria-live="polite"></p>
                </article>
            </div>
        `;

        this._root.querySelector('[data-mt-firmware-flash]')
            .addEventListener('click', () => this._flashMeshtasticFirmware());
        this._root.querySelector('[data-mt-firmware-toggle-output]')
            .addEventListener('click', (e) => this._toggleMtFirmwareOutput(e.currentTarget));
        // Board list depends on which release is selected (each release's
        // own manifest lists its own board catalog), so re-fetch it
        // whenever Version changes rather than only once at mount.
        this._root.querySelector('[data-mt-firmware-tag]')
            .addEventListener('change', () => this._loadMtFirmwareTargets());
        this._root.querySelector('[data-mt-firmware-board]')
            .addEventListener('change', () => {
                this._syncMtFlashMethodUi();
                this._updateFlashButtonState();
            });
        this._root.querySelector('[data-mt-rescan-releases]')
            .addEventListener('click', (e) => this._rescanReleases(e.currentTarget));
        this._root.querySelector('[data-mt-rescan-usb]')
            .addEventListener('click', (e) => this._rescanUsb(e.currentTarget));

        this._loadMtFirmwareReleases();
        this._loadMtFirmwareTargets();
        this._refreshSerialPortsList();
        this._loadInstalledFirmware();
    }

    render(config) {
        this._portUsage = this._buildPortUsageMap(config);
    }

    async _loadInstalledFirmware() {
        const root = this._root?.querySelector('[data-mt-firmware-installed]');
        if (!root) return;
        const versionEl = root.querySelector('.cfg-firmware-installed__version');
        const metaEl = root.querySelector('.cfg-firmware-installed__meta');
        if (!versionEl || !metaEl) return;
        versionEl.textContent = 'Checking…';
        metaEl.textContent = '';
        // ConfigurationPanel._api.get returns the JSON body, or null on error.
        const data = await this._api.get('/api/config/serial/firmware/installed');
        if (!data) {
            versionEl.textContent = 'Unavailable';
            metaEl.textContent = 'Could not query serial nodes';
            return;
        }
        const devices = data.devices || [];
        const connected = devices.filter((d) => d.connected);
        if (!connected.length) {
            versionEl.textContent = 'Not connected';
            metaEl.textContent = '';
            return;
        }
        // One primary node shown prominently; extras in meta.
        const primary = connected[0];
        const version = (primary.version || '').trim() || 'Version not reported';
        let hw = (primary.hw_model || '').toString().trim();
        if (hw && typeof HW_NAMES !== 'undefined') {
            hw = HW_NAMES[hw] || HW_NAMES[String(hw)] || hw;
        }
        const port = primary.port_short
            || this._shortPortLabel(primary.port)
            || primary.name
            || 'USB';
        versionEl.textContent = version;
        const meta = [];
        if (hw) meta.push(hw);
        if (port) meta.push(port);
        if (connected.length > 1) {
            meta.push(`+${connected.length - 1} more`);
        }
        metaEl.textContent = meta.join(' · ');
    }

    _shortPortLabel(port) {
        if (!port) return '';
        const raw = String(port);
        const tty = raw.match(/tty(?:USB|ACM|AMA)\d+/i);
        if (tty) return tty[0];
        const base = raw.split('/').pop() || '';
        if (base.startsWith('tty')) return base;
        // Match against the USB enumeration list when we have it.
        for (const p of this._enumeratedPorts || []) {
            const aliases = [p.device, p.by_id, p.by_path, p.stable_path]
                .filter(Boolean);
            if (aliases.includes(raw)) {
                return String(p.device || '').split('/').pop() || 'USB';
            }
        }
        if (base.startsWith('platform-') || base.includes('pci-')) return 'USB';
        return base;
    }

        _buildPortUsageMap(config) {
        const usage = {};
        const cap = (config && config.capture) || {};
        (Array.isArray(cap.serial) ? cap.serial : []).forEach((d) => {
            if (d.serial_port) usage[d.serial_port] = d.label ? `Serial ${d.label}` : 'Serial';
        });
        const mcList = Array.isArray(cap.meshcore_usb)
            ? cap.meshcore_usb
            : (cap.meshcore_usb ? [cap.meshcore_usb] : []);
        mcList.forEach((c) => {
            if (c && c.serial_port) usage[c.serial_port] = c.label ? `MeshCore ${c.label}` : 'MeshCore';
        });
                return usage;
    }

        async _refreshSerialPortsList() {
        const result = await this._api.get('/api/config/serial-ports');
        const ports = (result && Array.isArray(result.ports)) ? result.ports : [];
        this._enumeratedPorts = ports;
        this._renderMtFirmwareDevicePicker();
    }

        async _rescanUsb(button) {
        const original = button.textContent;
        button.disabled = true;
        button.textContent = 'Scanning…';
        try {
            await this._refreshSerialPortsList();
        } finally {
            button.textContent = original;
            button.disabled = false;
        }
    }

        _portOptionLabel(p, usage) {
        const devName = (p.device || '').split('/').pop();
        const chip = (p.description || '')
            .replace(/^Silicon Labs\s+/i, '')
            .replace(/\s+USB to UART Bridge Controller.*$/i, '')
            .trim() || p.description || p.device;
        const usedBy = [p.device, p.by_id, p.by_path].filter(Boolean)
            .map((alias) => usage[alias]).find(Boolean);
        const parts = [devName, chip];
        if (usedBy) parts.push(`used by ${usedBy}`);
        return parts.filter(Boolean).join(' — ');
    }

        async _loadMtFirmwareTargets() {
        const select = this._root.querySelector('[data-mt-firmware-board]');
        if (!select) return;

        const previous = select.value;
        const tag = this._root.querySelector('[data-mt-firmware-tag]')?.value || '';
        const params = new URLSearchParams();
        if (tag) params.set('tag', tag);

        const result = await this._api.get(`/api/config/serial/firmware/targets?${params}`);
        const boards = (result && Array.isArray(result.boards)) ? result.boards : [];
        this._boards = boards;

        if (boards.length === 0) {
            select.innerHTML = '<option value="">No boards for this version</option>';
        } else {
            select.innerHTML = [
                '<option value="">Select a board…</option>',
                ...boards.map((b) => {
                    const method = b.flash_method || 'esptool';
                    const disabled = method === 'unsupported' ? ' disabled' : '';
                    const suffix = method === 'nrf_dfu' ? ' (nRF DFU)'
                        : method === 'unsupported' ? ' (not flashable yet)' : '';
                    return (
                        `<option value="${this._esc(b.board)}" data-flash-method="${this._esc(method)}"${disabled}>`
                        + `${this._esc(b.label)}${suffix}</option>`
                    );
                }),
            ].join('');
            if (previous && boards.some((b) => b.board === previous)) {
                select.value = previous;
            }
        }
        this._syncMtFlashMethodUi();
        this._updateFlashButtonState();
    }

    _selectedFlashMethod() {
        const select = this._root?.querySelector('[data-mt-firmware-board]');
        const opt = select?.selectedOptions?.[0];
        return opt?.dataset?.flashMethod || 'esptool';
    }

    _syncMtFlashMethodUi() {
        const method = this._selectedFlashMethod();
        const eraseWrap = this._root.querySelector('[data-mt-erase-all-wrap]');
        const host = this._root.querySelector('[data-mt-nrf-host]');
        const hint = this._root.querySelector('.cfg-card__hint');
        if (method === 'nrf_dfu') {
            if (eraseWrap) eraseWrap.hidden = true;
            if (hint) {
                hint.textContent = 'Flash official Meshtastic firmware (nRF: Adafruit DFU over USB).';
            }
            if (host && window.FirmwareNrfPanel) {
                if (!this._nrfPanel) {
                    this._nrfPanel = new window.FirmwareNrfPanel({
                        uploadUrl: '/api/config/serial/firmware/upload',
                        onFlashWithUpload: (opts) => this._flashMeshtasticFirmware(opts),
                        appendOutput: (t) => this._appendMtFirmwareOutput(t),
                        setStatus: (kind, text) => {
                            const status = this._root.querySelector('[data-mt-firmware-status]');
                            if (!status) return;
                            status.dataset.kind = kind;
                            status.textContent = text;
                        },
                    });
                }
                this._nrfPanel.mount(host);
            }
        } else {
            if (eraseWrap) eraseWrap.hidden = false;
            if (hint) {
                hint.textContent = (
                    'Flash official Meshtastic firmware from GitHub. '
                    + 'Leave erase off for upgrades; turn it on for a blank board.'
                );
            }
            if (this._nrfPanel) this._nrfPanel.unmount();
            if (host) host.hidden = true;
        }
    }

        _updateFlashButtonState() {
        const flashBtn = this._root.querySelector('[data-mt-firmware-flash]');
        if (!flashBtn) return;
        const boardInput = this._root.querySelector('[data-mt-firmware-board]');
        const hasPorts = (this._enumeratedPorts || []).length > 0;
        const hasBoard = !!(boardInput && boardInput.value);
        if (!hasPorts) {
            flashBtn.disabled = true;
            flashBtn.title = 'No USB-serial device connected to flash.';
        } else if (!hasBoard) {
            flashBtn.disabled = true;
            flashBtn.title = 'Pick a board first.';
        } else {
            flashBtn.disabled = false;
            flashBtn.title = '';
        }
    }

        _boardLabel(board) {
        const match = (this._boards || []).find((b) => b.board === board);
        return match ? match.label : board.replace(/-/g, ' ');
    }

        _renderMtFirmwareDevicePicker() {
        const select = this._root.querySelector('[data-mt-firmware-device]');
        if (!select) return;

        const ports = (this._enumeratedPorts || []).filter((p) => p.vid);
        const usage = this._portUsage || {};

        if (ports.length === 0) {
            select.innerHTML = '<option value="">No USB-serial devices detected</option>';
        } else {
            const previous = select.value;
            select.innerHTML = ports.map((p) => (
                `<option value="${this._esc(p.stable_path || p.device)}">${this._esc(this._portOptionLabel(p, usage))}</option>`
            )).join('');
            if (previous && ports.some((p) => (p.stable_path || p.device) === previous)) {
                select.value = previous;
            }
        }
        this._updateFlashButtonState();
    }

        async _loadMtFirmwareReleases() {
        const select = this._root.querySelector('[data-mt-firmware-tag]');
        if (!select) return;
        const result = await this._api.get('/api/config/serial/firmware/releases');
        const releases = (result && Array.isArray(result.releases)) ? result.releases : [];
        const previous = select.value;
        const options = ['<option value="">Latest</option>'];
        releases.forEach((r) => {
            options.push(`<option value="${this._esc(r.tag)}">${this._esc(r.tag)}</option>`);
        });
        select.innerHTML = options.join('');
        if (previous && releases.some((r) => r.tag === previous)) select.value = previous;
    }

        async _rescanReleases(button) {
        const original = button.textContent;
        button.disabled = true;
        button.textContent = 'Checking…';
        try {
            await this._loadMtFirmwareReleases();
            await this._loadMtFirmwareTargets();
        } finally {
            button.textContent = original;
            button.disabled = false;
        }
    }

    _toggleMtFirmwareOutput(button) {
        const pre = this._root.querySelector('[data-mt-firmware-output]');
        if (!pre) return;
        pre.hidden = !pre.hidden;
        button.textContent = pre.hidden ? 'Show output' : 'Hide output';
    }

    _appendMtFirmwareOutput(text) {
        const pre = this._root.querySelector('[data-mt-firmware-output]');
        if (!pre || !text) return;
        pre.textContent = pre.textContent ? `${pre.textContent}\n${text}` : text;
        pre.scrollTop = pre.scrollHeight;
    }

    async _flashMeshtasticFirmware(uploadOpts) {
        const boardInput = this._root.querySelector('[data-mt-firmware-board]');
        const deviceSelect = this._root.querySelector('[data-mt-firmware-device]');
        const tagSelect = this._root.querySelector('[data-mt-firmware-tag]');
        const eraseAllInput = this._root.querySelector('[data-mt-erase-all]');
        const board = (boardInput?.value || '').trim();
        const port = deviceSelect?.value;
        const method = this._selectedFlashMethod();
        const eraseAll = method === 'esptool' && eraseAllInput
            ? eraseAllInput.checked : false;
        const uploadId = uploadOpts?.upload_id || '';
        const flashMode = uploadOpts?.flash_mode || '';
        if ((!board && !uploadId) || !port) return;

        const status = this._root.querySelector('[data-mt-firmware-status]');
        if (board && !(this._boards || []).some((b) => b.board === board)) {
            if (status) {
                status.dataset.kind = 'error';
                status.textContent = 'Pick a board from the list.';
            }
            return;
        }
        if (method === 'unsupported') {
            if (status) {
                status.dataset.kind = 'error';
                status.textContent = 'This board is not flashable from Meshpoint yet.';
            }
            return;
        }

        const boardLabel = board ? this._boardLabel(board) : 'uploaded image';
        const deviceLabel = deviceSelect.options[deviceSelect.selectedIndex]?.text || port;
        const tag = tagSelect?.value || '';

        if (!uploadId) {
            const ok = await window.confirmModal({
                label: 'Flash Meshtastic firmware',
                description: method === 'nrf_dfu'
                    ? `Write Meshtastic firmware (${tag || 'latest'}) for ${boardLabel} `
                        + `to "${deviceLabel}" via USB DFU? Enters DFU automatically (no unplug).`
                    : eraseAll
                        ? `Erase the ENTIRE flash on "${deviceLabel}" and write official Meshtastic `
                            + `firmware (${tag || 'latest'}) for ${boardLabel}?`
                        : `Write official Meshtastic firmware (${tag || 'latest'}) for ${boardLabel} `
                            + `to "${deviceLabel}", keeping channels and settings?`,
            });
            if (!ok) return;
        }

        const flashBtn = this._root.querySelector('[data-mt-firmware-flash]');
        const outputPre = this._root.querySelector('[data-mt-firmware-output]');

        flashBtn.disabled = true;
        status.dataset.kind = 'pending';
        status.textContent = `Flashing ${deviceLabel}…`;
        if (outputPre) outputPre.textContent = '';
        this._appendMtFirmwareOutput(
            `# Flashing ${boardLabel} (${tag || 'latest'}, ${method}) onto ${port}…`,
        );
        if (this._nrfPanel && method === 'nrf_dfu') {
            this._nrfPanel.setConsole('meshpoint:dfu$ flash --touch 1200');
        }

        let finalResult = null;
        try {
            const body = { board, port, tag, erase_all: eraseAll };
            if (uploadId) {
                body.upload_id = uploadId;
                body.flash_mode = flashMode || 'dfu';
            }
            finalResult = await window.UpdateStreamClient.postNdjson(
                '/api/config/serial/firmware/flash/stream',
                body,
                (event) => {
                    if (event.type === 'started' && Array.isArray(event.cmd)) {
                        this._appendMtFirmwareOutput(`$ ${event.cmd.join(' ')}`);
                    } else if (event.type === 'line') {
                        this._appendMtFirmwareOutput(event.text);
                    }
                },
            );
        } catch (err) {
            status.dataset.kind = 'error';
            status.textContent = `Request failed: ${err.message || err}`;
            this._appendMtFirmwareOutput(`! ${err.message || err}`);
            flashBtn.disabled = false;
            return;
        }

        const success = !!(finalResult && finalResult.success);
        status.dataset.kind = success ? 'success' : 'error';
        status.textContent = success
            ? 'Flashed.'
            : `Failed (exit code ${finalResult ? finalResult.returncode : '?'}). See output below.`;
        if (!success && outputPre) outputPre.hidden = false;
        const toggleBtn = this._root.querySelector('[data-mt-firmware-toggle-output]');
        if (toggleBtn && outputPre) {
            toggleBtn.textContent = outputPre.hidden ? 'Show output' : 'Hide output';
        }

        flashBtn.disabled = false;
        if (success) {
            await this._api.refresh();
            await this._loadInstalledFirmware();
        }
    }

    _esc(str) {
        const el = document.createElement('span');
        el.textContent = str == null ? '' : String(str);
        return el.innerHTML;
    }
}

window.MeshtasticFirmwareConfigCard = MeshtasticFirmwareConfigCard;
