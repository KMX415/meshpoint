/**
 * Browser-local "favorite" node list for the Meshpoint dashboard.
 *
 * iceice400 (Discord, May 2026) requested star/pin functionality on the
 * Node Cards list, drawer, and map. Storage is per-browser localStorage
 * for v0.7.5: forward-compatible if a backend favorites table is ever
 * added (the frontend would read localStorage first, then migrate up).
 *
 * Storage key: meshpoint.nodeFavorites (array of node_id strings).
 * Change event: meshpoint:node-favorites (CustomEvent with detail.list).
 *
 * Cap is 200 entries: keeps the localStorage payload small (well under
 * the 5 MB browser quota) and prevents accidental accumulation if a user
 * mass-favorites every node they see during a busy mesh event. When the
 * cap is hit, the oldest entry is dropped on the next add.
 */

const STORAGE_KEY = 'meshpoint.nodeFavorites';
const CHANGE_EVENT = 'meshpoint:node-favorites';
const MAX_FAVORITES = 200;

function _load() {
    try {
        const raw = localStorage.getItem(STORAGE_KEY);
        if (!raw) return [];
        const parsed = JSON.parse(raw);
        if (!Array.isArray(parsed)) return [];
        return parsed.filter((v) => typeof v === 'string' && v.length > 0);
    } catch (_e) {
        return [];
    }
}

let _favorites = _load();

function _save() {
    try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(_favorites));
    } catch (_e) {
        /* private mode / quota -- best-effort persistence */
    }
}

function _emit() {
    window.dispatchEvent(new CustomEvent(CHANGE_EVENT, {
        detail: { list: [..._favorites] },
    }));
}

class MeshpointNodeFavorites {
    /** @returns {string[]} a copy of the favorites list (no live reference). */
    static list() {
        return [..._favorites];
    }

    /** @param {string} nodeId */
    static has(nodeId) {
        if (!nodeId) return false;
        return _favorites.includes(String(nodeId));
    }

    /**
     * Toggle membership. Returns true if the node is now favorited,
     * false if it was just removed.
     * @param {string} nodeId
     */
    static toggle(nodeId) {
        if (!nodeId) return false;
        const id = String(nodeId);
        const idx = _favorites.indexOf(id);
        if (idx >= 0) {
            _favorites.splice(idx, 1);
            _save();
            _emit();
            return false;
        }
        if (_favorites.length >= MAX_FAVORITES) {
            console.warn(
                `MeshpointNodeFavorites: cap of ${MAX_FAVORITES} reached, ` +
                'dropping oldest entry to make room.'
            );
            _favorites.shift();
        }
        _favorites.push(id);
        _save();
        _emit();
        return true;
    }

    /**
     * Subscribe to favorite-list changes.
     * @param {(event: CustomEvent) => void} handler
     * @returns {() => void} unsubscribe function
     */
    static onChange(handler) {
        window.addEventListener(CHANGE_EVENT, handler);
        return () => window.removeEventListener(CHANGE_EVENT, handler);
    }
}

window.MeshpointNodeFavorites = MeshpointNodeFavorites;
