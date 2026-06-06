/**
 * Configuration → Advanced — relay filter controls.
 *
 * Blocklist, priority list, and dedup TTL via PUT /api/config/relay.
 * Filter changes hot-reload without a full service restart.
 */

class RelayFiltersCard {
    static NODE_ID_RE = /^[0-9a-f]{8}$/i;

    constructor(api) {
        this._api = api;
        this._root = null;
        this._blocklist = [];
        this._priority = [];
    }

    mount(root) {
        this._root = root;
        this._root.innerHTML = `
            <article class="cfg-card">
                <header class="cfg-card__head">
                    <h3 class="cfg-card__title">Relay filters</h3>
                    <p class="cfg-card__hint">
                        Blocklist affects <strong>relay only</strong> — packets still appear in the live feed.
                        Priority nodes bypass the burst gate (not the per-minute cap). Dedup default is 300 s.
                    </p>
                </header>
                <form class="cfg-form" data-relay-filters-form>
                    <div class="cfg-field">
                        <span class="cfg-field__label">Blocklist</span>
                        <div class="cfg-id-list" data-blocklist></div>
                        <div class="cfg-id-add">
                            <input class="cfg-field__input" type="text"
                                   placeholder="a3f2b1c0" maxlength="9"
                                   data-blocklist-input>
                            <button type="button" class="terminal-button"
                                    data-blocklist-add>Add</button>
                        </div>
                    </div>
                    <div class="cfg-field">
                        <span class="cfg-field__label">Priority list</span>
                        <div class="cfg-id-list" data-priority-list></div>
                        <div class="cfg-id-add">
                            <input class="cfg-field__input" type="text"
                                   placeholder="deadbeef" maxlength="9"
                                   data-priority-input>
                            <button type="button" class="terminal-button"
                                    data-priority-add>Add</button>
                        </div>
                    </div>
                    <label class="cfg-field">
                        <span class="cfg-field__label">Dedup TTL (seconds)</span>
                        <input class="cfg-field__input" type="number" min="5" max="3600"
                               step="1" data-dedup-ttl>
                        <span class="cfg-field__hint">How long a packet ID is remembered (default 300).</span>
                    </label>
                    <div class="cfg-card__actions">
                        <button class="terminal-button terminal-button--primary"
                                type="submit">Save relay filters</button>
                    </div>
                    <p class="cfg-status" data-relay-filters-status aria-live="polite"></p>
                </form>
            </article>
        `;

        this._blocklistEl = this._root.querySelector('[data-blocklist]');
        this._priorityEl = this._root.querySelector('[data-priority-list]');
        this._form = this._root.querySelector('[data-relay-filters-form]');
        this._statusEl = this._root.querySelector('[data-relay-filters-status]');

        this._root.querySelector('[data-blocklist-add]').addEventListener('click', () => {
            this._addId('blocklist');
        });
        this._root.querySelector('[data-priority-add]').addEventListener('click', () => {
            this._addId('priority');
        });
        this._form.addEventListener('submit', (e) => this._onSubmit(e));
    }

    render(config) {
        const relay = config.relay || {};
        this._blocklist = (relay.blocklist || []).map((id) => this._normalizeId(id));
        this._priority = (relay.priority_list || []).map((id) => this._normalizeId(id));
        this._paintLists();
        const ttl = relay.dedup_ttl_seconds;
        const ttlEl = this._root.querySelector('[data-dedup-ttl]');
        if (ttlEl) ttlEl.value = ttl != null ? ttl : 300;
    }

    _normalizeId(raw) {
        return String(raw || '').trim().toLowerCase().replace(/^!/, '');
    }

    _addId(which) {
        const input = this._root.querySelector(
            which === 'blocklist' ? '[data-blocklist-input]' : '[data-priority-input]',
        );
        const id = this._normalizeId(input.value);
        if (!RelayFiltersCard.NODE_ID_RE.test(id)) {
            this._setStatus('error', 'Node ID must be 8 hex characters (no ! prefix).');
            return;
        }
        const list = which === 'blocklist' ? this._blocklist : this._priority;
        if (!list.includes(id)) list.push(id);
        input.value = '';
        this._paintLists();
    }

    _removeId(which, id) {
        if (which === 'blocklist') {
            this._blocklist = this._blocklist.filter((x) => x !== id);
        } else {
            this._priority = this._priority.filter((x) => x !== id);
        }
        this._paintLists();
    }

    _paintLists() {
        this._blocklistEl.innerHTML = this._listHtml('blocklist', this._blocklist);
        this._priorityEl.innerHTML = this._listHtml('priority', this._priority);
        this._blocklistEl.querySelectorAll('[data-remove-id]').forEach((btn) => {
            btn.addEventListener('click', () => {
                this._removeId(btn.dataset.list, btn.dataset.id);
            });
        });
        this._priorityEl.querySelectorAll('[data-remove-id]').forEach((btn) => {
            btn.addEventListener('click', () => {
                this._removeId(btn.dataset.list, btn.dataset.id);
            });
        });
    }

    _listHtml(which, ids) {
        if (!ids.length) {
            return '<p class="cfg-id-empty">None</p>';
        }
        return ids.map((id) => `
            <div class="cfg-id-row">
                <code class="cfg-id-chip">!${this._api.escape(id)}</code>
                <button type="button" class="cfg-id-remove" data-remove-id
                        data-list="${which}" data-id="${this._api.escape(id)}"
                        aria-label="Remove ${id}">×</button>
            </div>
        `).join('');
    }

    async _onSubmit(event) {
        event.preventDefault();
        const ttl = Number(this._root.querySelector('[data-dedup-ttl]').value);
        if (!Number.isFinite(ttl) || ttl < 5 || ttl > 3600) {
            this._setStatus('error', 'Dedup TTL must be between 5 and 3600 seconds.');
            return;
        }
        this._setStatus('pending', 'Saving…');
        const result = await this._api.put('/api/config/relay', {
            blocklist: this._blocklist,
            priority_list: this._priority,
            dedup_ttl_seconds: ttl,
        });
        if (!result) {
            this._setStatus('error', 'Save failed.');
            return;
        }
        this._setStatus('success', 'Saved.');
        if (result.restart_required) {
            this._api.signalRestart('Relay settings updated.');
        } else {
            this._api.toast('Relay filters applied (no restart required).');
        }
        this._api.refresh();
    }

    _setStatus(kind, message) {
        if (!this._statusEl) return;
        this._statusEl.dataset.kind = kind;
        this._statusEl.textContent = message;
    }
}

window.RelayFiltersCard = RelayFiltersCard;
