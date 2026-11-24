/**
 * Progressive DFU UI for nRF boards on Configuration → Firmware.
 *
 * Mounted only when the selected board has flash_method === nrf_dfu.
 * Enters DFU over USB automatically (1200-baud touch on the Pi).
 * Drag-drop accepts .zip (serial DFU) or .uf2 (volume copy when mounted).
 */

class FirmwareNrfPanel {
    /**
     * @param {object} opts
     * @param {string} opts.uploadUrl  POST multipart upload endpoint
     * @param {function(object): Promise} opts.onFlashWithUpload
     *   Called with { upload_id, flash_mode } after a successful drop upload.
     * @param {function(string): void} [opts.appendOutput]
     * @param {function(string, string): void} [opts.setStatus] kind, text
     */
    constructor(opts) {
        this._uploadUrl = opts.uploadUrl;
        this._onFlashWithUpload = opts.onFlashWithUpload;
        this._appendOutput = opts.appendOutput || (() => {});
        this._setStatus = opts.setStatus || (() => {});
        this._root = null;
    }

    mount(host) {
        this._root = host;
        host.hidden = false;
        host.innerHTML = `
            <div class="cfg-firmware-nrf" data-nrf-panel>
                <p class="cfg-firmware-nrf__hint">
                    Enters DFU over USB automatically. No unplug needed unless recovery.
                </p>
                <p class="cfg-firmware-nrf__console" data-nrf-console aria-live="polite">
                    meshpoint:dfu$ waiting
                </p>
                <div class="cfg-firmware-nrf__drop" data-nrf-drop tabindex="0"
                     role="button"
                     aria-label="Drop DFU zip or UF2 firmware here">
                    <span class="cfg-firmware-nrf__drop-label">
                        Drop .zip (DFU) or .uf2 here for a custom image
                    </span>
                    <input type="file" accept=".zip,.uf2,application/zip"
                           data-nrf-file hidden>
                </div>
            </div>
        `;
        const drop = host.querySelector('[data-nrf-drop]');
        const fileInput = host.querySelector('[data-nrf-file]');
        drop.addEventListener('dragover', (e) => {
            e.preventDefault();
            drop.classList.add('cfg-firmware-nrf__drop--active');
        });
        drop.addEventListener('dragleave', () => {
            drop.classList.remove('cfg-firmware-nrf__drop--active');
        });
        drop.addEventListener('drop', (e) => {
            e.preventDefault();
            drop.classList.remove('cfg-firmware-nrf__drop--active');
            const file = e.dataTransfer?.files?.[0];
            if (file) this._handleFile(file);
        });
        drop.addEventListener('click', () => fileInput.click());
        drop.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                fileInput.click();
            }
        });
        fileInput.addEventListener('change', () => {
            const file = fileInput.files?.[0];
            if (file) this._handleFile(file);
            fileInput.value = '';
        });
    }

    unmount() {
        if (this._root) {
            this._root.hidden = true;
            this._root.innerHTML = '';
        }
    }

    setConsole(text) {
        const el = this._root?.querySelector('[data-nrf-console]');
        if (el) el.textContent = text;
    }

    async _handleFile(file) {
        const name = (file.name || '').toLowerCase();
        if (!name.endsWith('.zip') && !name.endsWith('.uf2')) {
            this._setStatus('error', 'Only .zip or .uf2 files are accepted.');
            this.setConsole('meshpoint:dfu$ reject -- bad type');
            return;
        }
        this.setConsole(`meshpoint:dfu$ upload ${file.name}`);
        this._setStatus('pending', `Uploading ${file.name}…`);
        const body = new FormData();
        body.append('file', file, file.name);
        let uploadId = null;
        try {
            const res = await fetch(this._uploadUrl, {
                method: 'POST',
                body,
                credentials: 'same-origin',
            });
            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                throw new Error(err.detail || `upload failed (${res.status})`);
            }
            const data = await res.json();
            uploadId = data.upload_id;
        } catch (err) {
            this._setStatus('error', err.message || String(err));
            this.setConsole(`meshpoint:dfu$ fail -- ${err.message || err}`);
            this._appendOutput(`! upload: ${err.message || err}`);
            return;
        }
        const flashMode = name.endsWith('.uf2') ? 'uf2' : 'dfu';
        this.setConsole(`meshpoint:dfu$ flash --mode ${flashMode}`);
        await this._onFlashWithUpload({
            upload_id: uploadId,
            flash_mode: flashMode,
        });
    }
}

window.FirmwareNrfPanel = FirmwareNrfPanel;
