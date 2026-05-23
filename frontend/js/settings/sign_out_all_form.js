/**
 * Sign-out-everywhere control for Settings → Auth.
 *
 * Single responsibility: prompt for confirmation, hit
 * ``POST /api/auth/logout_all``, then send the operator to ``/login``.
 * The server-side handler bumps ``session_version`` so every other
 * browser also drops to ``/login`` on its next request -- no need to
 * fan out client-side. A typed confirmation isn't required here
 * because the action is recoverable: a fresh login resumes work.
 */

class SignOutAllForm {
    constructor(rootEl) {
        this.root = rootEl;
        this.button = rootEl.querySelector('[data-sigout-all-btn]');
        this.status = rootEl.querySelector('[data-sigout-all-status]');
    }

    bind() {
        this.button?.addEventListener('click', () => this._invoke());
    }

    async _invoke() {
        const confirmed = window.confirm(
            'Sign out every browser session for this Meshpoint? '
            + "You'll be redirected to /login."
        );
        if (!confirmed) return;
        this.button.disabled = true;
        this._setStatus('pending', 'Invalidating all sessions…');
        try {
            const response = await fetch('/api/auth/logout_all', {
                method: 'POST',
                credentials: 'same-origin',
            });
            if (response.status === 204) {
                this._setStatus('success', 'All sessions revoked. Redirecting…');
                setTimeout(() => window.location.assign('/login'), 600);
                return;
            }
            this._setStatus('error', 'Could not revoke sessions.');
            this.button.disabled = false;
        } catch (_e) {
            this._setStatus('error', 'Network error. Try again.');
            this.button.disabled = false;
        }
    }

    _setStatus(kind, message) {
        if (!this.status) return;
        this.status.dataset.kind = kind;
        this.status.textContent = message;
    }
}

window.SignOutAllForm = SignOutAllForm;
