/** PiMesh backend controls. Forwarding itself belongs to the radio daemon. */
class PimeshBehaviorCard {
    constructor(api) {
        this._api = api;
        this._busy = false;
        this._actual = null;
    }

    mount(root) {
        this._root = root;
        root.innerHTML = `<article class="cfg-card">
            <header class="cfg-card__head">
                <h3 class="cfg-card__title">Device behavior</h3>
                <p class="cfg-card__hint" data-behavior-intro></p>
            </header>
            <form class="cfg-form">
                <label class="cfg-field">
                    <span class="cfg-field__label" data-behavior-label>Device role</span>
                    <select class="cfg-field__input" data-behavior-role disabled></select>
                    <span class="cfg-field__hint" data-behavior-hint></span>
                </label>
                <label class="cfg-field" data-behavior-filter-field hidden>
                    <span class="cfg-field__label">Rebroadcast filter</span>
                    <select class="cfg-field__input" data-behavior-filter disabled></select>
                    <span class="cfg-field__hint">Controls which packets may be relayed. Client mute does not relay other devices' packets.</span>
                </label>
                <div class="cfg-card__actions">
                    <button class="terminal-button terminal-button--primary" type="submit" disabled>Save behavior</button>
                    <button class="terminal-button" type="button" data-behavior-reload>Reload behavior</button>
                </div>
                <p class="cfg-status" role="status" aria-live="polite" data-behavior-status>Reading radio behavior.</p>
            </form>
        </article>`;
        this._role = root.querySelector('[data-behavior-role]');
        this._filter = root.querySelector('[data-behavior-filter]');
        this._save = root.querySelector('[type="submit"]');
        this._reload = root.querySelector('[data-behavior-reload]');
        this._status = root.querySelector('[data-behavior-status]');
        this._role.addEventListener('change', () => this._update());
        this._filter.addEventListener('change', () => this._update());
        this._reload.addEventListener('click', () => this._load());
        root.querySelector('form').addEventListener('submit', event => {
            event.preventDefault();
            this._submit();
        });
    }

    render(config) {
        this._root.hidden = !window.PlatformContext?.isPimesh(config);
        if (this._root.hidden || this._protocol) return;
        this._protocol = config.device.radio_protocol;
        const mc = this._protocol === 'meshcore';
        this._root.querySelector('[data-behavior-label]').textContent = mc ? 'Forwarding mode' : 'Device role';
        this._root.querySelector('[data-behavior-filter-field]').hidden = mc;
        // cfg-field uses display:flex, which overrides the browser's hidden rule.
        this._root.querySelector('[data-behavior-filter-field]').style.display = mc ? 'none' : '';
        this._root.querySelector('[data-behavior-intro]').textContent = mc
            ? 'MeshCore forwarding is provided by the separate openHop backend. Each protocol keeps its own behavior settings.'
            : 'Meshtastic roles control how this radio participates in the mesh. Saving may briefly restart the radio.';
        this._load();
    }

    _options(select, values, current) {
        select.replaceChildren();
        for (const value of new Set([...values, current])) {
            const option = document.createElement('option');
            option.value = value;
            option.textContent = value.toLowerCase().replaceAll('_', ' ');
            option.disabled = !values.includes(value);
            select.appendChild(option);
        }
        select.value = current;
    }

    _show(actual) {
        if (actual.protocol !== this._protocol) throw new Error('Protocol changed. Reload this page.');
        this._actual = actual;
        this._options(this._role, actual.modes || actual.roles, actual.mode || actual.role);
        if (actual.roles) this._options(this._filter, actual.rebroadcast_modes, actual.rebroadcast_mode);
    }

    _payload() {
        return this._protocol === 'meshcore'
            ? { protocol: this._protocol, mode: this._role.value }
            : { protocol: this._protocol, role: this._role.value, rebroadcast_mode: this._filter.value };
    }

    _update() {
        const hints = {
            monitor: 'Receive traffic and send your own messages, without repeating other devices.',
            forward: 'Repeat eligible MeshCore traffic and send your own messages. Repeater advertisements and discovery remain separately configured in openHop.',
            no_tx: 'Receive only. openHop blocks all radio transmissions, including messages and acknowledgments.',
            CLIENT: 'Normal participation: send, receive, and relay eligible traffic.',
            CLIENT_MUTE: 'Send and receive your own traffic without relaying for other devices.',
            CLIENT_BASE: 'Prioritize relaying traffic from favorited nodes.',
            ROUTER: 'Prioritize relaying for other devices. Intended for well-positioned infrastructure nodes.',
            ROUTER_LATE: 'Relay after other routers have had an opportunity to forward.',
            REPEATER: 'Dedicated relay role with reduced device information. Some messaging and telemetry behavior differs from client mode.',
        };
        const invalidFilter = this._protocol === 'meshtastic' && this._filter.value === 'ALL_SKIP_DECODING' && this._role.value !== 'REPEATER';
        this._root.querySelector('[data-behavior-hint]').textContent = invalidFilter
            ? 'All skip decoding requires the Repeater role. Choose another rebroadcast filter to save this role.'
            : hints[this._role.value] || 'Current backend role is outside the supported choices.';
        const disabled = this._busy || !this._actual || !!window.meshpointReadOnly;
        this._role.disabled = disabled;
        this._filter.disabled = disabled;
        this._reload.disabled = this._busy;
        const payload = this._payload();
        const unchanged = this._actual && Object.entries(payload).every(([key, value]) => this._actual[key] === value);
        const valid = this._protocol === 'meshcore'
            ? this._actual?.modes.includes(payload.mode)
            : this._actual?.roles.includes(payload.role) && this._actual?.rebroadcast_modes.includes(payload.rebroadcast_mode)
                && (payload.rebroadcast_mode !== 'ALL_SKIP_DECODING' || payload.role === 'REPEATER');
        this._save.disabled = disabled || unchanged || !valid;
        this._root.setAttribute('aria-busy', String(this._busy));
    }

    async _load() {
        if (this._busy) return;
        this._busy = true;
        this._update();
        this._status.textContent = 'Reading radio behavior.';
        try {
            const actual = await this._api.get(`/api/pimesh/behavior?protocol=${this._protocol}`);
            if (!actual) throw new Error('Radio behavior unavailable. Wait for connection, then reload behavior.');
            this._show(actual);
            this._status.textContent = 'Current behavior confirmed by the radio.';
        } catch (error) {
            this._actual = null;
            this._status.textContent = error.message;
        } finally {
            this._busy = false;
            this._update();
        }
    }

    async _submit() {
        if (this._busy || this._save.disabled) return;
        const payload = this._payload();
        this._busy = true;
        this._update();
        this._status.textContent = 'Saving and checking radio behavior.';
        try {
            const actual = await this._api.put('/api/pimesh/behavior', payload);
            if (!actual || !Object.entries(payload).every(([key, value]) => actual[key] === value)) {
                throw new Error('Save unconfirmed. The radio may be restarting; reload behavior before retrying.');
            }
            this._show(actual);
            this._status.textContent = 'Behavior saved and confirmed by the radio.';
        } catch (error) {
            this._actual = null;
            this._status.textContent = error.message;
        } finally {
            this._busy = false;
            this._update();
        }
    }
}
window.PimeshBehaviorCard = PimeshBehaviorCard;
