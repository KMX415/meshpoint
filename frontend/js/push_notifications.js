/**
 * LAN browser push notifications for mesh alerts (PR 04).
 *
 * Preferences live in localStorage. Alerts arrive on the existing
 * WebSocket as ``type: "alert"`` with ``event_type: "alert"`` in the
 * payload. Works while any authenticated dashboard tab is open.
 */
class PushNotifications {
    static STORAGE_KEY = 'meshpoint:push-notifications:v1';
    static DEFAULT_PREFS = {
        enabled: false,
        node_offline: true,
        node_online: true,
        battery_low: true,
        storm_guard: true,
        suppress_when_focused: true,
    };

    constructor() {
        this._prefs = this._readPrefs();
        this._swReady = null;
    }

    getPrefs() {
        return { ...this._prefs };
    }

    savePrefs(next) {
        this._prefs = { ...PushNotifications.DEFAULT_PREFS, ...next };
        try {
            localStorage.setItem(
                PushNotifications.STORAGE_KEY,
                JSON.stringify(this._prefs),
            );
        } catch (_e) { /* ignore quota errors */ }
    }

    isEnabled() {
        return !!this._prefs.enabled;
    }

    permissionState() {
        if (!('Notification' in window)) return 'unsupported';
        return Notification.permission;
    }

    async registerServiceWorker() {
        if (!('serviceWorker' in navigator)) return null;
        try {
            const reg = await navigator.serviceWorker.register('/sw.js', { scope: '/' });
            this._swReady = navigator.serviceWorker.ready;
            return reg;
        } catch (err) {
            console.warn('Service worker registration failed:', err);
            return null;
        }
    }

    async requestPermission() {
        if (!('Notification' in window)) {
            return 'unsupported';
        }
        if (Notification.permission === 'granted') {
            await this.registerServiceWorker();
            return 'granted';
        }
        if (Notification.permission === 'denied') {
            return 'denied';
        }
        const result = await Notification.requestPermission();
        if (result === 'granted') {
            await this.registerServiceWorker();
        }
        return result;
    }

    async enable() {
        const perm = await this.requestPermission();
        if (perm !== 'granted') return perm;
        this.savePrefs({ ...this._prefs, enabled: true });
        return perm;
    }

    disable() {
        this.savePrefs({ ...this._prefs, enabled: false });
    }

    handleAlert(data) {
        if (!this.isEnabled() || !data) return;
        const kind = data.alert_kind || '';
        if (!this._isKindEnabled(kind)) return;
        if (this._prefs.suppress_when_focused && document.visibilityState === 'visible') {
            return;
        }
        const title = data.title || 'Meshpoint alert';
        const body = data.body || '';
        this._show(title, body, data);
    }

    _isKindEnabled(kind) {
        const map = {
            node_offline: this._prefs.node_offline,
            node_online: this._prefs.node_online,
            battery_low: this._prefs.battery_low,
            storm_guard: this._prefs.storm_guard,
        };
        return map[kind] !== false;
    }

    async _show(title, body, payload) {
        if (!('Notification' in window) || Notification.permission !== 'granted') {
            return;
        }
        const tag = `meshpoint:${payload.alert_kind || 'alert'}:${payload.node_id || 'system'}`;
        try {
            if ('serviceWorker' in navigator) {
                const reg = this._swReady
                    ? await this._swReady
                    : await navigator.serviceWorker.ready;
                const active = reg.active || navigator.serviceWorker.controller;
                if (active) {
                    active.postMessage({
                        type: 'show-notification',
                        title,
                        body,
                        tag,
                        payload,
                    });
                    return;
                }
            }
            new Notification(title, { body, tag, renotify: true });
        } catch (err) {
            console.warn('Notification failed:', err);
        }
    }

    _readPrefs() {
        try {
            const raw = localStorage.getItem(PushNotifications.STORAGE_KEY);
            if (!raw) return { ...PushNotifications.DEFAULT_PREFS };
            return { ...PushNotifications.DEFAULT_PREFS, ...JSON.parse(raw) };
        } catch (_e) {
            return { ...PushNotifications.DEFAULT_PREFS };
        }
    }
}

window.PushNotifications = PushNotifications;
window.pushNotifications = new PushNotifications();
