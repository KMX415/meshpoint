/**
 * DAB+ Config tab -- shows what dab_channel_scan.py found (read from its
 * JSON output via GET /api/dab/scan-results) and lets an admin set a
 * friendlier display name per channel (PUT .../scan-results/{ch}/name),
 * layered on top of the raw broadcast ensemble label without touching it.
 * Also runs the scan itself (POST /api/dab/scan/stream) with live output,
 * instead of CLI-only over SSH.
 *
 * The scan DOES claim the RTL-SDR dongle (see src/audio/sdr_registry.py)
 * for its duration, same as Radio/DAB+/P2000/Pagers/POCSAG/RTL433 -- the
 * script itself talks to welle-cli directly and knows nothing about the
 * registry, so the backend route claims on this tab's behalf instead of
 * relying on the operator to remember to stop other tabs first. Reading/
 * renaming channels (everything else here) stays read-only against the
 * dongle, same as always.
 */

// Full Band III DAB channel raster (5A-13F, 38 channels; ETSI EN 300 401),
// grouped by band for the scan checkboxes -- same raster as dab_panel.js's
// DAB_ALL_CHANNELS, duplicated rather than imported per this repo's small-
// helper convention across independent frontend modules (see dab_panel.js's
// own note on its VU-meter code for the same reasoning).
const DAB_CONFIG_CHANNEL_GROUPS = (() => {
    const groups = [];
    for (let n = 5; n <= 12; n++) {
        groups.push({ band: String(n), channels: ['A', 'B', 'C', 'D'].map((l) => `${n}${l}`) });
    }
    groups.push({ band: '13', channels: ['A', 'B', 'C', 'D', 'E', 'F'].map((l) => `13${l}`) });
    return groups;
})();

// This deployment's own confirmed-good NL DAB+ channels (NPO/Commercial/
// Throwback/MTVNL/N-H-Flevo -- the same 5 the DAB+ tab's original curated
// presets were built from), pre-checked in the picker so a routine
// targeted rescan doesn't need re-selecting them by hand every time.
const DAB_CONFIG_DEFAULT_CHANNELS = ['7D', '8B', '9C', '11C', '12C'];

class DabConfigPanel {
    constructor() {
        this._root = null;
        this._data = null;
        this._editingChannel = null;
        this._scanning = false;
    }

    mount(root) {
        this._root = root;
        this._root.innerHTML = `
            <section class="lsn-section">
                <div class="panel">
                    <div class="panel__header">
                        <span>Scan for DAB+ Channels</span>
                    </div>
                    <div class="panel__body lsn-panel-body">
                        <div class="dabcfg-hint">
                            Drives welle-cli across the Band III raster to find which channels decode
                            content at this antenna. A full scan can take up to ~19 minutes; scanning
                            specific channels is faster for a targeted rescan (e.g. after a "nothing"
                            result that might just be a temporary receiver issue). Merges into the
                            existing results by default -- nothing already found is lost.
                        </div>
                        <div class="dabcfg-scan-actions">
                            <button class="terminal-button terminal-button--primary" type="button" data-dabcfg-scan-full>
                                Full scan (all 38 channels)
                            </button>
                            <button class="terminal-button" type="button" data-dabcfg-scan-toggle-advanced>
                                Scan specific channelsâ€¦
                            </button>
                        </div>
                        <div class="dabcfg-scan-advanced" data-dabcfg-scan-advanced hidden>
                            <div class="dabcfg-scan-channels" data-dabcfg-scan-channels>
                                ${DAB_CONFIG_CHANNEL_GROUPS.map((g) => `
                                    <div class="dabcfg-scan-band">
                                        <span class="dabcfg-scan-band__label">${this._esc(g.band)}</span>
                                        ${g.channels.map((ch) => `
                                            <label class="dabcfg-scan-chan">
                                                <input type="checkbox" value="${this._esc(ch)}" data-dabcfg-scan-chan-input
                                                       ${DAB_CONFIG_DEFAULT_CHANNELS.includes(ch) ? 'checked' : ''}>
                                                ${this._esc(ch)}
                                            </label>
                                        `).join('')}
                                    </div>
                                `).join('')}
                            </div>
                            <div class="dabcfg-scan-options">
                                <label class="dabcfg-scan-option">
                                    <span>Timeout per channel (seconds)</span>
                                    <input type="number" class="dabcfg-scan-option__input"
                                           min="5" max="240" value="60" data-dabcfg-scan-timeout>
                                </label>
                                <label class="dabcfg-scan-option dabcfg-scan-option--checkbox">
                                    <input type="checkbox" data-dabcfg-scan-discard>
                                    Discard existing results (start fresh instead of merging)
                                </label>
                            </div>
                            <button class="terminal-button terminal-button--primary" type="button" data-dabcfg-scan-selected>
                                Scan selected channels
                            </button>
                        </div>
                        <button class="terminal-button dabcfg-scan-output-toggle" type="button" data-dabcfg-scan-toggle-output hidden>
                            Show output
                        </button>
                        <pre class="dabcfg-scan-output" data-dabcfg-scan-output hidden></pre>
                        <p class="cfg-status" data-dabcfg-scan-status aria-live="polite"></p>
                    </div>
                </div>
            </section>
            <section class="lsn-section">
                <div class="panel">
                    <div class="panel__header dabcfg-header">
                        <span>DAB+ Config</span>
                        <button class="terminal-button" type="button" data-dabcfg-refresh>Refresh</button>
                    </div>
                    <div class="panel__body lsn-panel-body">
                        <div class="dabcfg-hint">
                            Channels found by the scan above. Names here are editable overrides --
                            the raw scanned label is kept underneath and used as the default whenever
                            no override is set.
                        </div>
                        <div data-dabcfg-body>Loading...</div>
                    </div>
                </div>
            </section>
        `;
        this._root.querySelector('[data-dabcfg-refresh]').addEventListener('click', () => this._refresh());
        this._root.querySelector('[data-dabcfg-scan-full]')
            .addEventListener('click', () => this._runScan({ channels: [] }));
        this._root.querySelector('[data-dabcfg-scan-selected]')
            .addEventListener('click', () => this._runSelectedScan());
        this._root.querySelector('[data-dabcfg-scan-toggle-advanced]')
            .addEventListener('click', (e) => this._toggleScanAdvanced(e.currentTarget));
        this._root.querySelector('[data-dabcfg-scan-toggle-output]')
            .addEventListener('click', (e) => this._toggleScanOutput(e.currentTarget));
    }

    show() {
        this._refresh();
    }

    hide() {
        // Static file, no live polling to stop.
    }

    async _refresh() {
        const body = this._root.querySelector('[data-dabcfg-body]');
        body.innerHTML = 'Loading...';
        try {
            const res = await fetch('/api/dab/scan-results');
            if (res.status === 404) {
                this._data = null;
                const err = await res.json().catch(() => ({}));
                body.innerHTML = `<div class="dabcfg-empty">
                    ${this._esc(err.detail || 'No DAB channel scan results found yet.')}
                </div>`;
                return;
            }
            if (!res.ok) {
                body.innerHTML = `<div class="dabcfg-empty">Error loading scan results (HTTP ${res.status}).</div>`;
                return;
            }
            this._data = await res.json();
            this._render();
        } catch (e) {
            body.innerHTML = `<div class="dabcfg-empty">Error loading scan results: ${this._esc(e.message)}</div>`;
        }
    }

    _render() {
        const body = this._root.querySelector('[data-dabcfg-body]');
        const channels = (this._data.channels || []).filter(c => c.ensemble || (c.stations || []).length);
        if (!channels.length) {
            body.innerHTML = `<div class="dabcfg-empty">Scan results loaded, but no channel has decoded anything yet.</div>`;
            return;
        }
        const lastRun = this._data.last_run_at ? new Date(this._data.last_run_at).toLocaleString() : 'unknown';
        body.innerHTML = `
            <div class="dabcfg-meta">Last scan: ${this._esc(lastRun)} &middot; ${channels.length} channel(s) with content</div>
            ${channels.map(c => this._rowHtml(c)).join('')}
        `;
        channels.forEach((c) => {
            const row = body.querySelector(`[data-dabcfg-row="${CSS.escape(c.channel)}"]`);
            if (!row) return;
            const editBtn = row.querySelector('[data-dabcfg-edit]');
            const saveBtn = row.querySelector('[data-dabcfg-save]');
            const cancelBtn = row.querySelector('[data-dabcfg-cancel]');
            if (editBtn) editBtn.addEventListener('click', () => this._startEdit(c.channel));
            if (saveBtn) saveBtn.addEventListener('click', () => this._saveEdit(c.channel));
            if (cancelBtn) cancelBtn.addEventListener('click', () => { this._editingChannel = null; this._render(); });
        });
    }

    _rowHtml(c) {
        const displayName = c.custom_name || c.ensemble || c.channel;
        const editing = this._editingChannel === c.channel;
        const stationCount = (c.stations || []).length;
        return `
            <div class="dabcfg-row" data-dabcfg-row="${this._esc(c.channel)}">
                <div class="dabcfg-row__top">
                    <div class="dabcfg-row__chan">${this._esc(c.channel)}</div>
                    <div class="dabcfg-row__name">
                        ${editing
                            ? `<input type="text" class="dabcfg-row__input" data-dabcfg-input
                                   value="${this._esc(c.custom_name || '')}"
                                   placeholder="${this._esc(c.ensemble || c.channel)}">`
                            : `${this._esc(displayName)}` +
                              (c.custom_name ? ' <span class="dabcfg-row__badge">custom</span>' : '')}
                    </div>
                    <div class="dabcfg-row__meta">SNR ${Number(c.snr || 0).toFixed(1)} dB &middot; ${stationCount} station(s)</div>
                    <div class="dabcfg-row__actions">
                        ${editing
                            ? `<button class="terminal-button" type="button" data-dabcfg-save>Save</button>
                               <button class="terminal-button" type="button" data-dabcfg-cancel>Cancel</button>`
                            : `<button class="terminal-button" type="button" data-dabcfg-edit>Rename</button>`}
                    </div>
                </div>
                ${stationCount ? `<div class="dabcfg-row__stations">${(c.stations || []).map(s => this._esc(s.name)).join(', ')}</div>` : ''}
            </div>
        `;
    }

    _startEdit(channel) {
        this._editingChannel = channel;
        this._render();
        const row = this._root.querySelector(`[data-dabcfg-row="${CSS.escape(channel)}"]`);
        const input = row && row.querySelector('[data-dabcfg-input]');
        if (input) { input.focus(); input.select(); }
    }

    async _saveEdit(channel) {
        const row = this._root.querySelector(`[data-dabcfg-row="${CSS.escape(channel)}"]`);
        const input = row && row.querySelector('[data-dabcfg-input]');
        const name = input ? input.value : '';
        try {
            const res = await fetch(`/api/dab/scan-results/${encodeURIComponent(channel)}/name`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ custom_name: name }),
            });
            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                alert('Error saving name: ' + (err.detail || `HTTP ${res.status}`));
                return;
            }
        } catch (e) {
            alert('Error saving name: ' + e.message);
            return;
        }
        this._editingChannel = null;
        await this._refresh();
    }

    _toggleScanAdvanced(button) {
        const advanced = this._root.querySelector('[data-dabcfg-scan-advanced]');
        if (!advanced) return;
        advanced.hidden = !advanced.hidden;
        button.textContent = advanced.hidden ? 'Scan specific channelsâ€¦' : 'Hide channel picker';
    }

    _toggleScanOutput(button) {
        const pre = this._root.querySelector('[data-dabcfg-scan-output]');
        if (!pre) return;
        pre.hidden = !pre.hidden;
        button.textContent = pre.hidden ? 'Show output' : 'Hide output';
    }

    _appendScanOutput(text) {
        const pre = this._root.querySelector('[data-dabcfg-scan-output]');
        if (!pre || !text) return;
        pre.textContent = pre.textContent ? `${pre.textContent}\n${text}` : text;
        pre.scrollTop = pre.scrollHeight;
    }

    _runSelectedScan() {
        const checked = Array.from(
            this._root.querySelectorAll('[data-dabcfg-scan-chan-input]:checked'),
        ).map((el) => el.value);
        if (!checked.length) {
            const status = this._root.querySelector('[data-dabcfg-scan-status]');
            if (status) {
                status.dataset.kind = 'error';
                status.textContent = 'Pick at least one channel, or use Full scan for all 38.';
            }
            return;
        }
        const timeoutEl = this._root.querySelector('[data-dabcfg-scan-timeout]');
        const discardEl = this._root.querySelector('[data-dabcfg-scan-discard]');
        this._runScan({
            channels: checked,
            timeout: timeoutEl ? Number(timeoutEl.value) || 60 : 60,
            discardExisting: !!(discardEl && discardEl.checked),
        });
    }

    /** Runs dab_channel_scan.py via POST /api/dab/scan/stream and
     * streams its output live -- same NDJSON pattern as the Meshtastic/
     * MeshCore/POCSAG firmware-flash cards (window.UpdateStreamClient).
     * On success, reloads the channel list below so newly-scanned content
     * shows up immediately without a manual Refresh click. */
    async _runScan({ channels = [], timeout = 60, discardExisting = false } = {}) {
        if (this._scanning) return;

        if (discardExisting) {
            const ok = await window.confirmModal({
                label: 'Discard existing scan results',
                description: 'This scan will start from a clean file instead of merging into '
                    + 'what\'s already been found -- every channel not covered by this run loses '
                    + 'its station list. Not reversible from here.',
            });
            if (!ok) return;
        }

        const fullBtn = this._root.querySelector('[data-dabcfg-scan-full]');
        const selectedBtn = this._root.querySelector('[data-dabcfg-scan-selected]');
        const outputToggle = this._root.querySelector('[data-dabcfg-scan-toggle-output]');
        const status = this._root.querySelector('[data-dabcfg-scan-status]');
        const outputPre = this._root.querySelector('[data-dabcfg-scan-output]');

        this._scanning = true;
        if (fullBtn) fullBtn.disabled = true;
        if (selectedBtn) selectedBtn.disabled = true;
        if (outputToggle) outputToggle.hidden = false;
        if (outputPre) outputPre.textContent = '';
        status.dataset.kind = 'pending';
        status.textContent = channels.length
            ? `Scanning ${channels.join(', ')} (timeout ${timeout}s each)â€¦`
            : `Scanning all 38 channels (timeout ${timeout}s each, up to ~${Math.round(38 * timeout / 60)} min)â€¦`;
        // No synthetic "starting" line here (unlike the firmware-flash
        // cards' own intro line) -- the next thing the output box shows
        // is the real echoed `$ ... --channels ... --timeout ...` command
        // from the {type:'started'} event below, which says the same
        // thing more precisely. The status line above already covers
        // the at-a-glance summary; a hand-written restatement here was
        // just redundant with both.

        let finalResult = null;
        try {
            finalResult = await window.UpdateStreamClient.postNdjson(
                '/api/dab/scan/stream',
                { channels, timeout, discard_existing: discardExisting },
                (event) => {
                    if (event.type === 'started' && Array.isArray(event.cmd)) {
                        this._appendScanOutput(`$ ${event.cmd.join(' ')}`);
                    } else if (event.type === 'line') {
                        this._appendScanOutput(event.text);
                    }
                },
            );
        } catch (err) {
            const busy = err && err.status === 503;
            status.dataset.kind = 'error';
            status.textContent = busy
                ? 'RTL-SDR dongle is busy with another listener -- stop it first.'
                : `Request failed: ${err.message || err}`;
            this._appendScanOutput(`! ${err.message || err}`);
            this._scanning = false;
            if (fullBtn) fullBtn.disabled = false;
            if (selectedBtn) selectedBtn.disabled = false;
            return;
        }

        const success = !!(finalResult && finalResult.success);
        status.dataset.kind = success ? 'success' : 'error';
        status.textContent = success ? 'Scan complete.' : 'Scan failed -- see output for details.';
        this._scanning = false;
        if (fullBtn) fullBtn.disabled = false;
        if (selectedBtn) selectedBtn.disabled = false;

        if (success) await this._refresh();
    }

    _esc(str) {
        const el = document.createElement('span');
        el.textContent = str == null ? '' : String(str);
        return el.innerHTML;
    }
}

window.DabConfigPanel = DabConfigPanel;

// Lives on the RTL-SDR Plugins page (plugins/apps/rtlsdr/) via the "hook"
// seam, not the built-in Listener page's tabbar -- see dab_panel.js's own
// note for why this moved wholesale instead of being duplicated.
if (typeof window.registerPageHook === 'function') {
    window.registerPageHook({
        host: 'rtlsdr',
        label: 'DAB+ Config',
        make: () => new DabConfigPanel(),
    });
} else {
    console.warn('DAB+ plugin: page hook registry missing');
}
