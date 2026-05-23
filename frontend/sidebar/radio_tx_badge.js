/**
 * Sidebar Radio item — live NodeInfo TX countdown badge.
 *
 * Surfaces the next-broadcast countdown on the Radio sidebar item so
 * an operator on any page can glance at the rail and know when the
 * Meshpoint will next advertise itself on the mesh. Mirrors the data
 * the in-page NodeInfo card on Configuration > Radio renders, but
 * this module is global and runs regardless of which route is
 * active.
 *
 * Single responsibility: own the lifecycle of one sidebar badge
 * driven by the NodeInfo broadcaster's next_due_at. Decoupled from
 * radio_nodeinfo_card.js on purpose — that card mounts/unmounts with
 * the Configuration > Radio page, this badge is sidebar-resident
 * and keeps ticking even while you're three menus deep in something
 * else.
 *
 * Data path:
 *   - GET /api/config every CONFIG_REFRESH_MS (currently 30 s) for
 *     the broadcaster's interval_minutes / running / next_due_at
 *     telemetry. Same endpoint the NodeInfo card uses; cheap GET.
 *   - 1 s wall-clock tick recomputes the formatted remaining time
 *     from the cached next_due_at and pushes it to the sidebar via
 *     SidebarController.setStatusBadge('radio', text).
 *   - When the countdown hits zero we schedule one extra config
 *     refresh ~3 s later so the new last_sent_at and next_due_at
 *     show up promptly without waiting for the next 30 s poll.
 *
 * Rendering rules:
 *   - interval_minutes === 0 (paused) -> badge hidden
 *   - broadcaster not running -> badge hidden
 *   - next_due_at unknown -> badge hidden
 *   - remaining > 1 hr -> "TX 2h"
 *   - remaining > 1 min -> "TX 12m"
 *   - remaining > 0 s   -> "TX 45s"
 *   - remaining == 0    -> "TX..."
 */
class RadioTxBadge {
    constructor(sidebar, fetchImpl = null) {
        this._sidebar = sidebar;
        this._fetch = fetchImpl || ((url, opts) => window.fetch(url, opts));
        this._tickInterval = null;
        this._refreshInterval = null;
        this._refreshTimeout = null;
        this._state = {
            intervalMinutes: 0,
            running: false,
            nextDueAt: null,
        };
        this._lastZeroAt = 0;
    }

    /**
     * Wire up timers and trigger an initial fetch. Idempotent: a
     * second call after destroy() will resume cleanly.
     */
    init() {
        this._refreshConfig();
        this._refreshInterval = setInterval(
            () => this._refreshConfig(),
            CONFIG_REFRESH_MS,
        );
        this._tickInterval = setInterval(() => this._tick(), 1000);
    }

    destroy() {
        if (this._tickInterval) {
            clearInterval(this._tickInterval);
            this._tickInterval = null;
        }
        if (this._refreshInterval) {
            clearInterval(this._refreshInterval);
            this._refreshInterval = null;
        }
        if (this._refreshTimeout) {
            clearTimeout(this._refreshTimeout);
            this._refreshTimeout = null;
        }
    }

    async _refreshConfig() {
        try {
            const res = await this._fetch('/api/config', {
                credentials: 'same-origin',
            });
            if (!res.ok) return;
            const config = await res.json();
            this._applyConfig(config);
        } catch (_e) {
            // Swallow: leaves cached state in place so the badge keeps
            // ticking against the last known next_due_at; next poll
            // tries again. Logging would just spam the console on
            // intermittent disconnects.
        }
    }

    _applyConfig(config) {
        const ni = (config && config.nodeinfo) || {};
        this._state.intervalMinutes = Number(ni.interval_minutes) || 0;
        this._state.running = !!ni.running;
        this._state.nextDueAt = _parseTimestamp(ni.next_due_at);
        this._tick();
    }

    _tick() {
        const { intervalMinutes, running, nextDueAt } = this._state;
        if (
            intervalMinutes === 0
            || !running
            || !nextDueAt
        ) {
            this._sidebar.setStatusBadge('radio', null);
            return;
        }

        const remaining = Math.max(
            0,
            Math.floor((nextDueAt.getTime() - Date.now()) / 1000),
        );
        const label = _formatBadge(remaining);
        this._sidebar.setStatusBadge('radio', label);

        if (remaining === 0) this._scheduleZeroRefresh();
    }

    /**
     * The countdown just hit zero, which means the broadcaster is
     * about to TX (or just did). Schedule one extra config refresh
     * a few seconds later so the new last_sent_at and re-anchored
     * next_due_at show up promptly without waiting for the routine
     * 30 s poll. Idempotent within a single zero window so we don't
     * stack timeouts on every 1 s tick that observes remaining=0.
     */
    _scheduleZeroRefresh() {
        const now = Date.now();
        if (now - this._lastZeroAt < ZERO_REFRESH_DEBOUNCE_MS) return;
        this._lastZeroAt = now;
        if (this._refreshTimeout) clearTimeout(this._refreshTimeout);
        this._refreshTimeout = setTimeout(
            () => this._refreshConfig(),
            ZERO_REFRESH_DELAY_MS,
        );
    }
}

const CONFIG_REFRESH_MS = 30 * 1000;
const ZERO_REFRESH_DELAY_MS = 3000;
const ZERO_REFRESH_DEBOUNCE_MS = 10 * 1000;

function _parseTimestamp(value) {
    if (!value) return null;
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? null : d;
}

function _formatBadge(seconds) {
    if (seconds <= 0) return 'TX...';
    if (seconds < 60) return `TX ${seconds}s`;
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `TX ${minutes}m`;
    const hours = Math.floor(minutes / 60);
    return `TX ${hours}h`;
}

window.RadioTxBadge = RadioTxBadge;
