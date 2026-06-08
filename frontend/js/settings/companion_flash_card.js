/**
 * Settings → System — USB companion firmware flasher (PR 14).
 *
 * Upload a .bin, confirm via DangerousModal, POST /api/firmware/flash,
 * and stream esptool output from /api/firmware/ws/flash-log.
 */

class CompanionFlashCard {
    constructor(rootEl) {
        this._host = rootEl;
        this._modal = new window.DangerousModal();
        this._uploadId = null;
        this._filename = '';
        this._ws = null;
        this._logLines = [];
    }

    mount() {
        if (!this._host) return;
        this._host.innerHTML = `
            <article class="auth-card companion-flash-card" id="companion-flash-card">
                <h3 class="auth-card__title">Flash companion firmware</h3>
                <p class="auth-card__hint">
                    Upload a <code>.bin</code> and flash the USB MeshCore or Meshtastic companion.
                    MeshCore capture pauses during the flash and auto-reconnects afterward.
                    Admin only; recorded in the audit log.
                </p>
                <label class="cfg-field">
                    <span class="cfg-field__label">Firmware file (.bin)</span>
                    <input class="cfg-field__input" type="file" accept=".bin,application/octet-stream"
                           data-fw-file>
                </label>
                <label class="cfg-field">
                    <span class="cfg-field__label">Serial port</span>
                    <input class="cfg-field__input" type="text" data-fw-port placeholder="/dev/ttyUSB0">
                </label>
                <div class="cfg-field cfg-field--row">
                    <label class="cfg-field">
                        <span class="cfg-field__label">Baud</span>
                        <input class="cfg-field__input" type="number" min="9600" max="921600"
                               step="1" data-fw-baud value="460800">
                    </label>
                    <label class="cfg-field">
                        <span class="cfg-field__label">Offset</span>
                        <input class="cfg-field__input" type="text" data-fw-offset value="0x10000">
                    </label>
                </div>
                <p class="auth-card__hint" data-fw-upload-status aria-live="polite"></p>
                <div class="auth-card__actions">
                    <button type="button" class="terminal-button terminal-button--danger"
                            data-fw-flash disabled>Flash firmware</button>
                    <button type="button" class="terminal-button terminal-button--ghost"
                            data-fw-clear-log>Clear log</button>
                </div>
                <pre class="companion-flash-log" data-fw-log aria-live="polite"></pre>
            </article>
        `;

        this._fileInput = this._host.querySelector('[data-fw-file]');
        this._portInput = this._host.querySelector('[data-fw-port]');
        this._baudInput = this._host.querySelector('[data-fw-baud]');
        this._offsetInput = this._host.querySelector('[data-fw-offset]');
        this._flashBtn = this._host.querySelector('[data-fw-flash]');
        this._uploadStatus = this._host.querySelector('[data-fw-upload-status]');
        this._logEl = this._host.querySelector('[data-fw-log]');

        this._fileInput.addEventListener('change', () => this._onFileSelected());
        this._flashBtn.addEventListener('click', () => this._onFlashClick());
        this._host.querySelector('[data-fw-clear-log]').addEventListener('click', () => {
            this._logLines = [];
            this._paintLog();
        });

        this._loadDefaults();
        this._connectLogWs();
    }

    async _loadDefaults() {
        try {
            const res = await fetch('/api/firmware/defaults', { credentials: 'same-origin' });
            if (!res.ok) return;
            const data = await res.json();
            if (data.serial_port && this._portInput) {
                this._portInput.value = data.serial_port;
            }
            if (data.baud_rate != null && this._baudInput) {
                this._baudInput.value = data.baud_rate;
            }
            if (data.partition_offset && this._offsetInput) {
                this._offsetInput.value = data.partition_offset;
            }
        } catch (_e) { /* best-effort */ }
    }

    _connectLogWs() {
        if (this._ws) return;
        const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
        const url = `${proto}//${location.host}/api/firmware/ws/flash-log`;
        try {
            this._ws = new WebSocket(url);
            this._ws.onmessage = (event) => {
                this._appendLog(event.data);
            };
            this._ws.onclose = () => {
                this._ws = null;
                setTimeout(() => this._connectLogWs(), 5000);
            };
        } catch (_e) {
            this._appendLog('[flasher] WebSocket unavailable');
        }
    }

    async _onFileSelected() {
        const file = this._fileInput?.files?.[0];
        if (!file) return;
        if (!file.name.toLowerCase().endsWith('.bin')) {
            this._setUploadStatus('error', 'Only .bin files are accepted.');
            this._uploadId = null;
            this._flashBtn.disabled = true;
            return;
        }
        this._setUploadStatus('pending', 'Uploading…');
        const form = new FormData();
        form.append('firmware_file', file);
        try {
            const res = await fetch('/api/firmware/upload', {
                method: 'POST',
                credentials: 'same-origin',
                body: form,
            });
            if (!res.ok) {
                const body = await res.json().catch(() => ({}));
                this._setUploadStatus('error', body.detail || `Upload failed (${res.status}).`);
                this._flashBtn.disabled = true;
                return;
            }
            const data = await res.json();
            this._uploadId = data.upload_id;
            this._filename = data.filename || file.name;
            this._setUploadStatus(
                'success',
                `Ready: ${this._filename} (${this._formatBytes(data.size_bytes)})`,
            );
            this._flashBtn.disabled = false;
        } catch (_e) {
            this._setUploadStatus('error', 'Upload failed (network error).');
            this._flashBtn.disabled = true;
        }
    }

    async _onFlashClick() {
        if (!this._uploadId) return;
        const port = (this._portInput?.value || '').trim();
        const baud = Number(this._baudInput?.value || 460800);
        const offset = (this._offsetInput?.value || '0x10000').trim();
        const ok = await this._modal.confirm({
            label: 'flash firmware',
            command: `Flash ${this._filename}`,
            description:
                `This halts MeshCore USB on ${port} for ~20–30 seconds while esptool writes the image. `
                + 'The companion will reboot and reconnect automatically.',
        });
        if (!ok) return;

        this._appendLog(`[ui] Starting flash on ${port}…`);
        this._flashBtn.disabled = true;
        try {
            const res = await fetch('/api/firmware/flash', {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    upload_id: this._uploadId,
                    serial_port: port,
                    baud_rate: baud,
                    partition_offset: offset,
                }),
            });
            const body = await res.json().catch(() => ({}));
            if (res.status === 409) {
                this._appendLog(`[ui] ${body.detail || 'Flash already in progress.'}`);
            } else if (!res.ok) {
                this._appendLog(`[ui] Flash request failed: ${body.detail || res.status}`);
            } else {
                this._appendLog(`[ui] Queued — watch log below for esptool output.`);
                this._uploadId = null;
                this._fileInput.value = '';
                this._setUploadStatus('', '');
            }
        } catch (_e) {
            this._appendLog('[ui] Flash request failed (network error).');
        } finally {
            this._flashBtn.disabled = !this._uploadId;
        }
    }

    _appendLog(line) {
        this._logLines.push(String(line));
        if (this._logLines.length > 500) {
            this._logLines = this._logLines.slice(-500);
        }
        this._paintLog();
    }

    _paintLog() {
        if (!this._logEl) return;
        this._logEl.textContent = this._logLines.join('\n');
        this._logEl.scrollTop = this._logEl.scrollHeight;
    }

    _setUploadStatus(kind, message) {
        if (!this._uploadStatus) return;
        this._uploadStatus.dataset.kind = kind || '';
        this._uploadStatus.textContent = message || '';
    }

    static _formatBytes(n) {
        const v = Number(n) || 0;
        if (v < 1024) return `${v} B`;
        if (v < 1024 * 1024) return `${(v / 1024).toFixed(1)} KB`;
        return `${(v / (1024 * 1024)).toFixed(2)} MB`;
    }
}

window.CompanionFlashCard = CompanionFlashCard;
