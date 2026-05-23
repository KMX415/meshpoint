/**
 * Failed-login lockout configuration form for Settings → Auth.
 *
 * Single responsibility: read the current values from
 * ``/api/identity`` (or the bootstrap snapshot) and ``PUT`` new
 * values to ``/api/config/auth_lockout``. Surfaces server-side
 * validation reasons (out-of-range cooldown, attempts) verbatim.
 */

class LockoutConfigForm {
    constructor(rootEl) {
        this.root = rootEl;
        this.form = rootEl.querySelector('[data-lockout-form]');
        this.attemptsInput = rootEl.querySelector('[data-lockout-attempts]');
        this.cooldownInput = rootEl.querySelector('[data-lockout-cooldown]');
        this.submit = rootEl.querySelector('[data-lockout-submit]');
        this.status = rootEl.querySelector('[data-lockout-status]');
    }

    bind() {
        if (!this.form) return;
        this.form.addEventListener('submit', (e) => this._submit(e));
    }

    setValues(attempts, cooldown) {
        if (this.attemptsInput && Number.isFinite(attempts)) {
            this.attemptsInput.value = String(attempts);
        }
        if (this.cooldownInput && Number.isFinite(cooldown)) {
            this.cooldownInput.value = String(cooldown);
        }
    }

    async _submit(event) {
        event.preventDefault();
        const attempts = parseInt(this.attemptsInput.value, 10);
        const cooldown = parseInt(this.cooldownInput.value, 10);
        if (!Number.isInteger(attempts) || attempts < 1 || attempts > 100) {
            this._setStatus('error', 'Attempts must be between 1 and 100.');
            return;
        }
        if (!Number.isInteger(cooldown) || cooldown < 1 || cooldown > 1440) {
            this._setStatus(
                'error', 'Cooldown must be between 1 and 1440 minutes.'
            );
            return;
        }
        this.submit.disabled = true;
        this._setStatus('pending', 'Saving…');
        try {
            const response = await fetch('/api/config/auth_lockout', {
                method: 'PUT',
                credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    lockout_attempts: attempts,
                    lockout_cooldown_minutes: cooldown,
                }),
            });
            if (response.ok) {
                this._setStatus('success', 'Lockout settings updated.');
                return;
            }
            this._setStatus('error', `Could not update (HTTP ${response.status}).`);
        } catch (_e) {
            this._setStatus('error', 'Network error. Try again.');
        } finally {
            this.submit.disabled = false;
        }
    }

    _setStatus(kind, message) {
        if (!this.status) return;
        this.status.dataset.kind = kind;
        this.status.textContent = message;
    }
}

window.LockoutConfigForm = LockoutConfigForm;
