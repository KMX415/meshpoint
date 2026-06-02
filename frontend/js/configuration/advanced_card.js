/**
 * Configuration → Advanced card.
 *
 * Storage retention and radio spectral-scan tuning. Relay enable/rate
 * live on Transmit; MeshCore USB on Configuration → MeshCore.
 */

class AdvancedConfigCard {
    constructor(api) {
        this._api = api;
        this._root = null;
    }

    mount(root) {
        this._root = root;
        this._root.innerHTML = `
            <div class="cfg-section" data-adv-root>
                <article class="cfg-card">
                    <header class="cfg-card__head">
                        <h3 class="cfg-card__title">Storage</h3>
                        <p class="cfg-card__hint">Local SQLite retention on the SD card.</p>
                    </header>
                    <form class="cfg-form" data-storage-form>
                        <label class="cfg-field">
                            <span class="cfg-field__label">Max packets retained</span>
                            <input class="cfg-field__input" type="number" min="1000"
                                   max="10000000" data-storage-max>
                        </label>
                        <label class="cfg-field">
                            <span class="cfg-field__label">Cleanup interval (seconds)</span>
                            <input class="cfg-field__input" type="number" min="60" max="86400"
                                   data-storage-cleanup>
                        </label>
                        <div class="cfg-card__actions">
                            <button class="terminal-button terminal-button--primary"
                                    type="submit">Save storage</button>
                        </div>
                        <p class="cfg-status" data-storage-status aria-live="polite"></p>
                    </form>
                </article>
                <article class="cfg-card">
                    <header class="cfg-card__head">
                        <h3 class="cfg-card__title">Radio (advanced)</h3>
                        <p class="cfg-card__hint">Spectral scan and optional SX1261 SPI path for noise-floor readout.</p>
                    </header>
                    <form class="cfg-form" data-radio-adv-form>
                        <label class="cfg-field">
                            <span class="cfg-field__label">Spectral scan interval (s)</span>
                            <input class="cfg-field__input" type="number" min="0" max="3600"
                                   step="1" data-radio-scan-interval>
                            <span class="cfg-field__hint">0 disables hardware noise-floor scan.</span>
                        </label>
                        <label class="cfg-field">
                            <span class="cfg-field__label">SX1261 SPI path (optional)</span>
                            <input class="cfg-field__input" type="text"
                                   placeholder="/dev/spidev0.1 or empty" data-radio-sx1261>
                        </label>
                        <div class="cfg-card__actions">
                            <button class="terminal-button terminal-button--primary"
                                    type="submit">Save radio advanced</button>
                        </div>
                        <p class="cfg-status" data-radio-adv-status aria-live="polite"></p>
                    </form>
                </article>
            </div>
        `;
        this._storageForm = this._root.querySelector('[data-storage-form]');
        this._radioAdvForm = this._root.querySelector('[data-radio-adv-form]');
        this._storageForm.addEventListener('submit', (e) => this._saveStorage(e));
        this._radioAdvForm.addEventListener('submit', (e) => this._saveRadioAdv(e));
    }

    render(config) {
        const isNode = window.PlatformContext
            && window.PlatformContext.isNodePlatform(config);
        const radioArticle = this._radioAdvForm
            && this._radioAdvForm.closest('article');
        if (radioArticle) {
            radioArticle.style.display = isNode ? 'none' : '';
        }

        const storage = config.storage || {};
        const radioAdv = config.radio_advanced || {};

        this._setVal('[data-storage-max]', storage.max_packets_retained);
        this._setVal('[data-storage-cleanup]', storage.cleanup_interval_seconds);
        this._setVal('[data-radio-scan-interval]', radioAdv.spectral_scan_interval_seconds);
        this._setVal('[data-radio-sx1261]', radioAdv.sx1261_spi_path || '');
    }

    _setVal(sel, v) {
        const el = this._root.querySelector(sel);
        if (el && v != null) el.value = v;
    }

    async _saveStorage(event) {
        event.preventDefault();
        const status = this._root.querySelector('[data-storage-status]');
        status.dataset.kind = 'pending';
        status.textContent = 'Saving…';
        const result = await this._api.put('/api/config/storage', {
            max_packets_retained: Number(
                this._root.querySelector('[data-storage-max]').value,
            ),
            cleanup_interval_seconds: Number(
                this._root.querySelector('[data-storage-cleanup]').value,
            ),
        });
        this._finish(status, result, 'Storage updated.');
    }

    async _saveRadioAdv(event) {
        event.preventDefault();
        const status = this._root.querySelector('[data-radio-adv-status]');
        status.dataset.kind = 'pending';
        status.textContent = 'Saving…';
        const result = await this._api.put('/api/config/radio/advanced', {
            spectral_scan_interval_seconds: Number(
                this._root.querySelector('[data-radio-scan-interval]').value,
            ),
            sx1261_spi_path: this._root.querySelector('[data-radio-sx1261]').value.trim(),
        });
        this._finish(status, result, 'Radio advanced updated.');
    }

    _finish(statusEl, result, restartMsg) {
        if (result) {
            statusEl.dataset.kind = 'success';
            statusEl.textContent = 'Saved.';
            if (result.restart_required) {
                this._api.signalRestart(restartMsg);
            } else {
                this._api.toast(restartMsg);
            }
            this._api.refresh();
        } else {
            statusEl.dataset.kind = 'error';
            statusEl.textContent = 'Save failed.';
        }
    }
}

window.AdvancedConfigCard = AdvancedConfigCard;
