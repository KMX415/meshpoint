/**
 * Configuration panel orchestrator.
 *
 * Single responsibility: load ``/api/config`` once, mount the right
 * card into each Configuration subsection container, and re-render
 * every card on data changes. Cards reuse the existing radio_*
 * implementations where the contract matches; new cards
 * (Transmit, MQTT, GPS) live under ``frontend/js/configuration/``.
 *
 * Each subsection lazy-mounts on first navigation so we don't
 * inflate every form's DOM at boot.
 */

class ConfigurationPanel {
    constructor() {
        this._config = null;
        this._cards = new Map();
        this._mounted = new Set();
    }

    bind() {
        // No global wiring needed; mounting happens in onSectionEnter().
    }

    async onSectionEnter(route) {
        if (!route.startsWith('configuration/')) return;
        const section = route.slice('configuration/'.length);
        if (!this._config) await this._loadConfig();
        this._mountSection(section);
        this._renderAll();
    }

    async _loadConfig() {
        try {
            const res = await fetch('/api/config', { credentials: 'same-origin' });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            this._config = await res.json();
        } catch (e) {
            console.error('Configuration load failed:', e);
            this._config = {};
        }
    }

    _mountSection(section) {
        if (this._mounted.has(section)) return;
        const api = this._buildApi();

        if (section === 'identity' && window.RadioIdentityCard) {
            const host = document.getElementById('cfg-identity-panel');
            if (host) {
                host.innerHTML = '';
                const card = new window.RadioIdentityCard(api);
                card.mount(host);
                this._cards.set('identity', card);
            }
        } else if (section === 'radio' && window.RadioConfigCard) {
            const host = document.getElementById('cfg-radio-panel');
            if (host) {
                host.innerHTML = `
                    <div class="cfg-section">
                        <div data-cfg-radio></div>
                        <div data-cfg-nodeinfo></div>
                    </div>
                `;
                const radio = new window.RadioConfigCard(api);
                radio.mount(host.querySelector('[data-cfg-radio]'));
                this._cards.set('radio', radio);
                if (window.RadioNodeInfoCard) {
                    const nodeinfo = new window.RadioNodeInfoCard(api);
                    nodeinfo.mount(host.querySelector('[data-cfg-nodeinfo]'));
                    this._cards.set('nodeinfo', nodeinfo);
                }
            }
        } else if (section === 'channels' && window.RadioChannels) {
            const host = document.getElementById('cfg-channels-panel');
            if (host) {
                host.innerHTML = '';
                const card = new window.RadioChannels(host);
                this._cards.set('channels', card);
            }
        } else if (section === 'transmit' && window.TransmitConfigCard) {
            const host = document.getElementById('cfg-transmit-panel');
            if (host) {
                host.innerHTML = '';
                const card = new window.TransmitConfigCard(api);
                card.mount(host);
                this._cards.set('transmit', card);
            }
        } else if (section === 'mqtt' && window.MqttConfigCard) {
            const host = document.getElementById('cfg-mqtt-panel');
            if (host) {
                host.innerHTML = '';
                const card = new window.MqttConfigCard(api);
                card.mount(host);
                this._cards.set('mqtt', card);
            }
        } else if (section === 'gps' && window.GpsConfigCard) {
            const host = document.getElementById('cfg-gps-panel');
            if (host) {
                host.innerHTML = '';
                const card = new window.GpsConfigCard(api);
                card.mount(host);
                this._cards.set('gps', card);
            }
        }
        this._mounted.add(section);
    }

    _renderAll() {
        if (!this._config) return;
        this._cards.forEach((card, key) => {
            try {
                if (key === 'channels') {
                    card.render(this._config.channels);
                } else {
                    card.render(this._config);
                }
            } catch (e) {
                console.error('Configuration card render failed:', e);
            }
        });
    }

    _buildApi() {
        const self = this;
        return {
            put: (url, body) => self._request('PUT', url, body),
            post: (url, body) => self._request('POST', url, body),
            refresh: () => self._loadConfig().then(() => self._renderAll()),
            toast: (msg) => self._toast(msg),
            signalRestart: (msg) => self._toast(msg + ' Restart service from Settings → Dangerous to apply.'),
            escape: (str) => {
                const el = document.createElement('span');
                el.textContent = str || '';
                return el.innerHTML;
            },
        };
    }

    async _request(method, url, body) {
        const init = { method, headers: { 'Content-Type': 'application/json' }, credentials: 'same-origin' };
        if (body !== undefined && body !== null) init.body = JSON.stringify(body);
        try {
            const res = await fetch(url, init);
            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                this._toast(`Error: ${err.detail || res.status}`);
                return null;
            }
            return await res.json();
        } catch (e) {
            this._toast(`Save failed: ${e.message}`);
            return null;
        }
    }

    _toast(text) {
        let toast = document.getElementById('cfg-toast');
        if (!toast) {
            toast = document.createElement('div');
            toast.id = 'cfg-toast';
            toast.className = 'cfg-toast';
            document.body.appendChild(toast);
        }
        toast.textContent = text;
        toast.classList.add('cfg-toast--visible');
        setTimeout(() => toast.classList.remove('cfg-toast--visible'), 2800);
    }
}

window.ConfigurationPanel = ConfigurationPanel;
