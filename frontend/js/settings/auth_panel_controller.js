/**
 * Settings → Auth panel orchestrator.
 *
 * Single responsibility: own the lifecycle of the four sub-forms
 * (password change, sign-out everywhere, viewer role, lockout) and
 * keep them in sync with ``/api/identity``. The controller does not
 * render any HTML itself -- it expects the panel structure to be
 * present in ``index.html`` and binds behaviour to the data
 * attributes those nodes carry.
 *
 * Lifecycle:
 *   const ctrl = new AuthPanelController(rootEl);
 *   ctrl.bind();          // wires form submissions
 *   await ctrl.refresh(); // pulls live config + viewer state
 *
 * The orchestrator only cares about coordination -- each sub-form
 * owns its own DOM and its own request shape.
 */

class AuthPanelController {
    constructor(rootEl) {
        this.root = rootEl;
        this.passwordChange = new window.PasswordChangeForm(
            rootEl.querySelector('[data-pwc-root]')
        );
        this.signOutAll = new window.SignOutAllForm(
            rootEl.querySelector('[data-sigout-all-root]')
        );
        this.viewerRole = new window.ViewerRoleForm(
            rootEl.querySelector('[data-viewer-root]')
        );
        this.lockout = new window.LockoutConfigForm(
            rootEl.querySelector('[data-lockout-root]')
        );
        this.sessionLifetime = new window.SessionLifetimeForm(
            rootEl.querySelector('[data-session-lifetime-root]')
        );
    }

    bind() {
        this.passwordChange.bind();
        this.signOutAll.bind();
        this.viewerRole.bind();
        this.lockout.bind();
        this.sessionLifetime.bind();
    }

    async refresh() {
        const [identity, settings] = await Promise.all([
            this._fetchIdentity(),
            this._fetchAuthSettings(),
        ]);
        if (identity) {
            this.viewerRole.setEnabled(!!identity.viewer_enabled);
        }
        if (settings) {
            this.lockout.setValues(
                settings.lockout_attempts,
                settings.lockout_cooldown_minutes,
            );
            this.sessionLifetime.setValues({
                current: settings.session_lifetime_minutes,
                min: settings.session_lifetime_min_minutes,
                max: settings.session_lifetime_max_minutes,
            });
        }
    }

    async _fetchIdentity() {
        try {
            const response = await fetch('/api/identity', {
                credentials: 'same-origin',
                cache: 'no-store',
            });
            if (!response.ok) return null;
            return await response.json();
        } catch (_e) {
            return null;
        }
    }

    async _fetchAuthSettings() {
        try {
            const response = await fetch('/api/config/auth_settings', {
                credentials: 'same-origin',
                cache: 'no-store',
            });
            if (!response.ok) return null;
            return await response.json();
        } catch (_e) {
            return null;
        }
    }
}

window.AuthPanelController = AuthPanelController;
