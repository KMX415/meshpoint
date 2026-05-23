/**
 * Viewer-role enable/disable form for Settings → Auth.
 *
 * Single responsibility: ``POST /api/auth/setup_viewer`` (with a fresh
 * password) when enabling, ``POST /api/auth/clear_viewer`` when
 * disabling. Reflects the current state via the ``viewer_enabled``
 * field on ``/api/identity`` so the operator always sees the truth.
 */

class ViewerRoleForm {
    constructor(rootEl) {
        this.root = rootEl;
        this.form = rootEl.querySelector('[data-viewer-form]');
        this.password = rootEl.querySelector('[data-viewer-password]');
        this.confirm = rootEl.querySelector('[data-viewer-confirm]');
        this.enableBtn = rootEl.querySelector('[data-viewer-enable]');
        this.disableBtn = rootEl.querySelector('[data-viewer-disable]');
        this.stateBadge = rootEl.querySelector('[data-viewer-state]');
        this.status = rootEl.querySelector('[data-viewer-status]');
        this._enabled = false;
    }

    bind() {
        this.form?.addEventListener('submit', (e) => this._enable(e));
        this.disableBtn?.addEventListener('click', () => this._disable());
    }

    setEnabled(enabled) {
        this._enabled = !!enabled;
        if (this.stateBadge) {
            this.stateBadge.textContent = enabled ? 'Enabled' : 'Disabled';
            this.stateBadge.dataset.state = enabled ? 'enabled' : 'disabled';
        }
        if (this.disableBtn) {
            this.disableBtn.disabled = !enabled;
        }
    }

    async _enable(event) {
        event.preventDefault();
        if (!this.password.value || this.password.value.length < 8) {
            this._setStatus('error', 'Viewer password must be at least 8 characters.');
            return;
        }
        if (this.password.value !== this.confirm.value) {
            this._setStatus('error', 'Passwords do not match.');
            return;
        }
        this.enableBtn.disabled = true;
        this._setStatus('pending', 'Enabling viewer role…');
        try {
            const response = await fetch('/api/auth/setup_viewer', {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ password: this.password.value }),
            });
            if (response.ok) {
                this._setStatus('success', 'Viewer role enabled.');
                this.form.reset();
                this.setEnabled(true);
                return;
            }
            this._setStatus('error', `Could not enable (HTTP ${response.status}).`);
        } catch (_e) {
            this._setStatus('error', 'Network error. Try again.');
        } finally {
            this.enableBtn.disabled = false;
        }
    }

    async _disable() {
        const confirmed = window.confirm(
            'Disable the viewer role? Existing viewer sessions remain '
            + 'valid until they expire -- use Sign out everywhere to '
            + 'kick them immediately.'
        );
        if (!confirmed) return;
        this.disableBtn.disabled = true;
        this._setStatus('pending', 'Disabling viewer role…');
        try {
            const response = await fetch('/api/auth/clear_viewer', {
                method: 'POST',
                credentials: 'same-origin',
            });
            if (response.status === 204) {
                this._setStatus('success', 'Viewer role disabled.');
                this.setEnabled(false);
                return;
            }
            this._setStatus('error', `Could not disable (HTTP ${response.status}).`);
        } catch (_e) {
            this._setStatus('error', 'Network error. Try again.');
        } finally {
            this.disableBtn.disabled = !this._enabled;
        }
    }

    _setStatus(kind, message) {
        if (!this.status) return;
        this.status.dataset.kind = kind;
        this.status.textContent = message;
    }
}

window.ViewerRoleForm = ViewerRoleForm;
