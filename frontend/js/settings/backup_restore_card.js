/**
 * Settings → System backup and restore card.
 *
 * Downloads a timestamped archive of local.yaml and the full data/
 * directory, and restores from an uploaded backup after confirmation.
 */

class BackupRestoreCard {
    constructor(rootEl) {
        this.root = rootEl;
        this.warningEl = rootEl.querySelector('[data-backup-warning]');
        this.summaryEl = rootEl.querySelector('[data-backup-summary]');
        this.statusEl = rootEl.querySelector('[data-backup-status]');
        this.downloadBtn = rootEl.querySelector('[data-backup-download]');
        this.fileInput = rootEl.querySelector('[data-backup-file]');
        this.restoreBtn = rootEl.querySelector('[data-backup-restore]');
        this.modal = window.DangerousModal ? new window.DangerousModal() : null;
        this._status = null;
    }

    bind() {
        this.downloadBtn?.addEventListener('click', () => this._download());
        this.restoreBtn?.addEventListener('click', () => this.fileInput?.click());
        this.fileInput?.addEventListener('change', () => this._onFileSelected());
    }

    async refresh() {
        try {
            const response = await fetch('/api/system/backup/status', {
                credentials: 'same-origin',
            });
            if (!response.ok) {
                this._setStatus('error', `Could not load backup status (HTTP ${response.status}).`);
                return;
            }
            this._status = await response.json();
            this._renderSummary();
            this._renderWarning();
        } catch (_e) {
            this._setStatus('error', 'Network error loading backup status.');
        }
    }

    _renderSummary() {
        if (!this.summaryEl || !this._status) return;
        const bytes = Number(this._status.estimated_bytes || 0);
        const mb = (bytes / (1024 * 1024)).toFixed(1);
        const disk = Number(this._status.disk_percent || 0).toFixed(1);
        this.summaryEl.textContent =
            `Device ${this._status.device_name || 'Meshpoint'} `
            + `(${this._status.device_id || 'unknown'}). `
            + `Estimated backup size about ${mb} MB. `
            + `Root disk use ${disk}%. `
            + 'Archive is not encrypted.';
    }

    _renderWarning() {
        if (!this.warningEl || !this._status) return;
        if (this._status.suggest_backup) {
            this.warningEl.hidden = false;
            this.warningEl.textContent =
                'Root filesystem is nearly full. Download a backup before the SD card fails.';
            return;
        }
        this.warningEl.hidden = true;
        this.warningEl.textContent = '';
    }

    async _download() {
        if (!this.downloadBtn) return;
        this.downloadBtn.disabled = true;
        this._setStatus('pending', 'Building backup…');
        try {
            const response = await fetch('/api/system/backup/download', {
                credentials: 'same-origin',
            });
            if (!response.ok) {
                this._setStatus('error', `Download failed (HTTP ${response.status}).`);
                return;
            }
            const blob = await response.blob();
            const disposition = response.headers.get('Content-Disposition') || '';
            const match = disposition.match(/filename="?([^";]+)"?/i);
            const filename = match ? match[1] : 'meshpoint-backup.tar.gz';
            const url = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = filename;
            document.body.appendChild(link);
            link.click();
            link.remove();
            URL.revokeObjectURL(url);
            this._setStatus('ok', 'Backup downloaded. Store the file offline and keep it private.');
        } catch (_e) {
            this._setStatus('error', 'Network error during download.');
        } finally {
            this.downloadBtn.disabled = false;
        }
    }

    async _onFileSelected() {
        const file = this.fileInput?.files?.[0];
        if (!file || !this.modal) return;
        const ok = await this.modal.confirm({
            label: 'Restore backup?',
            command: 'Restore backup',
            description:
                'This overwrites config/local.yaml and the full data/ directory, '
                + 'then restarts the Meshpoint service. The dashboard will reload in about 30 seconds. '
                + 'A copy of the current state is stashed on the Pi before restore.',
        });
        this.fileInput.value = '';
        if (!ok) return;
        await this._restore(file);
    }

    async _restore(file) {
        if (this.restoreBtn) this.restoreBtn.disabled = true;
        this._setStatus('pending', 'Uploading backup and starting restore…');
        try {
            const response = await fetch('/api/system/backup/restore', {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/gzip',
                },
                body: file,
            });
            const body = await response.json().catch(() => ({}));
            if (!response.ok) {
                const detail = body.detail || `HTTP ${response.status}`;
                this._setStatus('error', `Restore rejected: ${detail}`);
                return;
            }
            this._setStatus(
                'pending',
                body.message || 'Restore initiated. Waiting for the dashboard to come back…',
            );
            const recovered = await this._waitForServiceRecovery();
            if (recovered) {
                window.setTimeout(() => window.location.reload(), 800);
            }
        } catch (_e) {
            this._setStatus(
                'pending',
                'Connection dropped while restore runs. Refresh in about a minute or check journalctl -u meshpoint.',
            );
            await this._waitForServiceRecovery();
            window.setTimeout(() => window.location.reload(), 800);
        } finally {
            if (this.restoreBtn) this.restoreBtn.disabled = false;
        }
    }

    async _waitForServiceRecovery({ timeoutMs = 180000, intervalMs = 2000 } = {}) {
        const deadline = Date.now() + timeoutMs;
        while (Date.now() < deadline) {
            try {
                const response = await fetch('/api/identity', {
                    credentials: 'same-origin',
                    cache: 'no-store',
                });
                if (response.ok) {
                    this._setStatus('ok', 'Dashboard is back online. Reloading…');
                    return true;
                }
            } catch (_e) { /* restart drops the connection */ }
            await new Promise((resolve) => window.setTimeout(resolve, intervalMs));
        }
        this._setStatus(
            'error',
            'Still waiting for the dashboard. Refresh the page or check journalctl -u meshpoint over SSH.',
        );
        return false;
    }

    _setStatus(kind, message) {
        if (!this.statusEl) return;
        this.statusEl.dataset.kind = kind;
        this.statusEl.textContent = message;
    }
}

window.BackupRestoreCard = BackupRestoreCard;
