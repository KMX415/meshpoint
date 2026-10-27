/**
 * Theme controller.
 *
 * Sets a data-theme attribute on <html>. Theme precedence:
 *   1. a per-browser choice made in the theme toggle (localStorage)
 *   2. the server default (dashboard.theme in local.yaml, exposed by
 *      GET /api/themes as `default`) -- also stamped onto <html> at
 *      serve time so it paints correctly with no flash
 *   3. `dark`
 *
 * The theme list is discovered at runtime from GET /api/themes, which
 * scans frontend/themes/<id>/theme.json (see src/api/theme_registry.py).
 * Each non-baseline theme also ships a theme.css, injected server-side
 * into <head>. `dark` is the built-in baseline (palette on :root in
 * dashboard.css) and is always valid.
 */
const THEME_FALLBACK = [
    { id: 'dark', label: 'Dark', icon: 'moon' },
    { id: 'high-contrast', label: 'High contrast', icon: 'contrast' },
    { id: 'sunlight', label: 'Sunlight', icon: 'sun' },
];

class ThemeController {
    constructor(storageKey = 'meshpoint:theme:v1') {
        this._key = storageKey;
        this._persisted = this._readPersisted();
        // Trust whatever the server already stamped on <html> until the
        // manifest fetch confirms a persisted choice or the real default.
        this._current = this._persisted
            || document.documentElement.getAttribute('data-theme')
            || 'dark';
        this._themes = THEME_FALLBACK.slice();
        this.serverDefault = 'dark';
        // Resolves once the /api/themes manifest has been folded in (or
        // the fetch has failed and the fallback stands). Consumers that
        // need the real label/icon list — e.g. the topbar toggle — await
        // this.
        this.ready = this._loadManifest();
    }

    init() { this._setAttr(this._current); }

    current() { return this._current; }

    /** Discovered themes: [{ id, label, icon }]. */
    themes() { return this._themes.slice(); }

    ids() { return this._themes.map((t) => t.id); }

    /** Set + persist as this browser's explicit choice. */
    apply(theme) {
        const next = this._setAttr(theme);
        this._persisted = next;
        try { localStorage.setItem(this._key, next); } catch (_e) {}
        return next;
    }

    /** Set the attribute (and notify) without recording a browser choice. */
    _setAttr(theme) {
        const next = this.ids().includes(theme) ? theme : 'dark';
        document.documentElement.setAttribute('data-theme', next);
        this._current = next;
        // Let JS-rendered surfaces that can't read CSS vars (xterm, canvas
        // charts) re-theme themselves without a reload.
        try {
            window.dispatchEvent(new CustomEvent('meshpoint:themechange', { detail: next }));
        } catch (_e) { /* CustomEvent unsupported */ }
        return next;
    }

    cycle() {
        const order = this.ids();
        const idx = order.indexOf(this._current);
        const next = order[(idx + 1) % order.length];
        return this.apply(next);
    }

    async _loadManifest() {
        try {
            const res = await fetch('/api/themes', { credentials: 'same-origin' });
            if (!res.ok) return this._themes;
            const data = await res.json();
            if (Array.isArray(data.themes) && data.themes.length) {
                this._themes = data.themes.map((t) => ({
                    id: t.id,
                    label: t.label || t.id,
                    icon: t.icon || '',
                }));
            }
            if (typeof data.default === 'string') this.serverDefault = data.default;

            if (this._persisted && this.ids().includes(this._persisted)) {
                // Honour the browser's own choice.
                if (this._current !== this._persisted) this._setAttr(this._persisted);
            } else if (this.ids().includes(this.serverDefault)) {
                // No local choice (or its folder was removed) -> server default.
                if (this._current !== this.serverDefault) this._setAttr(this.serverDefault);
            } else if (!this.ids().includes(this._current)) {
                this._setAttr('dark');
            }
        } catch (_e) {
            /* offline / pre-auth — fallback list stands */
        }
        return this._themes;
    }

    _readPersisted() {
        try { return localStorage.getItem(this._key); } catch (_e) { return null; }
    }
}

window.ThemeController = ThemeController;
window.themeController = new ThemeController();
