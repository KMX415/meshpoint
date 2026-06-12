/**
 * Console-style operator status footer for analytics tabs.
 *
 * Renders a slim monospace strip at the bottom of a panel:
 *   TRAFFIC · concentrator · 8,247 pkts · updated 14s ago
 */
class StatusStrip {
    constructor(hostEl, label) {
        this._host = hostEl;
        this._label = (label || 'STATUS').toUpperCase();
        this._root = null;
        this._itemsEl = null;
        this._updatedEl = null;
    }

    mount() {
        if (!this._host || this._root) return;
        const root = document.createElement('footer');
        root.className = 'status-strip';
        root.setAttribute('role', 'status');
        root.setAttribute('aria-live', 'polite');
        root.innerHTML = `
            <span class="status-strip__label">${this._label}</span>
            <span class="status-strip__sep" aria-hidden="true">·</span>
            <span class="status-strip__items"></span>
            <span class="status-strip__updated"></span>
        `;
        this._host.appendChild(root);
        this._root = root;
        this._itemsEl = root.querySelector('.status-strip__items');
        this._updatedEl = root.querySelector('.status-strip__updated');
    }

    /**
     * @param {string[]} items - dot-separated status fragments
     * @param {Date|number|null} updatedAt - when underlying data was fetched
     */
    update(items, updatedAt) {
        if (!this._root) return;
        const parts = (items || []).filter((item) => item != null && String(item).trim());
        this._itemsEl.textContent = parts.length ? parts.join(' · ') : 'waiting for data';
        this._root.classList.toggle('status-strip--quiet', parts.length === 0);

        if (this._updatedEl) {
            if (updatedAt) {
                this._updatedEl.textContent = ` · updated ${_formatRelative(updatedAt)}`;
            } else {
                this._updatedEl.textContent = '';
            }
        }
    }
}

function _formatRelative(timestamp) {
    const ms = timestamp instanceof Date ? timestamp.getTime() : Number(timestamp);
    if (!ms) return 'just now';
    const seconds = Math.max(0, Math.floor((Date.now() - ms) / 1000));
    if (seconds < 30) return 'just now';
    if (seconds < 60) return `${seconds}s ago`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
    return `${Math.floor(seconds / 86400)}d ago`;
}

window.StatusStrip = StatusStrip;
