/**
 * P2000/Pagers/RTL433/ACARS tab content -- a live-scrolling decoded
 * message log with Start/Stop controls. Reused across kinds
 * (parameterized) since the pipeline/UI shape is identical, just a
 * different backend endpoint prefix, page title, and (for rtl_433,
 * whose decoded field set varies wildly by device model instead of a
 * fixed protocol/capcode/message shape, and for ACARS) row layout --
 * see src/audio/pager_listener.py, plugins/apps/rtl433/backend/listener.py
 * and plugins/apps/acars/backend/listener.py.
 *
 * Only one of Radio/P2000/Pagers/POCSAG/RTL433/ACARS can hold the
 * RTL-SDR dongle at a time (manual-stop-required design, 2026-07-12):
 * starting this while another is active returns an error from the
 * backend, shown inline rather than silently stopping the other one.
 */
// Matches src/audio/sdr_registry.py's owner names.
const _DONGLE_OWNER_LABELS = {
    radio: 'Radio', p2000: 'P2000', pagers: 'Pagers', pocsag: 'POCSAG', rtl433: 'RTL433', adsb: 'ADS-B', dab: 'DAB+',
    dab_scan: 'DAB+ scan',
};

class PagerPanel {
    constructor(kind, apiPrefix, title, rowRenderer = null) {
        this.kind = kind;              // 'p2000', 'pagers', 'pocsag', or 'rtl433' -- matches the registry
        this._apiPrefix = apiPrefix;   // e.g. '/api/p2000'
        this._title = title;
        this._root = null;
        this._statusTimer = null;
        // Optional (message, escapeFn) -> HTML override for kinds whose
        // decoded events don't fit the protocol/capcode/message shape
        // (e.g. rtl_433, whose fields vary per device model).
        this._rowRenderer = rowRenderer;
        // "Hide idle frames" -- POCSAG batches pad every unused frame slot
        // with a fixed idle code word (see src/audio/pager_listener.py);
        // multimon-ng doesn't recognize that pattern specially and just
        // decodes it like any other address, which comes out as a small
        // single-digit capcode (0-7) with Function 0 and no message text.
        // Real-world POCSAG capcodes are never that small, so filtering on
        // capcode<8 + function 0 + no message is a safe, practical way to
        // hide that structural noise. Per-kind storage key (not shared
        // across P2000/Pagers/POCSAG/RTL433) so each tab's toggle -- and
        // default -- is independent: POCSAG defaults ON (idle padding is
        // dense there, one real frame per otherwise-mostly-idle batch, see
        // extra/pocsag_test/pocsag_test.ino), everything else defaults off
        // so existing behavior doesn't silently change where the noise is
        // rare and someone might actually want to see every raw frame.
        this._hideIdle = (() => {
            try {
                const stored = localStorage.getItem(`meshpoint.pagerHideIdle.${kind}`);
                if (stored !== null) return stored === '1';
            } catch (_e) { /* fall through to the default below */ }
            return kind === 'pocsag';
        })();
        this._lastStatus = null;
        this._tunable = ['pagers', 'pocsag', 'rtl433', 'acars'].includes(kind);
        this._frequencyLoaded = false;
    }

    mount(root) {
        this._root = root;
        this._root.innerHTML = `
            <section class="lsn-section">
                <div class="panel">
                    <div class="panel__header">${this._esc(this._title)}</div>
                    <div class="panel__body pager-controls">
                        <div class="pager-status" data-pager-status>
                            <span class="pager-status__dot" data-pager-dot></span>
                            <span data-pager-status-text>idle</span>
                        </div>
                        <div class="pager-actions">
                            ${this._tunable ? `<label class="lsn-field">${this.kind === 'acars' ? 'ACARS frequencies (MHz, comma separated)' : 'Receive frequency (MHz)'}<input data-receive-frequency type="text" inputmode="decimal" autocomplete="off" placeholder="Enter local frequency"></label>` : ''}
                            ${this.kind === 'p2000' ? '<p>P2000: Netherlands FLEX service, fixed at 169.65 MHz.</p>' : ''}
                            <label class="pager-idle-toggle">
                                <input type="checkbox" data-pager-hide-idle ${this._hideIdle ? 'checked' : ''}>
                                Hide idle frames
                            </label>
                            <button class="terminal-button" type="button" data-pager-start>Start listening</button>
                            <button class="terminal-button" type="button" data-pager-stop>Stop</button>
                            <button class="terminal-button" type="button" data-pager-clear>Clear</button>
                        </div>
                    </div>
                </div>
            </section>
            <section class="lsn-section">
                <div class="panel">
                    <div class="panel__header">Messages <span class="pager-count" data-pager-count></span></div>
                    <div class="panel__body lsn-panel-body">
                        <div class="pager-log" data-pager-log>
                            <div class="pager-log__empty">No messages yet.</div>
                        </div>
                    </div>
                </div>
            </section>
        `;
        this._root.querySelector('[data-pager-start]').addEventListener('click', () => this._start());
        this._root.querySelector('[data-pager-stop]').addEventListener('click', () => this._stop());
        this._root.querySelector('[data-pager-clear]').addEventListener('click', () => this._clear());
        this._root.querySelector('[data-pager-hide-idle]').addEventListener('change', (ev) => {
            this._hideIdle = ev.target.checked;
            try { localStorage.setItem(`meshpoint.pagerHideIdle.${this.kind}`, this._hideIdle ? '1' : '0'); } catch (_e) { /* ignore */ }
            if (this._lastStatus) this._render(this._lastStatus);
        });
    }

    show() {
        this._refresh();
        this._statusTimer = setInterval(() => this._refresh(), 2000);
    }

    hide() {
        clearInterval(this._statusTimer);
        this._statusTimer = null;
    }

    async _start() {
        const btn = this._root.querySelector('[data-pager-start]');
        btn.disabled = true;
        try {
            const options = {method: 'POST'};
            if (this._tunable) {
                const values = this._root.querySelector('[data-receive-frequency]').value.split(',').map(v => v.trim());
                const numbers = values.map(Number);
                if (values.some(v => !v) || numbers.some(v => !Number.isFinite(v)) || (this.kind !== 'acars' && numbers.length !== 1)) throw new Error('Enter valid receive frequencies in MHz.');
                options.headers = {'Content-Type':'application/json'};
                options.body = JSON.stringify(this.kind === 'acars' ? {frequencies:numbers} : {frequency_mhz:numbers[0]});
            }
            const res = await fetch(`${this._apiPrefix}/start`, options);
            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                this._showError(err.detail || `HTTP ${res.status}`);
            }
        } catch (e) {
            this._showError(e.message);
        } finally {
            btn.disabled = false;
            this._refresh();
        }
    }

    async _stop() {
        try {
            await fetch(`${this._apiPrefix}/stop`, { method: 'POST' });
        } catch (_e) { /* ignore -- status poll will reflect reality */ }
        this._refresh();
    }

    async _clear() {
        // Independent of Start/Stop -- wipes the on-screen message
        // history without touching whether the listener is running.
        try {
            await fetch(`${this._apiPrefix}/clear`, { method: 'POST' });
        } catch (_e) { /* ignore -- status poll will reflect reality */ }
        this._refresh();
    }

    async _refresh() {
        try {
            const res = await fetch(`${this._apiPrefix}/status`);
            if (!res.ok) return;
            const status = await res.json();
            this._render(status);
        } catch (_e) { /* transient network hiccup -- next poll retries */ }
    }

    _render(status) {
        this._lastStatus = status;
        const frequencyInput = this._root.querySelector('[data-receive-frequency]');
        if (frequencyInput) {
            if (!this._frequencyLoaded && !frequencyInput.value) {
                frequencyInput.value = this.kind === 'acars' ? (status.frequencies || []).join(', ') : (status.frequency_mhz || '');
                this._frequencyLoaded = true;
            }
            frequencyInput.disabled = !!status.running;
        }
        const dot = this._root.querySelector('[data-pager-dot]');
        const text = this._root.querySelector('[data-pager-status-text]');
        const startBtn = this._root.querySelector('[data-pager-start]');
        // Only the RTL-SDR dongle's ACTUAL owner can be "busy" from this
        // tab's point of view -- if dongle_owner === our own kind, that's
        // just us running, not something else in the way.
        const busyOwner = (status.dongle_owner && status.dongle_owner !== this.kind)
            ? status.dongle_owner : null;

        if (dot) {
            dot.classList.toggle('pager-status__dot--on', !!status.running);
            dot.classList.toggle('pager-status__dot--busy', !!busyOwner);
        }
        if (text) {
            if (status.running) {
                const f = status.frequencies;
                if (Array.isArray(f) && f.length > 1) {
                    text.textContent = `listening on ${f.length} channels (${f[0]}–${f[f.length - 1]} MHz)`;
                } else if (Array.isArray(f) && f.length === 1) {
                    text.textContent = `listening on ${f[0]} MHz`;
                } else {
                    text.textContent = `listening on ${Number(status.frequency_mhz).toFixed(4)} MHz`;
                }
            } else if (busyOwner) {
                text.textContent = `busy -- in use by ${_DONGLE_OWNER_LABELS[busyOwner] || busyOwner}`;
            } else if (status.last_error) {
                text.textContent = `stopped -- ${status.last_error}`;
            } else {
                text.textContent = 'idle';
            }
        }
        if (startBtn) startBtn.disabled = !!status.running || !!busyOwner;

        const countEl = this._root.querySelector('[data-pager-count]');
        if (countEl) countEl.textContent = status.message_count ? `(${status.message_count})` : '';

        const log = this._root.querySelector('[data-pager-log]');
        if (!log) return;
        let messages = status.messages || [];
        if (this._hideIdle) messages = messages.filter((m) => !this._isIdleFrame(m));
        if (messages.length === 0) {
            log.innerHTML = '<div class="pager-log__empty">No messages yet.</div>';
            return;
        }
        // Newest first for a live feed.
        log.innerHTML = messages.slice().reverse().map((m) => this._rowHtml(m)).join('');
    }

    // POCSAG batch padding, not a real page -- see the constructor comment
    // above for the reasoning. Only ever true for the default POCSAG/Pagers
    // row shape (m.function is undefined for FLEX/RTL433 rows, so this is
    // naturally a no-op there).
    _isIdleFrame(m) {
        return m.function === '0' && !m.message && Number(m.capcode) < 8;
    }

    _rowHtml(m) {
        if (this._rowRenderer) return this._rowRenderer(m, this._esc.bind(this));
        const time = m.received_at
            ? new Date(m.received_at * 1000).toLocaleTimeString([], {
                hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
            })
            : '';
        return `
            <div class="pager-row">
                <span class="pager-row__time">${this._esc(time)}</span>
                <span class="pager-row__proto">${this._esc(m.protocol || '')}</span>
                <span class="pager-row__capcode">${this._esc(m.capcode || '')}</span>
                <span class="pager-row__msg">${this._esc(m.message || m.raw || '')}</span>
            </div>
        `;
    }

    _showError(msg) {
        const text = this._root.querySelector('[data-pager-status-text]');
        if (text) text.textContent = msg;
    }

    _esc(str) {
        const el = document.createElement('span');
        el.textContent = str == null ? '' : String(str);
        return el.innerHTML;
    }
}

window.PagerPanel = PagerPanel;
