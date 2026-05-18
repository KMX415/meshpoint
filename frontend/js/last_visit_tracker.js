/**
 * Per-route last-visit tracker.
 *
 * Records the timestamp of when the user last viewed each route in
 * localStorage and exposes it for the "what changed since" line on
 * each page. Survives reloads; per-user (browser-scoped).
 *
 * Single responsibility: timestamps. Pages compute their own deltas
 * by reading getLastVisit(route) and querying the relevant data
 * source for "events newer than that timestamp."
 */
class LastVisitTracker {
    constructor(storageKey = 'meshpoint:last_visit:v1') {
        this._key = storageKey;
        this._cache = this._load();
    }

    /** Returns ms-since-epoch or null when route has never been visited. */
    getLastVisit(route) {
        if (!route) return null;
        const ts = this._cache[route];
        return typeof ts === 'number' ? ts : null;
    }

    markVisited(route, timestamp = null) {
        if (!route) return;
        this._cache[route] = timestamp ?? Date.now();
        this._save();
    }

    _load() {
        try {
            const raw = localStorage.getItem(this._key);
            if (!raw) return {};
            const parsed = JSON.parse(raw);
            return (parsed && typeof parsed === 'object') ? parsed : {};
        } catch (_e) {
            return {};
        }
    }

    _save() {
        try {
            localStorage.setItem(this._key, JSON.stringify(this._cache));
        } catch (_e) { /* ignore quota / private mode */ }
    }
}

window.LastVisitTracker = LastVisitTracker;
window.lastVisitTracker = new LastVisitTracker();
