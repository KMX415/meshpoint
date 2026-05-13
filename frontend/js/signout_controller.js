/**
 * Sign-out button controller for the dashboard topbar.
 *
 * Single responsibility: POST /api/auth/logout, then send the
 * browser to /login. Survives a network failure by redirecting
 * anyway -- the global 401 interceptor will catch any subsequent
 * authenticated call if the cookie somehow lingered.
 */

class SignOutController {
    constructor(buttonId) {
        this.button = document.getElementById(buttonId);
    }

    bind() {
        if (!this.button) return;
        this.button.addEventListener('click', () => this._signOut());
    }

    async _signOut() {
        this.button.disabled = true;
        try {
            await fetch('/api/auth/logout', {
                method: 'POST',
                credentials: 'same-origin',
            });
        } catch (_) {
            /* network-level failure -- still send the user to /login,
               the cookie may already be invalid server-side */
        } finally {
            window.location.assign('/login');
        }
    }
}

window.SignOutController = SignOutController;
