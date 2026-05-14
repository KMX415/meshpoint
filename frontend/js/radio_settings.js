/**
 * Radio tab orchestrator.
 *
 * Owns the page shell (console header, card stack, restart bar, footer,
 * toast) and dispatches /api/config payloads to per-card modules:
 *   - RadioStatusCard
 *   - RadioIdentityCard
 *   - RadioConfigCard
 *   - RadioNodeInfoCard
 *   - RadioChannels (legacy, in radio_channels.js)
 *   - RadioCompanionCard
 *
 * Each card receives a shared ``api`` helper (put / post / refresh /
 * toast / signalRestart / escape) so cross-cutting concerns live in
 * one place. Adding a new card means: write a class with the same
 * contract, mount it in ``_buildCards``, and add a render call in
 * ``_renderAll``.
 */
class RadioSettings {
    constructor() {
        this._initialized = false;
        this._config = null;
        this._cards = [];
        this._channels = null;
        this._restartShown = false;
    }

    async onActivated() {
        if (!this._initialized) {
            this._buildShell();
            this._buildCards();
            this._initialized = true;
        }
        await this._loadConfig();
    }

    _buildShell() {
        const panel = document.getElementById('radio-panel');
        if (!panel) return;

        panel.innerHTML = `
            <div class="r-stage">
                <div class="r-shell">
                    <div class="r-observational-banner" role="status">
                        <span class="r-observational-banner__icon" aria-hidden="true">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="16" height="16">
                                <circle cx="12" cy="12" r="10"/>
                                <line x1="12" y1="8" x2="12" y2="12"/>
                                <line x1="12" y1="16" x2="12.01" y2="16"/>
                            </svg>
                        </span>
                        <span class="r-observational-banner__text">
                            <strong>Radio is observational in v0.7.4.</strong>
                            Editing has moved to <a href="#/configuration/radio" class="r-observational-banner__link">Configuration &rsaquo; Radio</a>,
                            <a href="#/configuration/identity" class="r-observational-banner__link">Identity</a>,
                            <a href="#/configuration/channels" class="r-observational-banner__link">Channels</a>, and
                            <a href="#/configuration/transmit" class="r-observational-banner__link">Transmit</a>.
                        </span>
                    </div>

                    <div class="restart-bar" id="r-restart-bar">
                        <span class="restart-bar__icon">!</span>
                        <span class="restart-bar__msg" id="r-restart-msg">
                            Some changes require a service restart to take effect.
                        </span>
                        <button class="r-btn r-btn--warn"
                                id="r-restart-btn">Restart Service</button>
                    </div>

                    <div class="r-console">
                        <span class="r-console__prompt">admin@meshpoint:~$</span>
                        <span class="r-console__cursor">_</span>
                        <span class="r-console__cmd">radio status</span>
                        <div class="r-console__right">
                            <span class="r-heartbeat r-heartbeat--ok"></span>
                            <span class="r-console__meta" id="r-shell-meta">--</span>
                        </div>
                    </div>

                    <div class="r-card-row r-card-row--hero">
                        <div id="r-card-status"></div>
                        <div id="r-card-identity"></div>
                    </div>
                    <div id="r-card-config"></div>
                    <div id="r-card-nodeinfo"></div>
                    <div id="r-card-channels"></div>
                    <div id="r-card-companion"></div>

                    <div class="r-console-foot">
                        <span class="r-console-foot__hint">
                            <kbd>Tab</kbd> next field
                        </span>
                        <span class="r-console-foot__sep">|</span>
                        <span class="r-console-foot__hint">
                            <kbd>Esc</kbd> close
                        </span>
                        <span class="r-console-foot__sep">|</span>
                        <span class="r-console-foot__hint" id="r-build-stamp">
                            radio v0.7.1
                        </span>
                    </div>
                </div>
            </div>
        `;

        document.getElementById('r-restart-btn').addEventListener(
            'click', () => this._restartService(),
        );
    }

    _buildCards() {
        const api = this._buildApi();

        const status = new RadioStatusCard(api);
        status.mount(document.getElementById('r-card-status'));
        this._cards.push(status);

        const identity = new RadioIdentityCard(api);
        identity.mount(document.getElementById('r-card-identity'));
        this._cards.push(identity);

        const radioConfig = new RadioConfigCard(api);
        radioConfig.mount(document.getElementById('r-card-config'));
        this._cards.push(radioConfig);

        const nodeinfo = new RadioNodeInfoCard(api);
        nodeinfo.mount(document.getElementById('r-card-nodeinfo'));
        this._cards.push(nodeinfo);

        this._channels = new RadioChannels(
            document.getElementById('r-card-channels'),
        );

        const companion = new RadioCompanionCard(api);
        companion.mount(document.getElementById('r-card-companion'));
        this._cards.push(companion);
    }

    _buildApi() {
        const self = this;
        return {
            put:           (url, body) => self._request('PUT', url, body),
            post:          (url, body) => self._request('POST', url, body),
            refresh:       () => self._loadConfig(),
            toast:         (msg) => self._showToast(msg),
            signalRestart: (reason) => self._showRestartBar(reason),
            escape:        (str) => self._escape(str),
        };
    }

    async _loadConfig() {
        try {
            const res = await fetch('/api/config');
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            this._config = await res.json();
            this._renderAll();
        } catch (e) {
            console.error('Failed to load config:', e);
            this._showToast(`Load failed: ${e.message}`);
        }
    }

    _renderAll() {
        if (!this._config) return;
        this._cards.forEach((card) => {
            try {
                card.render(this._config);
            } catch (e) {
                console.error('Card render failed:', e);
            }
        });
        if (this._channels) this._channels.render(this._config.channels);
        this._renderShellMeta();
    }

    _renderShellMeta() {
        const meta = document.getElementById('r-shell-meta');
        if (!meta) return;
        const radio = this._config.radio || {};
        const region = radio.region || '--';
        const freq = radio.frequency_mhz ? `${radio.frequency_mhz} MHz` : '';
        meta.textContent = freq ? `${region} -- ${freq}` : region;
    }

    async _request(method, url, body) {
        const init = { method, headers: { 'Content-Type': 'application/json' } };
        if (body !== undefined && body !== null) {
            init.body = JSON.stringify(body);
        }
        try {
            const res = await fetch(url, init);
            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                this._showToast(`Error: ${err.detail || res.status}`);
                return null;
            }
            return await res.json();
        } catch (e) {
            this._showToast(`Save failed: ${e.message}`);
            return null;
        }
    }

    async _restartService() {
        const ok = confirm(
            'Restart the Meshpoint service? This briefly interrupts packet capture.',
        );
        if (!ok) return;
        try {
            await fetch('/api/config/restart', { method: 'POST' });
            const msg = document.getElementById('r-restart-msg');
            if (msg) msg.textContent = 'Restarting... reloading in 10 seconds.';
            setTimeout(() => location.reload(), 10000);
        } catch (e) {
            this._showToast(`Restart failed: ${e.message}`);
        }
    }

    _showRestartBar(reason) {
        this._restartShown = true;
        const bar = document.getElementById('r-restart-bar');
        if (!bar) return;
        bar.classList.add('restart-bar--visible');
        if (reason) {
            const msg = document.getElementById('r-restart-msg');
            if (msg) msg.textContent = reason;
        }
    }

    _showToast(text) {
        let toast = document.getElementById('r-toast');
        if (!toast) {
            toast = document.createElement('div');
            toast.id = 'r-toast';
            toast.className = 'r-toast';
            document.body.appendChild(toast);
        }
        toast.textContent = text;
        toast.classList.add('r-toast--visible');
        setTimeout(() => toast.classList.remove('r-toast--visible'), 2500);
    }

    _escape(str) {
        const el = document.createElement('span');
        el.textContent = str || '';
        return el.innerHTML;
    }
}

window.radioSettings = new RadioSettings();
