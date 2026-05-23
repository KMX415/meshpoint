/**
 * Wires SinceLine into specific routes and computes deltas.
 *
 * Single responsibility: glue the LastVisitTracker + SinceLine to
 * the router. Per-route snapshot providers return a numeric counter
 * (e.g. total packets). The controller stores the counter at last
 * visit and renders the delta on the next visit.
 *
 * Snapshot providers should be cheap and synchronous (or return a
 * Promise resolving quickly). They are called once on route entry.
 */
class SinceLineController {
    constructor(router, tracker) {
        this._router = router;
        this._tracker = tracker;
        this._routes = new Map();
    }

    register(routeId, config) {
        // config = {
        //   hostEl, label, getCount: () => number|Promise<number>,
        // }
        this._routes.set(routeId, {
            ...config,
            line: new window.SinceLine(config.hostEl),
            mounted: false,
        });
    }

    start() {
        if (!this._router) return;
        this._router.onRouteChange((route) => this._onRouteEnter(route));
    }

    async _onRouteEnter(route) {
        const cfg = this._routes.get(route);
        if (!cfg) return;
        if (!cfg.mounted) {
            cfg.line.mount();
            cfg.mounted = true;
        }

        const storageKey = `route:${route}`;
        const lastVisitAt = this._tracker.getLastVisit(storageKey);
        const lastCount = this._readNumber(`since:${route}:count`);
        let nowCount = 0;
        try {
            nowCount = Number(await cfg.getCount()) || 0;
        } catch (_e) { nowCount = 0; }
        const delta = Math.max(0, nowCount - (lastCount ?? nowCount));

        cfg.line.update({
            lastVisitAt,
            items: delta > 0
                ? [{ label: cfg.label || 'events', count: delta }]
                : [],
        });

        this._tracker.markVisited(storageKey);
        this._writeNumber(`since:${route}:count`, nowCount);
    }

    _readNumber(key) {
        try {
            const raw = localStorage.getItem(key);
            if (raw === null) return null;
            const n = Number(raw);
            return Number.isFinite(n) ? n : null;
        } catch (_e) { return null; }
    }

    _writeNumber(key, value) {
        try { localStorage.setItem(key, String(value)); } catch (_e) {}
    }
}

window.SinceLineController = SinceLineController;
