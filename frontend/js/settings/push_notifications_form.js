/**
 * Settings → System: browser push notification preferences.
 */

class PushNotificationsForm {
    constructor(rootEl) {
        this.root = rootEl;
        this._statusEl = rootEl.querySelector('[data-push-notifications-status]');
        this._masterToggle = rootEl.querySelector('[data-push-enabled]');
        this._kindInputs = Array.from(rootEl.querySelectorAll('[data-push-kind]'));
        this._focusToggle = rootEl.querySelector('[data-push-suppress-focused]');
        this._enableBtn = rootEl.querySelector('[data-push-enable-btn]');
        this._bind();
        this._syncFromStorage();
    }

    _bind() {
        if (this._enableBtn) {
            this._enableBtn.addEventListener('click', () => this._onEnableClick());
        }
        if (this._masterToggle) {
            this._masterToggle.addEventListener('change', () => this._onMasterChange());
        }
        this._kindInputs.forEach((el) => {
            el.addEventListener('change', () => this._saveKinds());
        });
        if (this._focusToggle) {
            this._focusToggle.addEventListener('change', () => this._saveKinds());
        }
    }

    _syncFromStorage() {
        const prefs = window.pushNotifications.getPrefs();
        if (this._masterToggle) {
            this._masterToggle.checked = prefs.enabled;
        }
        this._kindInputs.forEach((el) => {
            const key = el.dataset.pushKind;
            el.checked = prefs[key] !== false;
            el.disabled = !prefs.enabled;
        });
        if (this._focusToggle) {
            this._focusToggle.checked = prefs.suppress_when_focused !== false;
            this._focusToggle.disabled = !prefs.enabled;
        }
        this._updatePermissionHint();
    }

    async _onEnableClick() {
        const perm = await window.pushNotifications.enable();
        if (perm === 'granted') {
            this._setStatus('success', 'Notifications enabled for this browser.');
        } else if (perm === 'denied') {
            this._setStatus('error', 'Permission denied. Allow notifications in browser settings.');
        } else if (perm === 'unsupported') {
            this._setStatus('error', 'This browser does not support notifications.');
        } else {
            this._setStatus('error', 'Permission not granted.');
        }
        this._syncFromStorage();
    }

    _onMasterChange() {
        const enabled = !!(this._masterToggle && this._masterToggle.checked);
        if (enabled) {
            this._onEnableClick();
            return;
        }
        window.pushNotifications.disable();
        this._setStatus('success', 'Notifications disabled.');
        this._syncFromStorage();
    }

    _saveKinds() {
        const prefs = window.pushNotifications.getPrefs();
        const next = { ...prefs };
        this._kindInputs.forEach((el) => {
            next[el.dataset.pushKind] = el.checked;
        });
        if (this._focusToggle) {
            next.suppress_when_focused = this._focusToggle.checked;
        }
        window.pushNotifications.savePrefs(next);
        this._setStatus('success', 'Alert preferences saved.');
    }

    _updatePermissionHint() {
        const hint = this.root.querySelector('[data-push-permission-hint]');
        if (!hint) return;
        const perm = window.pushNotifications.permissionState();
        if (perm === 'unsupported') {
            hint.textContent = 'Notifications are not supported in this browser.';
        } else if (perm === 'denied') {
            hint.textContent = 'Blocked — reset site permissions to enable alerts.';
        } else if (perm === 'granted') {
            hint.textContent = 'Permission granted.';
        } else {
            hint.textContent = 'Click Enable to request browser permission.';
        }
    }

    _setStatus(kind, message) {
        if (!this._statusEl) return;
        this._statusEl.dataset.kind = kind;
        this._statusEl.textContent = message;
    }
}

window.PushNotificationsForm = PushNotificationsForm;
