/**
 * Radio settings panel for the local Meshpoint dashboard.
 * Renders TX status, node identity, radio configuration with
 * modem preset selector, duty cycle meter, and MeshCore companion info.
 */
class RadioSettings {
    constructor() {
        this._initialized = false;
        this._config = null;
        this._channels = null;
        this._restartNeeded = false;
    }

    async onActivated() {
        if (!this._initialized) {
            this._build();
            this._initialized = true;
        }
        await this._loadConfig();
    }

    _build() {
        const panel = document.getElementById('radio-panel');
        if (!panel) return;

        panel.innerHTML = `
            <div class="radio">
                <div class="radio__top-row">
                    <div class="radio-card radio-card--status" id="radio-tx-status"></div>
                    <div class="radio-card radio-card--identity" id="radio-identity"></div>
                </div>
                <div class="radio-card radio-card--config" id="radio-config"></div>
                <div class="radio-card radio-card--channels" id="radio-channels-card"></div>
                <div class="radio-card radio-card--companion" id="radio-companion"></div>
                <div id="radio-restart-bar" class="radio-restart-bar" style="display:none">
                    <span>Some changes require a service restart to take effect.</span>
                    <button class="radio-restart-bar__btn" id="radio-restart-btn">Restart Service</button>
                </div>
            </div>
        `;

        document.getElementById('radio-restart-btn').addEventListener('click', async () => {
            if (!confirm('Restart the Meshpoint service? This will briefly interrupt packet capture.')) return;
            try {
                await fetch('/api/config/restart', { method: 'POST' });
                document.getElementById('radio-restart-bar').innerHTML =
                    '<span>Restarting... page will reload in 10 seconds.</span>';
                setTimeout(() => location.reload(), 10000);
            } catch (e) {
                alert('Restart failed: ' + e.message);
            }
        });

        this._channels = new RadioChannels(
            document.getElementById('radio-channels-card')
        );
    }

    async _loadConfig() {
        try {
            const res = await fetch('/api/config');
            this._config = await res.json();
            this._renderAll();
        } catch (e) {
            console.error('Failed to load config:', e);
        }
    }

    _renderAll() {
        const c = this._config;
        if (!c) return;
        this._renderTxStatus(c);
        this._renderIdentity(c);
        this._renderRadioConfig(c);
        this._renderCompanion(c);
        if (this._channels) {
            this._channels.render(c.channels);
        }
    }

    _renderTxStatus(c) {
        const el = document.getElementById('radio-tx-status');
        const tx = c.transmit;
        const duty = c.duty_cycle || {};
        const pct = duty.used_percent || 0;
        const statusLabel = tx.enabled ? 'READY' : 'DISABLED';
        const statusClass = tx.enabled ? 'radio-status--on' : 'radio-status--off';

        el.innerHTML = `
            <h3 class="radio-card__title">TX Status</h3>
            <div class="radio-status ${statusClass}">${statusLabel}</div>
            <div class="radio-duty">
                <label class="radio-label">Duty Cycle</label>
                <div class="radio-duty__bar">
                    <div class="radio-duty__fill" style="width:${Math.min(pct, 100)}%"></div>
                </div>
                <span class="radio-duty__text">${pct.toFixed(1)}% of ${tx.max_duty_cycle_percent}%</span>
            </div>
            <div class="radio-field">
                <label class="radio-label">TX Enabled</label>
                <label class="radio-toggle">
                    <input type="checkbox" id="radio-tx-enabled" ${tx.enabled ? 'checked' : ''}>
                    <span class="radio-toggle__slider"></span>
                </label>
            </div>
        `;

        document.getElementById('radio-tx-enabled').addEventListener('change', async (e) => {
            const result = await this._putConfig('/api/config/transmit', { enabled: e.target.checked });
            if (result && result.restart_required) {
                this._showRestartBar();
                this._showToast('TX ' + (e.target.checked ? 'enabled' : 'disabled') + '. Restart required.');
            }
        });
    }

    _renderIdentity(c) {
        const el = document.getElementById('radio-identity');
        const tx = c.transmit;

        el.innerHTML = `
            <h3 class="radio-card__title">Node Identity</h3>
            <div class="radio-field">
                <label class="radio-label">Node ID</label>
                <input class="radio-input radio-input--mono" id="radio-node-id" value="${tx.node_id_hex || ''}" placeholder="!aabbccdd" maxlength="10">
            </div>
            <div class="radio-field">
                <label class="radio-label">Long Name</label>
                <input class="radio-input" id="radio-long-name" value="${this._esc(tx.long_name || '')}" maxlength="36">
            </div>
            <div class="radio-field">
                <label class="radio-label">Short Name</label>
                <input class="radio-input" id="radio-short-name" value="${this._esc(tx.short_name || '')}" maxlength="4">
            </div>
            <button class="radio-save-btn" id="radio-save-identity">Save Identity</button>
        `;

        document.getElementById('radio-save-identity').addEventListener('click', async () => {
            const nodeIdRaw = document.getElementById('radio-node-id').value.trim();
            const longName = document.getElementById('radio-long-name').value.trim();
            const shortName = document.getElementById('radio-short-name').value.trim();

            const identityPayload = { long_name: longName, short_name: shortName };

            if (nodeIdRaw) {
                const hex = nodeIdRaw.replace(/^!/, '');
                const parsed = parseInt(hex, 16);
                if (!isNaN(parsed) && parsed > 0) {
                    identityPayload.node_id = parsed;
                }
            }

            await this._saveIdentity(identityPayload);
        });
    }

    _renderRadioConfig(c) {
        const el = document.getElementById('radio-config');
        const radio = c.radio;
        const tx = c.transmit;
        const presets = c.presets || [];
        const regions = c.regions || [];

        const presetOptions = presets.map(p => {
            const selected = p.name === radio.current_preset ? 'selected' : '';
            const rxOnly = p.tx_capable ? '' : ' (RX only)';
            return `<option value="${p.name}" ${selected}>${p.display_name}${rxOnly}</option>`;
        }).join('');

        const regionOptions = regions.map(r => {
            const selected = r.id === radio.region ? 'selected' : '';
            return `<option value="${r.id}" ${selected}>${r.name} (${r.frequency_mhz} MHz)</option>`;
        }).join('');

        el.innerHTML = `
            <h3 class="radio-card__title">Radio Configuration</h3>
            <div class="radio-config-grid">
                <div class="radio-field">
                    <label class="radio-label">Region</label>
                    <select class="radio-select" id="radio-region">${regionOptions}</select>
                </div>
                <div class="radio-field">
                    <label class="radio-label">Modem Preset</label>
                    <select class="radio-select" id="radio-preset">
                        ${presetOptions}
                        <option value="CUSTOM" ${!radio.current_preset ? 'selected' : ''}>Custom</option>
                    </select>
                </div>
                <div class="radio-field">
                    <label class="radio-label">Frequency (MHz)</label>
                    <input type="number" class="radio-input radio-input--narrow" id="radio-freq" value="${radio.frequency_mhz}" step="0.001" min="100" max="1000">
                </div>
                <div class="radio-field">
                    <label class="radio-label">Spreading Factor</label>
                    <span class="radio-value radio-value--mono" id="radio-sf">SF${radio.spreading_factor}</span>
                </div>
                <div class="radio-field">
                    <label class="radio-label">Bandwidth</label>
                    <span class="radio-value radio-value--mono" id="radio-bw">${radio.bandwidth_khz} kHz</span>
                </div>
                <div class="radio-field">
                    <label class="radio-label">Coding Rate</label>
                    <span class="radio-value radio-value--mono" id="radio-cr">${radio.coding_rate}</span>
                </div>
                <div class="radio-field">
                    <label class="radio-label">TX Power (dBm)</label>
                    <input type="number" class="radio-input radio-input--narrow" id="radio-tx-power" value="${tx.tx_power_dbm}" min="0" max="30">
                </div>
                <div class="radio-field">
                    <label class="radio-label">Hop Limit</label>
                    <input type="number" class="radio-input radio-input--narrow" id="radio-hop-limit" value="${tx.hop_limit}" min="0" max="7">
                </div>
                <div class="radio-field">
                    <label class="radio-label">Sync Word</label>
                    <span class="radio-value radio-value--mono">${radio.sync_word}</span>
                </div>
                <div class="radio-field">
                    <label class="radio-label">Preamble</label>
                    <span class="radio-value radio-value--mono">${radio.preamble_length} symbols</span>
                </div>
            </div>
            <button class="radio-save-btn" id="radio-save-config">Save Radio Settings</button>
        `;

        const presetSelect = document.getElementById('radio-preset');
        presetSelect.addEventListener('change', () => {
            const name = presetSelect.value;
            if (name === 'CUSTOM') return;
            const p = presets.find(x => x.name === name);
            if (!p) return;
            document.getElementById('radio-sf').textContent = `SF${p.sf}`;
            document.getElementById('radio-bw').textContent = `${p.bw_khz} kHz`;
            document.getElementById('radio-cr').textContent = p.cr;
        });

        const regionSelect = document.getElementById('radio-region');
        regionSelect.addEventListener('change', () => {
            const r = regions.find(x => x.id === regionSelect.value);
            if (r) document.getElementById('radio-freq').value = r.frequency_mhz;
        });

        document.getElementById('radio-save-config').addEventListener('click', async () => {
            const radioPayload = {};
            const selectedRegion = regionSelect.value;
            if (selectedRegion !== radio.region) radioPayload.region = selectedRegion;

            const selectedPreset = presetSelect.value;
            if (selectedPreset !== 'CUSTOM') {
                radioPayload.preset = selectedPreset;
            }

            const freqVal = parseFloat(document.getElementById('radio-freq').value);
            if (!isNaN(freqVal) && freqVal !== radio.frequency_mhz) {
                radioPayload.frequency_mhz = freqVal;
            }

            const txPower = parseInt(document.getElementById('radio-tx-power').value);
            const hopLimit = parseInt(document.getElementById('radio-hop-limit').value);
            const txPayload = {};
            if (!isNaN(txPower) && txPower !== tx.tx_power_dbm) txPayload.tx_power_dbm = txPower;
            if (!isNaN(hopLimit) && hopLimit !== tx.hop_limit) txPayload.hop_limit = hopLimit;

            if (Object.keys(radioPayload).length > 0) {
                const result = await this._putConfig('/api/config/radio', radioPayload);
                if (result && result.restart_required) this._showRestartBar();
            }
            if (Object.keys(txPayload).length > 0) {
                await this._saveTransmit(txPayload);
            }

            this._showToast('Radio settings saved');
        });
    }

    _renderCompanion(c) {
        const el = document.getElementById('radio-companion');
        const mc = c.meshcore || {};
        const radio = mc.radio || {};

        if (!mc.connected) {
            el.innerHTML = `
                <h3 class="radio-card__title">MeshCore Companion</h3>
                <div class="radio-companion-offline">
                    <span class="radio-status radio-status--off">NOT CONNECTED</span>
                    <p class="radio-companion__hint">Connect a MeshCore USB companion to enable MC messaging.</p>
                </div>
            `;
            return;
        }

        el.innerHTML = `
            <h3 class="radio-card__title">MeshCore Companion</h3>
            <div class="radio-companion-grid">
                <div class="radio-field"><label class="radio-label">Status</label><span class="radio-status radio-status--on">CONNECTED</span></div>
                <div class="radio-field"><label class="radio-label">Name</label><span class="radio-value">${this._esc(mc.companion_name || 'Unknown')}</span></div>
                <div class="radio-field"><label class="radio-label">Frequency</label><span class="radio-value radio-value--mono">${radio.frequency_mhz || '?'} MHz</span></div>
                <div class="radio-field"><label class="radio-label">Bandwidth</label><span class="radio-value radio-value--mono">${radio.bandwidth_khz || '?'} kHz</span></div>
                <div class="radio-field"><label class="radio-label">SF</label><span class="radio-value radio-value--mono">SF${radio.spreading_factor || '?'}</span></div>
                <div class="radio-field"><label class="radio-label">TX Power</label><span class="radio-value radio-value--mono">${radio.tx_power || '?'} dBm</span></div>
            </div>
            <div class="radio-companion__actions">
                <button class="radio-save-btn radio-save-btn--secondary" id="radio-mc-advert">Send Advert</button>
                <button class="radio-save-btn radio-save-btn--secondary" id="radio-mc-refresh">Refresh</button>
            </div>
        `;

        document.getElementById('radio-mc-advert').addEventListener('click', async () => {
            try {
                await fetch('/api/messages/send', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ text: '', destination: 'advert', protocol: 'meshcore' }),
                });
                this._showToast('Advert sent');
            } catch (e) {
                this._showToast('Advert failed');
            }
        });

        document.getElementById('radio-mc-refresh').addEventListener('click', () => this._loadConfig());
    }

    async _saveTransmit(payload) {
        await this._putConfig('/api/config/transmit', payload);
        await this._loadConfig();
    }

    async _saveIdentity(payload) {
        const result = await this._putConfig('/api/config/identity', payload);
        if (result) {
            this._showToast('Identity saved');
            if (result.restart_required) this._showRestartBar();
        }
        await this._loadConfig();
    }

    async _putConfig(url, payload) {
        try {
            const res = await fetch(url, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                this._showToast(`Error: ${err.detail || res.status}`);
                return null;
            }
            return await res.json();
        } catch (e) {
            this._showToast('Save failed: ' + e.message);
            return null;
        }
    }

    _showRestartBar() {
        this._restartNeeded = true;
        const bar = document.getElementById('radio-restart-bar');
        if (bar) bar.style.display = 'flex';
    }

    _showToast(msg) {
        let toast = document.getElementById('radio-toast');
        if (!toast) {
            toast = document.createElement('div');
            toast.id = 'radio-toast';
            toast.className = 'radio-toast';
            document.body.appendChild(toast);
        }
        toast.textContent = msg;
        toast.classList.add('radio-toast--visible');
        setTimeout(() => toast.classList.remove('radio-toast--visible'), 2500);
    }

    _esc(str) {
        const el = document.createElement('span');
        el.textContent = str || '';
        return el.innerHTML;
    }
}

window.radioSettings = new RadioSettings();
