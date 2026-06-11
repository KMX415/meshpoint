/**
 * Configuration → Channels — Quick Deploy QR export.
 *
 * Fetches GET /api/config/export and renders a Meshtastic-compatible
 * channel URL as QR + downloadable JSON. Private PSKs are never shown.
 */

class QuickDeployCard {
    constructor(api) {
        this._api = api;
        this._root = null;
        this._exportData = null;
    }

    mount(root) {
        this._root = root;
        this._root.innerHTML = `
            <article class="cfg-card cfg-card--quick-deploy">
                <header class="cfg-card__head">
                    <h3 class="cfg-card__title">Quick Deploy</h3>
                    <p class="cfg-card__hint">
                        Share public channel settings with field radios.
                        Uses the standard Meshtastic default key only:
                        private channel PSKs are never exported.
                    </p>
                </header>
                <div class="cfg-quick-deploy">
                    <div class="cfg-quick-deploy__qr" data-qr-host>
                        <p class="cfg-quick-deploy__placeholder">Loading…</p>
                    </div>
                    <div class="cfg-quick-deploy__meta" data-export-meta></div>
                    <div class="cfg-card__actions">
                        <button type="button" class="terminal-button"
                                data-copy-url disabled>Copy URL</button>
                        <button type="button" class="terminal-button terminal-button--primary"
                                data-download-json disabled>Download JSON</button>
                    </div>
                    <p class="cfg-status" data-quick-deploy-status aria-live="polite"></p>
                </div>
            </article>
        `;

        this._qrHost = this._root.querySelector('[data-qr-host]');
        this._metaEl = this._root.querySelector('[data-export-meta]');
        this._statusEl = this._root.querySelector('[data-quick-deploy-status]');
        this._copyBtn = this._root.querySelector('[data-copy-url]');
        this._downloadBtn = this._root.querySelector('[data-download-json]');

        this._copyBtn.addEventListener('click', () => this._copyUrl());
        this._downloadBtn.addEventListener('click', () => this._downloadJson());
    }

    async render(_config) {
        this._setStatus('pending', 'Loading export…');
        const data = await this._api.get('/api/config/export');
        if (!data) {
            this._setStatus('error', 'Could not load export.');
            return;
        }
        this._exportData = data;
        this._paintMeta(data);
        await this._paintQr(data.meshtastic_url);
        this._copyBtn.disabled = !data.meshtastic_url;
        this._downloadBtn.disabled = false;
        this._setStatus('success', 'Ready: scan with Meshtastic app.');
    }

    _paintMeta(data) {
        const rows = [
            ['Channel', data.channel_name],
            ['Preset', data.modem_preset_display || data.modem_preset],
            ['Region', data.region],
            ['Frequency', data.frequency_mhz != null ? `${data.frequency_mhz} MHz` : 'n/a'],
            ['Hop limit', data.hop_limit],
        ];
        this._metaEl.innerHTML = rows.map(([k, v]) => `
            <div class="cfg-quick-deploy__row">
                <span class="cfg-quick-deploy__key">${this._api.escape(k)}</span>
                <span class="cfg-quick-deploy__val">${this._api.escape(String(v ?? 'n/a'))}</span>
            </div>
        `).join('');
    }

    async _paintQr(url) {
        if (!url) {
            this._qrHost.innerHTML = '<p class="cfg-quick-deploy__placeholder">No URL</p>';
            return;
        }
        if (typeof window.QRCode === 'undefined') {
            this._qrHost.innerHTML = `
                <p class="cfg-quick-deploy__url">${this._api.escape(url)}</p>
                <p class="cfg-quick-deploy__placeholder">QR library unavailable: use Copy URL.</p>
            `;
            return;
        }
        this._qrHost.innerHTML = '<canvas data-qr-canvas></canvas>';
        const canvas = this._qrHost.querySelector('[data-qr-canvas]');
        try {
            const root = getComputedStyle(document.documentElement);
            await window.QRCode.toCanvas(canvas, url, {
                width: 220,
                margin: 1,
                color: {
                    dark: root.getPropertyValue('--text-primary').trim() || '#e2e8f0',
                    light: root.getPropertyValue('--bg-primary').trim() || '#0a0e17',
                },
            });
        } catch (e) {
            console.error('QR render failed:', e);
            this._qrHost.innerHTML = `<p class="cfg-quick-deploy__placeholder">QR render failed.</p>`;
        }
    }

    async _copyUrl() {
        const url = this._exportData && this._exportData.meshtastic_url;
        if (!url) return;
        try {
            await navigator.clipboard.writeText(url);
            this._api.toast('Channel URL copied.');
        } catch (e) {
            this._setStatus('error', 'Copy failed: select URL manually.');
        }
    }

    _downloadJson() {
        if (!this._exportData) return;
        const blob = new Blob(
            [JSON.stringify(this._exportData, null, 2)],
            { type: 'application/json' },
        );
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = 'meshpoint-quick-deploy.json';
        a.click();
        URL.revokeObjectURL(a.href);
        this._api.toast('JSON downloaded.');
    }

    _setStatus(kind, message) {
        if (!this._statusEl) return;
        this._statusEl.dataset.kind = kind;
        this._statusEl.textContent = message;
    }
}

window.QuickDeployCard = QuickDeployCard;
