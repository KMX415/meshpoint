/**
 * Soft hash router for the dashboard.
 *
 * One responsibility: turn the URL hash into a route id and notify
 * subscribers. No DOM, no styling, no business logic. The sidebar
 * controller subscribes to drive section visibility + active state.
 *
 * Route ids look like:
 *
 *   "dashboard"
 *   "stats"
 *   "messages"
 *   "radio"
 *   "terminal"
 *   "configuration/identity"
 *   "configuration/radio"
 *   "settings/updates"
 *
 * Default route is whatever was passed to the constructor; on a
 * fresh load with an empty hash we synthesize a #/<default> so
 * back-button history starts in a clean place.
 */

class Router {
    constructor(options = {}) {
        this._defaultRoute = options.defaultRoute || 'dashboard';
        this._allowedRoutes = new Set(options.allowedRoutes || []);
        this._listeners = new Set();
        this._currentRoute = null;
        this._onHashChange = this._onHashChange.bind(this);
    }

    start() {
        window.addEventListener('hashchange', this._onHashChange);
        if (!location.hash || location.hash === '#') {
            this.navigate(this._defaultRoute, { replace: true });
        } else {
            this._dispatch(this._readRouteFromHash());
        }
    }

    stop() {
        window.removeEventListener('hashchange', this._onHashChange);
    }

    onRouteChange(handler) {
        this._listeners.add(handler);
        if (this._currentRoute) handler(this._currentRoute);
        return () => this._listeners.delete(handler);
    }

    navigate(route, { replace = false } = {}) {
        const target = `#/${route}`;
        if (replace) {
            history.replaceState(null, '', target);
            this._dispatch(route);
        } else {
            location.hash = target;
        }
    }

    currentRoute() {
        return this._currentRoute;
    }

    _onHashChange() {
        const route = this._readRouteFromHash();
        if (route !== this._currentRoute) this._dispatch(route);
    }

    _readRouteFromHash() {
        const raw = location.hash.replace(/^#\/?/, '').trim();
        if (!raw) return this._defaultRoute;
        if (this._allowedRoutes.size && !this._allowedRoutes.has(raw)) {
            return this._defaultRoute;
        }
        return raw;
    }

    _dispatch(route) {
        this._currentRoute = route;
        this._listeners.forEach((handler) => {
            try { handler(route); } catch (err) { console.error('Router listener:', err); }
        });
    }
}

window.Router = Router;
