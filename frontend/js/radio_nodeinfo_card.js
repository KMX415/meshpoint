/**
 * Radio tab — NodeInfo Broadcast card (observational, v0.7.4).
 *
 * Live countdown to the next NodeInfo broadcast plus a status lamp
 * (ACTIVE / IDLE / PAUSED). Read-only: editing the interval and
 * triggering an on-demand broadcast moved to Configuration → Radio
 * in v0.7.4.
 */
class RadioNodeInfoCard {
    constructor(api) {
        this._api = api;
        this._root = null;
        this._timer = null;
        this._zeroSince = null;
        // Live broadcaster state. Drives countdown, lamp, last-sent.
        this._saved = {
            interval_minutes: 0,
            running: false,
            last_sent_at: null,
            next_due_at: null,
        };
    }

    mount(rootEl) {
        this._root = rootEl;
        rootEl.classList.add('r-card', 'r-card--readout');
        rootEl.innerHTML = `
            <div class="r-card__header">
                <h3 class="r-card__title">NodeInfo Broadcast</h3>
                <span class="status-lamp" id="r-ni-lamp">
                    <span class="status-lamp__dot"></span>
                    <span class="status-lamp__label">--</span>
                </span>
            </div>
            <div class="r-countdown">
                <div class="r-countdown__label">Next broadcast in</div>
                <div class="r-countdown__value" id="r-ni-countdown">--</div>
                <div class="r-countdown__sub">
                    <span class="r-countdown__sub-item" id="r-ni-last">
                        Last sent <span>--</span>
                    </span>
                    <span class="r-countdown__sub-sep">|</span>
                    <span class="r-countdown__sub-item">
                        Interval <span id="r-ni-interval-label">--</span>
                    </span>
                </div>
            </div>
            <a class="r-config-link" href="#/configuration/radio">
                <span>Edit broadcast interval</span>
                <span aria-hidden="true">→</span>
            </a>
        `;
    }

    render(config) {
        const ni = config.nodeinfo || {};
        this._saved.interval_minutes = ni.interval_minutes || 0;
        this._saved.running = !!ni.running;
        this._saved.last_sent_at = _parseTimestamp(ni.last_sent_at);
        this._saved.next_due_at = _parseTimestamp(ni.next_due_at);
        this._zeroSince = null;

        this._renderIntervalLabel();
        this._renderLamp();
        this._tick();
        this._startTimer();
    }

    destroy() {
        this._stopTimer();
    }

    _renderIntervalLabel() {
        const el = this._root.querySelector('#r-ni-interval-label');
        const minutes = this._saved.interval_minutes;
        el.textContent = minutes === 0 ? 'paused' : _formatDuration(minutes * 60);
    }

    _renderLamp() {
        const lamp = this._root.querySelector('#r-ni-lamp');
        const label = lamp.querySelector('.status-lamp__label');
        lamp.classList.remove(
            'status-lamp--ready',
            'status-lamp--warn',
            'status-lamp--off',
        );
        if (this._saved.interval_minutes === 0) {
            lamp.classList.add('status-lamp--off');
            label.textContent = 'PAUSED';
        } else if (this._saved.running) {
            lamp.classList.add('status-lamp--ready');
            label.textContent = 'ACTIVE';
        } else {
            lamp.classList.add('status-lamp--warn');
            label.textContent = 'IDLE';
        }
    }

    _startTimer() {
        this._stopTimer();
        this._timer = setInterval(() => this._tick(), 1000);
    }

    _stopTimer() {
        if (this._timer) {
            clearInterval(this._timer);
            this._timer = null;
        }
    }

    _tick() {
        const valueEl = this._root.querySelector('#r-ni-countdown');
        const lastEl = this._root.querySelector('#r-ni-last span');

        if (this._saved.interval_minutes === 0) {
            valueEl.textContent = 'PAUSED';
            valueEl.style.opacity = '0.45';
            lastEl.textContent = this._saved.last_sent_at
                ? _formatAgo(_secondsAgo(this._saved.last_sent_at))
                : 'never';
            return;
        }

        valueEl.style.opacity = '1';
        const next = this._saved.next_due_at;
        if (!next) {
            valueEl.textContent = 'awaiting first send';
        } else {
            const remaining = Math.max(
                0, Math.floor((next.getTime() - Date.now()) / 1000),
            );
            valueEl.textContent = remaining === 0
                ? 'broadcasting...'
                : _formatCountdown(remaining);
            if (remaining === 0) {
                this._scheduleBroadcastRefresh();
            }
        }

        lastEl.textContent = this._saved.last_sent_at
            ? _formatAgo(_secondsAgo(this._saved.last_sent_at))
            : 'never';
    }

    _scheduleBroadcastRefresh() {
        if (this._zeroSince !== null) return;
        this._zeroSince = Date.now();
        const refreshOnce = async () => {
            try {
                await this._api.refresh();
            } catch (_e) { /* swallow; backstop will retry */ }
        };
        // Wait ~2.5s for the backend broadcaster to complete TX (~700ms
        // airtime + Lambda/handler overhead), then re-fetch state. A
        // backstop refresh at +5s catches the rare case where the first
        // call races the backend's _last_sent_at write.
        setTimeout(refreshOnce, 2500);
        setTimeout(() => {
            if (this._zeroSince !== null) refreshOnce();
        }, 5000);
    }
}

function _parseTimestamp(value) {
    if (!value) return null;
    const d = new Date(value);
    return isNaN(d.getTime()) ? null : d;
}

function _secondsAgo(date) {
    return Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000));
}

function _formatCountdown(seconds) {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    if (h > 0) {
        return `${h}h ${String(m).padStart(2, '0')}m ${String(s).padStart(2, '0')}s`;
    }
    if (m > 0) return `${m}m ${String(s).padStart(2, '0')}s`;
    return `${s}s`;
}

function _formatAgo(seconds) {
    if (seconds < 60) return `${seconds} sec ago`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    return m > 0 ? `${h} hr ${m} min ago` : `${h} hr ago`;
}

function _formatDuration(seconds) {
    if (seconds < 3600) return `${Math.floor(seconds / 60)} min`;
    const h = seconds / 3600;
    return Number.isInteger(h) ? `${h} hr` : `${h.toFixed(1)} hr`;
}

window.RadioNodeInfoCard = RadioNodeInfoCard;
