/**
 * Configuration panel orchestrator.
 *
 * Single responsibility: load ``/api/config`` once, mount the right
 * editable card into each Configuration subsection container, and
 * re-render every card on data changes. The seven subsections
 * (Identity, Radio, Channels, MeshCore, Transmit, MQTT, GPS, Advanced) all
 * mount dedicated editable cards from ``frontend/js/configuration/``.
 * The observational read-only versions (``RadioIdentityCard``,
 * ``RadioConfigCard``, ``RadioChannels``, ``RadioCompanionCard``)
 * live on the top-level Radio page only.
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
        await this._loadConfig();
        this._mountSection(section);
        this._renderAll();
        if (section === 'radio') this._scrollToFocusTarget();
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

        if (section === 'identity' && window.IdentityConfigCard) {
            const host = document.getElementById('cfg-identity-panel');
            if (host) {
                host.innerHTML = '';
                const card = new window.IdentityConfigCard(api);
                card.mount(host);
                this._cards.set('identity', card);
            }
        } else if (section === 'radio' && window.RadioConfigEditCard) {
            const host = document.getElementById('cfg-radio-panel');
            if (host) {
                host.innerHTML = `
                    <div class="cfg-section">
                        <div data-cfg-radio></div>
                        <div data-cfg-nodeinfo-edit></div>
                        <div data-cfg-nodeinfo-status></div>
                    </div>
                `;
                const radio = new window.RadioConfigEditCard(api);
                radio.mount(host.querySelector('[data-cfg-radio]'));
                this._cards.set('radio', radio);
                if (window.NodeInfoConfigCard) {
                    const edit = new window.NodeInfoConfigCard(api);
                    edit.mount(host.querySelector('[data-cfg-nodeinfo-edit]'));
                    this._cards.set('nodeinfo-edit', edit);
                }
                if (window.RadioNodeInfoCard) {
                    const status = new window.RadioNodeInfoCard(api);
                    status.mount(host.querySelector('[data-cfg-nodeinfo-status]'));
                    this._cards.set('nodeinfo-status', status);
                }
            }
        } else if (section === 'channels') {
            const host = document.getElementById('cfg-channels-panel');
            if (host) {
                host.innerHTML = '<div class="cfg-section" data-channels-mount></div>';
                const mount = host.querySelector('[data-channels-mount]');
                if (window.QuickDeployCard) {
                    const quick = new window.QuickDeployCard(api);
                    quick.mount(mount);
                    this._cards.set('quick-deploy', quick);
                }
                if (window.ChannelsConfigCard) {
                    const card = new window.ChannelsConfigCard(api);
                    card.mount(mount);
                    this._cards.set('channels', card);
                }
            }
        } else if (section === 'meshcore' && window.MeshcoreConfigCard) {
            const host = document.getElementById('cfg-meshcore-panel');
            if (host) {
                host.innerHTML = '';
                const card = new window.MeshcoreConfigCard(api);
                card.mount(host);
                this._cards.set('meshcore', card);
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
        } else if (section === 'advanced' && window.AdvancedConfigCard) {
            const host = document.getElementById('cfg-advanced-panel');
            if (host) {
                host.innerHTML = '';
                const card = new window.AdvancedConfigCard(api);
                card.mount(host);
                this._cards.set('advanced', card);
            }
        }
        this._mounted.add(section);
    }

    _renderAll() {
        if (!this._config) return;
        this._cards.forEach((card) => {
            try {
                card.render(this._config);
            } catch (e) {
                console.error('Configuration card render failed:', e);
            }
        });
    }

    _buildApi() {
        const self = this;
        return {
            get: (url) => self._request('GET', url, undefined),
            put: (url, body) => self._request('PUT', url, body),
            post: (url, body) => self._request('POST', url, body),
            refresh: () => self._loadConfig().then(() => self._renderAll()),
            toast: (msg) => self._toast(msg),
            signalRestart: (msg) => self._toast(
                msg + ' Restart the service from Settings → System to apply.',
            ),
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
        const isGet = method === 'GET';
        try {
            const res = await fetch(url, init);
            if (!res.ok) {
                if (!isGet) {
                    const err = await res.json().catch(() => ({}));
                    this._toast(`Error: ${err.detail || res.status}`);
                }
                return null;
            }
            return await res.json();
        } catch (e) {
            if (!isGet) this._toast(`Save failed: ${e.message}`);
            return null;
        }
    }

    _scrollToFocusTarget() {
        const targetId = sessionStorage.getItem('cfg-scroll-target');
        if (!targetId) return;
        sessionStorage.removeItem('cfg-scroll-target');
        requestAnimationFrame(() => {
            const el = document.getElementById(targetId);
            if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
        });
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
