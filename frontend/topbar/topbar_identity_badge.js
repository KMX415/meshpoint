/**
 * Topbar — LCD-style identity badge.
 *
 * Renders the device's short name in a segmented-font feel: monospace,
 * uppercase, wide letter-spacing, amber-tinted glow. A one-frame
 * flicker animation runs when the value changes so muscle memory
 * registers identity updates the same way a piece of physical lab
 * gear would.
 *
 * Single responsibility: paint the short name as a quick-glance badge
 * and play the change-flicker. Orchestrator pushes new values in via
 * setShortName().
 */
class TopbarIdentityBadge {
    constructor(rootEl) {
        this._root = rootEl;
        this._valueEl = rootEl.querySelector('.topbar-ident__value');
        this._lastValue = null;
    }

    setShortName(short) {
        const next = (short && short.trim()) ? short.trim().toUpperCase() : '----';
        if (next === this._lastValue) return;
        this._lastValue = next;
        this._valueEl.textContent = next;
        this._root.classList.remove('topbar-ident--flicker');
        // Force reflow so the animation restarts on consecutive updates.
        void this._root.offsetWidth;
        this._root.classList.add('topbar-ident--flicker');
    }
}

window.TopbarIdentityBadge = TopbarIdentityBadge;
