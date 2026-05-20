/**
 * Configuration → Radio — NodeInfo broadcast interval editor.
 *
 * Preset chips, numeric input (0 or 5-1440 min), and Save. Hot-reloads
 * the running broadcaster via ``PUT /api/config/nodeinfo``.
 */

class NodeInfoConfigCard {
    static PRESETS = [
        { minutes: 0, label: 'Off', off: true },
        { minutes: 5, label: '5m' },
        { minutes: 30, label: '30m' },
        { minutes: 60, label: '1h' },
        { minutes: 180, label: '3h' },
        { minutes: 360, label: '6h' },
        { minutes: 720, label: '12h' },
        { minutes: 1440, label: '24h' },
    ];

    constructor(api) {
        this._api = api;
        this._root = null;
        this._saved = { interval_minutes: 0 };
        this._draft = { interval_minutes: 0 };
    }

    mount(root) {
        this._root = root;
        this._root.innerHTML = `
            <article class="cfg-card" id="cfg-nodeinfo-interval">
                <header class="cfg-card__head">
                    <h3 class="cfg-card__title">NodeInfo broadcast interval</h3>
                    <p class="cfg-card__hint">
                        How often this Meshpoint advertises its identity on the mesh.
                        0 pauses periodic broadcasts (DMs and Send Now still work).
                        Saved intervals take effect immediately without a restart.
                    </p>
                </header>
                <form class="cfg-form" data-ni-form>
                    <div class="cfg-field">
                        <span class="cfg-field__label">Preset</span>
                        <div class="cfg-chip-row" data-ni-chips></div>
                    </div>
                    <label class="cfg-field cfg-field--narrow">
                        <span class="cfg-field__label">Custom (minutes)</span>
                        <input class="cfg-field__input" type="number"
                               min="0" max="1440" step="1" data-ni-input>
                    </label>
                    <p class="cfg-card__hint">
                        Use 0 to pause, or 5-1440 for an active cadence.
                    </p>
                    <div class="cfg-card__actions">
                        <button class="terminal-button terminal-button--primary"
                                type="submit" data-ni-save>Save NodeInfo</button>
                    </div>
                    <p class="cfg-status" data-ni-status aria-live="polite"></p>
                </form>
            </article>
        `;
        this._chipsEl = this._root.querySelector('[data-ni-chips]');
        this._inputEl = this._root.querySelector('[data-ni-input]');
        this._saveBtn = this._root.querySelector('[data-ni-save]');
        this._statusEl = this._root.querySelector('[data-ni-status]');
        this._form = this._root.querySelector('[data-ni-form]');
        this._renderChips();
        this._wire();
    }

    render(config) {
        const ni = (config && config.nodeinfo) || {};
        this._saved.interval_minutes = ni.interval_minutes || 0;
        this._draft.interval_minutes = this._saved.interval_minutes;
        this._inputEl.value = String(this._draft.interval_minutes);
        this._setActiveChip(this._draft.interval_minutes);
        this._renderPendingCue();
        this._setStatus('', '');
    }

    _renderChips() {
        this._chipsEl.innerHTML = NodeInfoConfigCard.PRESETS.map((p) => {
            const offCls = p.off ? ' cfg-chip--off' : '';
            return `<button type="button" class="cfg-chip${offCls}"
                    data-minutes="${p.minutes}">${this._esc(p.label)}</button>`;
        }).join('');
        this._chipsEl.querySelectorAll('[data-minutes]').forEach((chip) => {
            chip.addEventListener('click', (e) => {
                e.preventDefault();
                const minutes = parseInt(chip.dataset.minutes, 10);
                this._inputEl.value = String(minutes);
                this._draft.interval_minutes = minutes;
                this._setActiveChip(minutes);
                this._renderPendingCue();
            });
        });
    }

    _wire() {
        this._form.addEventListener('submit', (e) => this._onSubmit(e));
        this._inputEl.addEventListener('input', () => {
            const minutes = parseInt(this._inputEl.value, 10);
            if (isNaN(minutes)) return;
            this._setActiveChip(minutes);
            if (minutes === 0 || (minutes >= 5 && minutes <= 1440)) {
                this._draft.interval_minutes = minutes;
            }
            this._renderPendingCue();
        });
    }

    async _onSubmit(event) {
        event.preventDefault();
        const minutes = this._draft.interval_minutes;
        if (isNaN(minutes) || (minutes !== 0 && (minutes < 5 || minutes > 1440))) {
            this._setStatus('error', 'Interval must be 0 or 5-1440 minutes.');
            return;
        }
        this._setStatus('pending', 'Saving…');
        const result = await this._api.put('/api/config/nodeinfo', {
            interval_minutes: minutes,
        });
        if (!result) {
            this._setStatus('error', 'Save failed.');
            return;
        }
        this._setStatus('success', minutes === 0
            ? 'Broadcasts paused.'
            : 'Interval saved.');
        this._api.toast(minutes === 0
            ? 'NodeInfo broadcasts paused'
            : 'NodeInfo interval saved');
        await this._api.refresh();
    }

    _setActiveChip(minutes) {
        this._chipsEl.querySelectorAll('[data-minutes]').forEach((chip) => {
            const m = parseInt(chip.dataset.minutes, 10);
            chip.classList.toggle('cfg-chip--selected', m === minutes);
        });
    }

    _isPending() {
        return this._draft.interval_minutes !== this._saved.interval_minutes;
    }

    _renderPendingCue() {
        if (this._saveBtn) {
            this._saveBtn.classList.toggle('cfg-btn--has-pending', this._isPending());
        }
    }

    _setStatus(kind, message) {
        if (!this._statusEl) return;
        this._statusEl.dataset.kind = kind || '';
        this._statusEl.textContent = message;
    }

    _esc(str) {
        return this._api.escape ? this._api.escape(String(str)) : String(str);
    }
}

window.NodeInfoConfigCard = NodeInfoConfigCard;
