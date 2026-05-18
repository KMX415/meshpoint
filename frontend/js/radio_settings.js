/**
 * Radio tab orchestrator (observational, v0.7.4).
 *
 * Renders the Radio status dashboard: a console-style header strip,
 * a stack of read-only telemetry cards, and a footer. All editing
 * was relocated to Configuration → Radio / Identity / Channels /
 * Transmit; the orchestrator no longer owns Save/restart wiring.
 *
 * Cards rendered, in order:
 *   - RadioStatusCard      (TX duty gauge + TX-enabled indicator)
 *   - RadioIdentityCard    (long/short name, node ID)
 *   - RadioConfigCard      (region/preset/freq/power readouts)
 *   - RadioNodeInfoCard    (countdown + last-sent + interval)
 *   - RadioChannels        (read-only channel table)
 *   - RadioCompanionCard   (MeshCore companion: operational, kept)
 *
 * Each card receives a shared ``api`` helper (put / post / refresh /
 * toast / escape) so the few operational actions still living in
 * this tab (Companion advert/refresh) keep working.
 */
class RadioSettings {
    constructor() {
        this._initialized = false;
        this._config = null;
        this._cards = [];
        this._channels = null;
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
                            <strong>Radio is observational.</strong>
                            One-stop view of every live radio detail. Each card
                            links to its editor in Configuration.
                        </span>
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
                            Live values · refreshes on tab activation
                        </span>
                    </div>
                </div>
            </div>
        `;
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
            put:     (url, body) => self._request('PUT', url, body),
            post:    (url, body) => self._request('POST', url, body),
            refresh: () => self._loadConfig(),
            toast:   (msg) => self._showToast(msg),
            escape:  (str) => self._escape(str),
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
