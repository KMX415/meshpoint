/**
 * Theme controller (dark / high-contrast / sunlight).
 *
 * Sets a data-theme attribute on <html> and persists the choice.
 * High-contrast and sunlight themes are CSS-only opt-ins — see
 * frontend/css/theme_high_contrast.css.
 *
 * Single responsibility: persist + apply. Settings UI flips the
 * attribute; CSS does the rest.
 */
class ThemeController {
    constructor(storageKey = 'meshpoint:theme:v1') {
        this._key = storageKey;
        this._current = this._readPersisted() || 'dark';
    }

    init() { this.apply(this._current); }

    current() { return this._current; }

    apply(theme) {
        const valid = ['dark', 'high-contrast', 'sunlight'];
        const next = valid.includes(theme) ? theme : 'dark';
        document.documentElement.setAttribute('data-theme', next);
        this._current = next;
        try { localStorage.setItem(this._key, next); } catch (_e) {}
    }

    cycle() {
        const order = ['dark', 'high-contrast', 'sunlight'];
        const idx = order.indexOf(this._current);
        const next = order[(idx + 1) % order.length];
        this.apply(next);
        return next;
    }

    _readPersisted() {
        try { return localStorage.getItem(this._key); } catch (_e) { return null; }
    }
}

window.ThemeController = ThemeController;
window.themeController = new ThemeController();
