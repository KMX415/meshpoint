/**
 * Live auth controller for /setup and /login pages.
 *
 * Mode is read from <body data-auth-mode>. The classes below are
 * single-responsibility: IdentityLoader populates the identity strip
 * from the public /api/identity probe, AuthForm submits credentials
 * and translates server reasons into messages. The page picks the
 * right form variant via the AuthFormFactory.
 *
 * The radar visual ships sweep + center pulse only in v0.7.3. The
 * design intent is to paint cyan blips from real concentrator RX
 * events, which requires a deliberately-public, scrubbed event feed
 * (no node ids, no payloads, rate-limited). That public feed is
 * scoped to v0.7.4 so the pre-auth surface gets its own privacy
 * review rather than being bolted onto the auth release.
 */

class IdentityLoader {
    constructor({ nameId, versionId, mode, redirectOnMismatch = true }) {
        this.nameEl = document.getElementById(nameId);
        this.versionEl = document.getElementById(versionId);
        this.mode = mode;
        this.redirectOnMismatch = redirectOnMismatch;
    }

    async load() {
        try {
            const res = await fetch('/api/identity', { credentials: 'same-origin' });
            if (!res.ok) return;
            const data = await res.json();
            this._render(data);
            this._enforceMode(data);
        } catch (_) {
            /* identity probe is decorative -- silent failure is fine */
        }
    }

    _render(data) {
        if (this.nameEl && data.device_name) this.nameEl.textContent = data.device_name;
        if (this.versionEl && data.firmware_version) {
            this.versionEl.textContent = `v${data.firmware_version}`;
        }
    }

    _enforceMode(data) {
        if (!this.redirectOnMismatch) return;
        if (this.mode === 'login' && data.setup_required) {
            window.location.replace('/setup');
            return;
        }
        if (this.mode === 'setup' && !data.setup_required) {
            window.location.replace('/login');
        }
    }
}

function copyForReason(reason) {
    switch (reason) {
        case 'password_too_short':    return 'Must be at least 8 characters.';
        case 'password_too_long':     return 'That entry is too long.';
        case 'invalid_password':      return 'That entry is not valid.';
        case 'already_set':           return 'Setup is already complete. Redirecting to sign in...';
        case 'setup_required':        return 'No admin is configured yet. Redirecting to setup...';
        case 'invalid_credentials':   return 'Wrong credentials.';
        case 'locked_out':            return 'Too many attempts. Try again shortly.';
        case 'network_error':         return 'Network error. Check the device connection.';
        default:                      return 'Something went wrong. Try again.';
    }
}

class AuthForm {
    constructor() {
        this.form = document.getElementById('auth-form');
        this.passwordInput = document.getElementById('password-input');
        this.errorEl = document.getElementById('error-msg');
        this.submitBtn = document.getElementById('submit-btn');
        this._lockoutTimer = null;
    }

    bindCommon() {
        this.form.addEventListener('submit', (e) => {
            e.preventDefault();
            this._submit();
        });
        this.passwordInput.addEventListener('input', () => this._clearError());
    }

    _setLoading(on) {
        this.submitBtn.classList.toggle('auth-button--loading', on);
        this.submitBtn.disabled = on;
    }

    _showError(reason, retryAfterSeconds) {
        if (this._lockoutTimer) {
            clearInterval(this._lockoutTimer);
            this._lockoutTimer = null;
        }
        if (reason === 'locked_out' && retryAfterSeconds) {
            this._startLockoutCountdown(retryAfterSeconds);
        } else {
            this.errorEl.textContent = copyForReason(reason);
        }
        this.passwordInput.classList.add('auth-input--error');
        setTimeout(() => this.passwordInput.classList.remove('auth-input--error'), 400);
    }

    _startLockoutCountdown(seconds) {
        this.submitBtn.disabled = true;
        let remaining = seconds;
        const render = () => {
            const m = Math.floor(remaining / 60);
            const s = String(remaining % 60).padStart(2, '0');
            this.errorEl.textContent = `Locked. Try again in ${m}:${s}`;
        };
        render();
        this._lockoutTimer = setInterval(() => {
            remaining -= 1;
            if (remaining <= 0) {
                clearInterval(this._lockoutTimer);
                this._lockoutTimer = null;
                this.errorEl.textContent = '';
                this.submitBtn.disabled = false;
            } else {
                render();
            }
        }, 1000);
    }

    _clearError() {
        if (this._lockoutTimer) return;
        this.errorEl.textContent = '';
        this.passwordInput.classList.remove('auth-input--error');
    }

    async _postJson(url, body) {
        try {
            const res = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
                credentials: 'same-origin',
            });
            const retryAfter = res.headers.get('Retry-After');
            const text = await res.text();
            const payload = text ? JSON.parse(text) : {};
            return {
                ok: res.ok,
                status: res.status,
                detail: payload.detail || 'unknown',
                retryAfter: retryAfter ? parseInt(retryAfter, 10) : null,
            };
        } catch (_) {
            return { ok: false, status: 0, detail: 'network_error', retryAfter: null };
        }
    }

    _redirectAfterAuth() {
        window.location.replace(_safeNextPath(window.location.search));
    }
}

/**
 * Strict allowlist for the post-auth redirect target.
 *
 * Accepts only paths that are unambiguously same-origin: must start
 * with `/`, must not start with `//` or `/\\` (protocol-relative or
 * backslash injection), must not contain a scheme separator, and
 * must match a conservative character class. Anything else falls
 * back to `/` so a hostile `?next=` cannot bounce the freshly
 * authenticated session off the device.
 */
function _safeNextPath(search) {
    const params = new URLSearchParams(search);
    const next = params.get('next');
    if (typeof next !== 'string' || next.length === 0 || next.length > 512) return '/';
    if (next[0] !== '/') return '/';
    if (next.startsWith('//') || next.startsWith('/\\')) return '/';
    if (next.includes('://')) return '/';
    if (!/^[A-Za-z0-9._~/?=&%#-]+$/.test(next)) return '/';
    return next;
}

class SetupForm extends AuthForm {
    constructor() {
        super();
        this.confirmInput = document.getElementById('confirm-input');
        this.lengthRule = document.querySelector('[data-rule="length"]');
        this.matchRule = document.querySelector('[data-rule="match"]');
    }

    bind() {
        this.bindCommon();
        const apply = () => this._applyRules();
        this.passwordInput.addEventListener('input', apply);
        this.confirmInput.addEventListener('input', apply);
        apply();
    }

    _applyRules() {
        const pw = this.passwordInput.value;
        const cf = this.confirmInput.value;
        const lengthOk = pw.length >= 8;
        const matchOk = pw.length > 0 && pw === cf;
        this.lengthRule.classList.toggle('auth-rule--ok', lengthOk);
        this.matchRule.classList.toggle('auth-rule--ok', matchOk);
    }

    async _submit() {
        const pw = this.passwordInput.value;
        const cf = this.confirmInput.value;
        if (pw.length < 8) return this._showError('password_too_short');
        if (pw !== cf)     return this._showError('invalid_password');
        this._setLoading(true);
        const result = await this._postJson('/api/auth/setup', { password: pw });
        this._setLoading(false);
        if (result.ok) {
            this._redirectAfterAuth();
            return;
        }
        if (result.detail === 'already_set') {
            this._showError('already_set');
            setTimeout(() => window.location.replace('/login'), 1200);
            return;
        }
        this._showError(result.detail, result.retryAfter);
    }
}

class LoginForm extends AuthForm {
    constructor() {
        super();
        this.usernameInput = document.getElementById('username-input');
    }

    bind() {
        this.bindCommon();
    }

    async _submit() {
        const username = (this.usernameInput.value || '').trim();
        const password = this.passwordInput.value;
        if (!username || !password) return this._showError('invalid_credentials');
        this._setLoading(true);
        const result = await this._postJson('/api/auth/login', { username, password });
        this._setLoading(false);
        if (result.ok) {
            this._redirectAfterAuth();
            return;
        }
        if (result.detail === 'setup_required') {
            this._showError('setup_required');
            setTimeout(() => window.location.replace('/setup'), 1200);
            return;
        }
        this._showError(result.detail, result.retryAfter);
    }
}

class AuthFormFactory {
    static build(mode) {
        if (mode === 'setup') return new SetupForm();
        return new LoginForm();
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const mode = document.body.dataset.authMode || 'login';
    new IdentityLoader({
        nameId: 'identity-name',
        versionId: 'identity-version',
        mode,
    }).load();

    AuthFormFactory.build(mode).bind();
});
