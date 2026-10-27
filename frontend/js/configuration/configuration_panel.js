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
        this._scrollToFocusTarget();
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
        const pimeshMc = window.PlatformContext?.isPimesh(this._config)
            && this._config.device.radio_protocol === 'meshcore';

        if (section === 'identity' && window.IdentityConfigCard) {
            const host = document.getElementById('cfg-identity-panel');
            if (host) {
                host.innerHTML = '';
                const card = new window.IdentityConfigCard(api);
                card.mount(host);
                this._cards.set('identity', card);
            }
        } else if (section === 'radio') {
            const host = document.getElementById('cfg-radio-panel');
            const isNode = window.PlatformContext
                && window.PlatformContext.isNodePlatform(this._config);
            if (host) {
                host.innerHTML = `
                    <div class="cfg-section">
                        <div data-cfg-pimesh></div>
                        <div data-cfg-pimesh-behavior></div>
                        <div data-cfg-wismesh-hero></div>
                        <div data-cfg-radio></div>
                        <div data-cfg-nodeinfo-edit></div>
                        <div data-cfg-nodeinfo-status></div>
                        <div data-cfg-telemetry-edit></div>
                        <div data-cfg-telemetry-status></div>
                    </div>
                `;
                if (window.PlatformContext?.isPimesh(this._config) && window.PimeshProtocolCard) {
                    const protocolCard = new window.PimeshProtocolCard(api);
                    protocolCard.mount(host.querySelector('[data-cfg-pimesh]'));
                    this._cards.set('pimesh', protocolCard);
                    const mt = this._config.device.radio_protocol === 'meshtastic';
                    if (mt) {
                        const behaviorCard = new window.PimeshBehaviorCard(api);
                        behaviorCard.mount(host.querySelector('[data-cfg-pimesh-behavior]'));
                        this._cards.set('pimesh-behavior', behaviorCard);
                        const card = new window.WismeshRadioCard(api);
                        card.mount(host.querySelector('[data-cfg-radio]'));
                        this._cards.set('pimesh-radio', card);
                    } else {
                        this._mountMeshcoreLink(host.querySelector('[data-cfg-radio]'));
                    }
                } else if (isNode && window.WismeshStatusCard) {
                    const hero = new window.WismeshStatusCard(api);
                    hero.mount(host.querySelector('[data-cfg-wismesh-hero]'));
                    this._cards.set('wismesh-hero', hero);
                    const heroHost = host.querySelector('[data-cfg-radio]');
                    if (heroHost) heroHost.style.display = 'none';
                } else if (window.RadioConfigEditCard) {
                    const radio = new window.RadioConfigEditCard(api);
                    radio.mount(host.querySelector('[data-cfg-radio]'));
                    this._cards.set('radio', radio);
                }
                if (!window.PlatformContext?.isPimesh(this._config) && window.NodeInfoConfigCard) {
                    const edit = new window.NodeInfoConfigCard(api);
                    edit.mount(host.querySelector('[data-cfg-nodeinfo-edit]'));
                    this._cards.set('nodeinfo-edit', edit);
                }
                if (!window.PlatformContext?.isPimesh(this._config) && window.RadioNodeInfoCard) {
                    const status = new window.RadioNodeInfoCard(api);
                    status.mount(host.querySelector('[data-cfg-nodeinfo-status]'));
                    this._cards.set('nodeinfo-status', status);
                }
                if (!window.PlatformContext?.isPimesh(this._config) && window.TelemetryBroadcastCard) {
                    const telem = new window.TelemetryBroadcastCard(api);
                    telem.mount(host.querySelector('[data-cfg-telemetry-edit]'));
                    this._cards.set('telemetry-edit', telem);
                }
                if (!window.PlatformContext?.isPimesh(this._config) && window.BroadcastStatusCard) {
                    const telemStatus = new window.BroadcastStatusCard(api, {
                        title: 'Telemetry Broadcast',
                        configKey: 'telemetry',
                        editRoute: '#/configuration/radio',
                        scrollTarget: 'cfg-telemetry-interval',
                    });
                    telemStatus.mount(host.querySelector('[data-cfg-telemetry-status]'));
                    this._cards.set('telemetry-status', telemStatus);
                }
            }
        } else if (section === 'channels') {
            const host = document.getElementById('cfg-channels-panel');
            if (host) {
                host.innerHTML = `
                    <div class="cfg-section">
                        <div data-quick-deploy-mount></div>
                        <div data-channels-mount></div>
                    </div>
                `;
                const pimesh = window.PlatformContext?.isPimesh(this._config);
                const pimeshMc = pimesh && this._config.device.radio_protocol === 'meshcore';
                if (window.QuickDeployCard && !pimesh) {
                    const quickMount = host.querySelector('[data-quick-deploy-mount]');
                    const quick = new window.QuickDeployCard(api);
                    quick.mount(quickMount);
                    this._cards.set('quick-deploy', quick);
                }
                if (pimeshMc) {
                    this._mountMeshcoreLink(host.querySelector('[data-channels-mount]'));
                } else if (window.ChannelsConfigCard) {
                    const channelsMount = host.querySelector('[data-channels-mount]');
                    const card = new window.ChannelsConfigCard(api);
                    card.mount(channelsMount);
                    this._cards.set('channels', card);
                }
            }
        } else if (section === 'meshcore' && window.MeshcoreConfigCard) {
            const host = document.getElementById('cfg-meshcore-panel');
            if (host) {
                host.innerHTML = `<div class="cfg-section">
                        <div data-cfg-meshcore-advert></div>
                        <div data-cfg-meshcore-advert-status></div>
                    </div>
                    <div data-cfg-meshcore-main></div>
                    <div class="cfg-section"><div data-cfg-meshcore-behavior></div></div>`;
                const card = new window.MeshcoreConfigCard(api);
                card.mount(host.querySelector('[data-cfg-meshcore-main]'));
                this._cards.set('meshcore', card);
                if (pimeshMc) {
                    const behavior = new window.PimeshBehaviorCard(api);
                    behavior.mount(host.querySelector('[data-cfg-meshcore-behavior]'));
                    this._cards.set('pimesh-behavior', behavior);
                    const advert = new window.PositionBroadcastCard(api, { meshcore: true });
                    advert.mount(host.querySelector('[data-cfg-meshcore-advert]'));
                    this._cards.set('meshcore-advert', advert);
                    const status = new window.BroadcastStatusCard(api, {
                        title: 'MeshCore advertisements',
                        configKey: 'position',
                        editRoute: '#/configuration/meshcore',
                        scrollTarget: 'cfg-meshcore-advert-interval',
                    });
                    status.mount(host.querySelector('[data-cfg-meshcore-advert-status]'));
                    this._cards.set('meshcore-advert-status', status);
                }
            }
        } else if (section === 'serial' && window.SerialConfigCard) {
            const host = document.getElementById('cfg-serial-panel');
            if (host) {
                host.innerHTML = '';
                const card = new window.SerialConfigCard(api);
                card.mount(host);
                this._cards.set('serial', card);
            }
        } else if (section === 'firmware') {
            const host = document.getElementById('cfg-firmware-panel');
            if (host && window.PlatformContext?.isPimesh(this._config)) {
                host.innerHTML = `<article class="cfg-card"><header class="cfg-card__head">
                    <h3 class="cfg-card__title">PiMesh software</h3>
                    <p class="cfg-card__hint">PiMesh runs its radio software on the Pi.
                    Both protocol backends are installed with Meshpoint. Use the PiMesh installer
                    to update them while preserving each protocol’s configuration.</p>
                    </header><p>Change the active protocol in
                    <a href="#/configuration/radio">Configuration → Radio</a>.</p></article>`;
                this._mounted.add(section);
                return;
            }
            if (host) {
                host.innerHTML = `
                    <div class="cfg-section">
                        <div data-cfg-firmware-meshcore></div>
                        <div data-cfg-firmware-meshtastic></div>
                    </div>
                `;
                if (window.MeshcoreFirmwareConfigCard) {
                    const mc = new window.MeshcoreFirmwareConfigCard(api);
                    mc.mount(host.querySelector('[data-cfg-firmware-meshcore]'));
                    this._cards.set('firmware-meshcore', mc);
                }
                if (window.MeshtasticFirmwareConfigCard) {
                    const mt = new window.MeshtasticFirmwareConfigCard(api);
                    mt.mount(host.querySelector('[data-cfg-firmware-meshtastic]'));
                    this._cards.set('firmware-meshtastic', mt);
                }
            }
        } else if (section === 'transmit' && window.TransmitConfigCard) {
            const host = document.getElementById('cfg-transmit-panel');
            const isNode = window.PlatformContext
                && window.PlatformContext.isNodePlatform(this._config);
            if (host) {
                host.innerHTML = '';
                if (window.PlatformContext?.isPimesh(this._config)
                    && this._config.device.radio_protocol === 'meshcore') {
                    this._mountMeshcoreLink(host);
                } else if (isNode && window.WismeshRadioCard) {
                    const card = new window.WismeshRadioCard(api);
                    card.mount(host);
                    this._cards.set('transmit', card);
                } else if (window.TransmitConfigCard) {
                    const card = new window.TransmitConfigCard(api);
                    card.mount(host);
                    this._cards.set('transmit', card);
                }
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
                host.innerHTML = `
                    <div class="cfg-section">
                        <div data-cfg-gps-main></div>
                        <div data-cfg-position-edit></div>
                        <div data-cfg-position-status></div>
                    </div>
                `;
                const card = new window.GpsConfigCard(api);
                card.mount(host.querySelector('[data-cfg-gps-main]'));
                this._cards.set('gps', card);
                if (!pimeshMc && window.PositionBroadcastCard) {
                    const pos = new window.PositionBroadcastCard(api);
                    pos.mount(host.querySelector('[data-cfg-position-edit]'));
                    this._cards.set('position-edit', pos);
                }
                if (!pimeshMc && window.BroadcastStatusCard) {
                    const posStatus = new window.BroadcastStatusCard(api, {
                        title: 'Position Broadcast',
                        configKey: 'position',
                        editRoute: '#/configuration/gps',
                        scrollTarget: 'cfg-position-interval',
                    });
                    posStatus.mount(host.querySelector('[data-cfg-position-status]'));
                    this._cards.set('position-status', posStatus);
                }
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

    _mountMeshcoreLink(host) {
        host.innerHTML = `<p class="cfg-callout">Manage MeshCore channels, radio settings,
            transmit, device behavior and advertisements in
            <a class="cfg-inline-link" href="#/configuration/meshcore">MeshCore settings</a>.</p>`;
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
            lastError: () => self._lastRequestError || '',
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
        this._lastRequestError = '';
        try {
            const res = await fetch(url, init);
            if (!res.ok) {
                // Credit: javastraat/meshpoint 676f7e3 — toast GET failures too
                // (e.g. empty Firmware dropdowns on GitHub rate-limit).
                const err = await res.json().catch(() => ({}));
                const detail = this._formatErrorDetail(err.detail, res.status);
                this._lastRequestError = detail;
                this._toast(`${isGet ? 'Error' : 'Save failed'}: ${detail}`);
                return null;
            }
            return await res.json();
        } catch (e) {
            this._lastRequestError = e.message || 'request failed';
            this._toast(`${isGet ? 'Error' : 'Save failed'}: ${e.message}`);
            return null;
        }
    }

    _formatErrorDetail(detail, status) {
        if (detail == null || detail === '') return String(status);
        if (typeof detail === 'string') return detail;
        if (Array.isArray(detail)) {
            return detail.map((d) => (d && d.msg) || JSON.stringify(d)).join('; ');
        }
        try {
            return JSON.stringify(detail);
        } catch (_e) {
            return String(detail);
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
