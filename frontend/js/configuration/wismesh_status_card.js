/**
 * Configuration → Radio: WisMesh status hero (node platform only).
 */

class WismeshStatusCard {
    constructor(api) {
        this._api = api;
        this._root = null;
    }

    mount(root) {
        this._root = root;
        this._root.innerHTML = `
            <article class="cfg-card cfg-card--hero wismesh-hero" data-wismesh-hero>
                <header class="cfg-card__head">
                    <h3 class="cfg-card__title">WisMesh HAT</h3>
                    <p class="cfg-card__hint">
                        Meshtastic RF is owned by meshtasticd on this Pi.
                        Do not run <code>meshtastic --host</code> while Meshpoint is running.
                    </p>
                </header>
                <div class="wismesh-hero__grid">
                    <div class="wismesh-hero__pill" data-wismesh-bridge>Bridge: --</div>
                    <div class="wismesh-hero__pill" data-wismesh-module>Module: --</div>
                    <div class="wismesh-hero__id">
                        <span class="wismesh-hero__id-label">Node ID</span>
                        <code class="wismesh-hero__id-val" data-wismesh-node-id>--</code>
                    </div>
                    <p class="cfg-field__hint" data-wismesh-fw></p>
                </div>
            </article>
        `;
        this._bridgeEl = this._root.querySelector('[data-wismesh-bridge]');
        this._moduleEl = this._root.querySelector('[data-wismesh-module]');
        this._nodeIdEl = this._root.querySelector('[data-wismesh-node-id]');
        this._fwEl = this._root.querySelector('[data-wismesh-fw]');
    }

    render(config) {
        if (!this._root) return;
        const md = window.PlatformContext.meshtasticdRuntime(config);
        const yaml = window.PlatformContext.meshtasticdConfig(config);
        const connected = Boolean(md.bridge_connected);
        this._bridgeEl.textContent = connected
            ? 'Bridge: connected'
            : 'Bridge: disconnected';
        this._bridgeEl.classList.toggle('wismesh-hero__pill--ok', connected);
        this._bridgeEl.classList.toggle('wismesh-hero__pill--warn', !connected);

        const badge = yaml.module_badge || md.module_badge || '';
        const preset = yaml.preset || '';
        this._moduleEl.textContent = badge
            ? `Module: ${badge}`
            : (preset ? `Preset file: ${preset}` : 'Module: --');

        const nodeHex = md.local_node_id_hex || '';
        this._nodeIdEl.textContent = nodeHex
            ? (nodeHex.startsWith('!') ? nodeHex : `!${nodeHex}`)
            : '--';

        const fw = md.firmware_version || '';
        this._fwEl.textContent = fw
            ? `meshtasticd firmware ${fw}`
            : '';
    }
}

window.WismeshStatusCard = WismeshStatusCard;
