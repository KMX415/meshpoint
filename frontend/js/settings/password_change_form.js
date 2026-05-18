/**
 * Password change form controller for Settings → Auth.
 *
 * Single responsibility: bind one form to ``POST /api/auth/change_password``.
 * Validates locally (matches confirmation, length floor) before
 * round-tripping; surfaces server-side rejection codes verbatim so the
 * user knows whether their current password was wrong vs the new one
 * was too short. On success, the server reseats the session cookie
 * via ``Set-Cookie`` and we render a tasteful confirmation -- no
 * redirect, since the caller is staying put.
 */

class PasswordChangeForm {
    constructor(rootEl) {
        this.root = rootEl;
        this.form = rootEl.querySelector('[data-pwc-form]');
        this.curr = rootEl.querySelector('[data-pwc-current]');
        this.next = rootEl.querySelector('[data-pwc-new]');
        this.confirm = rootEl.querySelector('[data-pwc-confirm]');
        this.submit = rootEl.querySelector('[data-pwc-submit]');
        this.status = rootEl.querySelector('[data-pwc-status]');
        this.strength = rootEl.querySelector('[data-pwc-strength]');
    }

    bind() {
        if (!this.form) return;
        this.form.addEventListener('submit', (e) => this._submit(e));
        this.next?.addEventListener('input', () => this._renderStrength());
    }

    _renderStrength() {
        const value = this.next.value || '';
        const score = Math.min(5, Math.floor(value.length / 4));
        this.strength?.setAttribute('data-strength', String(score));
        this.strength?.setAttribute(
            'aria-valuenow', String(score)
        );
    }

    _setStatus(kind, message) {
        if (!this.status) return;
        this.status.dataset.kind = kind;
        this.status.textContent = message;
    }

    async _submit(event) {
        event.preventDefault();
        if (!this.next.value || this.next.value.length < 8) {
            this._setStatus('error', 'New password must be at least 8 characters.');
            return;
        }
        if (this.next.value !== this.confirm.value) {
            this._setStatus('error', 'New password and confirmation do not match.');
            return;
        }
        this.submit.disabled = true;
        this._setStatus('pending', 'Updating password…');
        try {
            const response = await fetch('/api/auth/change_password', {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    current_password: this.curr.value,
                    new_password: this.next.value,
                }),
            });
            if (response.ok) {
                this._setStatus(
                    'success',
                    'Password updated. Other browser sessions have been signed out.'
                );
                this.form.reset();
                this._renderStrength();
                return;
            }
            const detail = await this._readDetail(response);
            this._setStatus('error', this._humanReason(detail, response.status));
        } catch (_e) {
            this._setStatus('error', 'Network error. Try again.');
        } finally {
            this.submit.disabled = false;
        }
    }

    async _readDetail(response) {
        try {
            const body = await response.json();
            return body?.detail || '';
        } catch (_) {
            return '';
        }
    }

    _humanReason(detail, status) {
        if (detail === 'invalid_current_password') {
            return 'Current password is incorrect.';
        }
        if (detail === 'password_too_short') {
            return 'New password is too short (8 chars minimum).';
        }
        if (detail === 'password_too_long') {
            return 'New password is too long.';
        }
        if (status === 401) return 'Authentication required.';
        return 'Could not update password. Try again.';
    }
}

window.PasswordChangeForm = PasswordChangeForm;
