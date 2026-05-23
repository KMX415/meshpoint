/**
 * Session lifetime configuration form (Settings → Auth).
 *
 * Single responsibility: read the current ``session_lifetime_minutes``
 * from ``GET /api/config/auth_settings`` and ``PUT`` new values to
 * ``/api/config/auth_session_lifetime``. Surfaces preset chips for
 * the common operator choices (1h / 8h / 1 day / 7 days / 30 days)
 * and a custom-minutes input that the chips and the manual entry
 * stay in sync with.
 *
 * Range is enforced both client-side (so the operator can't even
 * submit nonsense) and server-side (the route uses Pydantic ``ge`` /
 * ``le`` for the canonical bounds: 5 minutes -> 30 days).
 */

class SessionLifetimeForm {
    constructor(rootEl) {
        this.root = rootEl;
        this.form = rootEl.querySelector('[data-session-lifetime-form]');
        this.input = rootEl.querySelector('[data-session-lifetime-input]');
        this.preview = rootEl.querySelector('[data-session-lifetime-preview]');
        this.submit = rootEl.querySelector('[data-session-lifetime-submit]');
        this.status = rootEl.querySelector('[data-session-lifetime-status]');
        this.presetButtons = Array.from(
            rootEl.querySelectorAll('[data-session-lifetime-preset]')
        );
        this._minMinutes = 5;
        this._maxMinutes = 30 * 24 * 60;
    }

    bind() {
        if (!this.form) return;
        this.form.addEventListener('submit', (e) => this._submit(e));
        this.input?.addEventListener('input', () => this._onInputChange());
        this.presetButtons.forEach((btn) => {
            btn.addEventListener('click', () => this._onPresetClick(btn));
        });
    }

    setValues({ current, min, max } = {}) {
        if (Number.isFinite(min)) this._minMinutes = min;
        if (Number.isFinite(max)) this._maxMinutes = max;
        if (Number.isFinite(current) && this.input) {
            this.input.value = String(current);
        }
        if (this.input) {
            this.input.min = String(this._minMinutes);
            this.input.max = String(this._maxMinutes);
        }
        this._refreshPreview();
        this._highlightActivePreset();
    }

    _onPresetClick(btn) {
        const minutes = parseInt(btn.dataset.sessionLifetimePreset, 10);
        if (!Number.isFinite(minutes)) return;
        if (this.input) {
            this.input.value = String(minutes);
        }
        this._refreshPreview();
        this._highlightActivePreset();
    }

    _onInputChange() {
        this._refreshPreview();
        this._highlightActivePreset();
    }

    async _submit(event) {
        event.preventDefault();
        const minutes = parseInt(this.input?.value, 10);
        if (!Number.isInteger(minutes)
            || minutes < this._minMinutes
            || minutes > this._maxMinutes) {
            const range = `${this._minMinutes}–${this._maxMinutes}`;
            this._setStatus('error', `Lifetime must be ${range} minutes.`);
            return;
        }
        this.submit.disabled = true;
        this._setStatus('pending', 'Saving…');
        try {
            const response = await fetch('/api/config/auth_session_lifetime', {
                method: 'PUT',
                credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_lifetime_minutes: minutes }),
            });
            if (response.ok) {
                this._setStatus(
                    'success',
                    `Saved. New logins will stay valid for ${this._humanize(minutes)}.`,
                );
                return;
            }
            this._setStatus('error', `Could not update (HTTP ${response.status}).`);
        } catch (_e) {
            this._setStatus('error', 'Network error. Try again.');
        } finally {
            this.submit.disabled = false;
        }
    }

    _refreshPreview() {
        if (!this.preview) return;
        const minutes = parseInt(this.input?.value, 10);
        if (!Number.isFinite(minutes)) {
            this.preview.textContent = '';
            return;
        }
        this.preview.textContent = this._humanize(minutes);
    }

    _highlightActivePreset() {
        const minutes = parseInt(this.input?.value, 10);
        this.presetButtons.forEach((btn) => {
            const presetMinutes = parseInt(btn.dataset.sessionLifetimePreset, 10);
            const active = presetMinutes === minutes;
            btn.classList.toggle('auth-preset--active', active);
            btn.setAttribute('aria-pressed', active ? 'true' : 'false');
        });
    }

    _humanize(minutes) {
        if (!Number.isFinite(minutes) || minutes <= 0) return '';
        if (minutes < 60) return `${minutes} minute${minutes === 1 ? '' : 's'}`;
        if (minutes < 24 * 60) {
            const hours = +(minutes / 60).toFixed(2);
            return `${hours} hour${hours === 1 ? '' : 's'}`;
        }
        const days = +(minutes / (24 * 60)).toFixed(2);
        return `${days} day${days === 1 ? '' : 's'}`;
    }

    _setStatus(kind, message) {
        if (!this.status) return;
        this.status.dataset.kind = kind;
        this.status.textContent = message;
    }
}

window.SessionLifetimeForm = SessionLifetimeForm;
