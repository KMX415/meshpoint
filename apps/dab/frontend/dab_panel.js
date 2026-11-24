/**
 * DAB/DAB+ tab content -- styled like the Radio tab's Digital skin (LEDs,
 * VFD-style readout, scrolling station tag, VU meter, native <audio>
 * controls) so it reads as the same instrument family, then a channel
 * picker and station list below since DAB+ needs a genuinely different
 * model: pick a channel/ensemble first (it carries several stations at
 * once), wait for welle-cli to decode the station list, then pick one --
 * see backend/listener.py.
 */
const _DAB_DONGLE_OWNER_LABELS = {
    radio: 'Radio', p2000: 'P2000', pagers: 'Pagers', pocsag: 'POCSAG', rtl433: 'RTL433', dab: 'DAB+',
    dab_scan: 'DAB+ scan',
};

// How long a favorite/preset click waits for its station to actually show
// up in welle-cli's progressively-decoded list before giving up (see
// _resolvePendingPlay()). Was 30s; live testing on a weaker channel (7D,
// ~9dB SNR vs e.g. 12C's 19dB) showed that's not always enough headroom
// for a cold dongle spin-up + OFDM sync lock + full station-list decode,
// so a click could silently time out even though the station would have
// shown up seconds later.
const _DAB_PENDING_PLAY_TIMEOUT_MS = 60000;

// Full Band III DAB channel raster (5A-13F, 38 channels; ETSI EN 300 401)
// for the manual channel dropdown, alongside the curated presets above --
// This implementation supports Band III only; L-Band is not implemented.
const DAB_ALL_CHANNELS = (() => {
    const channels = [];
    for (let n = 5; n <= 12; n++) {
        for (const letter of ['A', 'B', 'C', 'D']) channels.push(`${n}${letter}`);
    }
    for (const letter of ['A', 'B', 'C', 'D', 'E', 'F']) channels.push(`13${letter}`);
    return channels;
})();

class DabPanel {
    constructor() {
        this._root = null;
        this._statusTimer = null;
        this._playingSid = null;
        this._lastStatus = null;
        this._tuning = false;
        this._nowPlayingTextCache = null;
        // Sub-tabs within the DAB+ tab: 'favorites', 'manual', or a
        // channel code. Starts on Favorites so there's something useful
        // to see immediately rather than an empty tab needing a click.
        this._activeChannelTab = 'favorites';
        // Channel tabs between Favorites and Manual -- loaded from
        // dab_channel_scan.py's JSON output (GET /api/dab/scan-results)
        // instead of a hardcoded list, so they reflect whatever this
        // antenna actually found rather than one location's presets.
        // { channel, name } per entry; name is the DAB+ Config tab's
        // custom_name override when set, else the scanned ensemble label.
        this._channelPresets = [];
        // A favorite tune-and-play jumps to a channel that may not be the
        // one currently running, then has to wait for that specific
        // station's sid to show up in the progressively-decoded services
        // list before it can actually play -- these track that wait.
        this._pendingPlay = null;      // { channel, sid }
        this._pendingPlayAt = 0;
        // Web Audio VU (mirrors ListenerPanel's own graph, duplicated per
        // this repo's small-helper convention rather than importing
        // across js modules -- see telemetry_rail.js's identical note).
        this._audioCtx = null;
        this._analyser = null;
        this._srcNode = null;
        this._vuData = null;
        this._vuRaf = null;
        this._vuLevel = 0;
    }

    mount(root) {
        this._root = root;
        root.innerHTML = `
            <section class="lsn-section">
                <div class="panel lsn-radio">
                    <div class="panel__header">
                        <span>DAB+</span>
                        <div class="lsn-status" id="dab-lsn-status">
                            <span class="lsn-status__dot" data-dab-dot></span>
                            <span data-dab-status-text>idle</span>
                        </div>
                    </div>
                    <div class="panel__body lsn-radio__body">
                        <div class="lsn-display">
                            <div class="lsn-leds">
                                <span class="lsn-badge" title="DAB+ digital radio">DAB+</span>
                                <span class="lsn-led lsn-led--onair" data-dab-onair
                                      title="On air : the receiver is running and streaming"><i></i>ON AIR</span>
                                <span class="lsn-led lsn-led--tune" data-dab-tuning
                                      title="Tuning : switching channel and restarting the receiver"><i></i>TUNING</span>
                            </div>
                            <div class="lsn-freq dab-nowplaying-big">
                                <span class="lsn-station__scroll">
                                    <span class="lsn-station__text lsn-station__text--big" data-dab-nowplayingtext>: : :</span>
                                </span>
                            </div>
                            <div class="lsn-station" data-dab-nowplaying>
                                <span class="lsn-tag lsn-tag--qual" data-dab-snrtag
                                      title="Signal-to-noise ratio"></span>
                                <span class="lsn-tag lsn-tag--pty" data-dab-ptytag
                                      title="Programme type"></span>
                                <span class="lsn-freq__unit dab-chan-tag" data-dab-chantag
                                      title="Channel"></span>
                            </div>
                            <div class="lsn-vu" title="Audio level (real-time)">
                                <span class="lsn-vu__label">VU</span>
                                <div class="lsn-vu__bar" data-dab-vubar></div>
                            </div>
                        </div>
                        <audio id="dab-audio" controls preload="none"></audio>
                    </div>
                </div>
            </section>
            <section class="lsn-section">
                <div class="panel">
                    <div class="panel__header">
                        <span>Channel</span>
                        <button type="button" class="terminal-button" data-dab-stop>Stop</button>
                    </div>
                    <div class="panel__body lsn-panel-body">
                        <div class="lsn-tabbar dab-chantabs" data-dab-chantabs>${this._chanTabsHtml()}</div>
                        <div class="dab-chanhint" data-dab-chanhint style="display:none"></div>
                        <div class="dab-chantab-content" data-dab-chantab-content></div>
                    </div>
                </div>
            </section>
        `;
        this._buildVuSegments();
        root.querySelector('[data-dab-stop]').addEventListener('click', () => this._stopEnsemble());
        root.querySelector('[data-dab-chantabs]').addEventListener('click', (ev) => {
            const btn = ev.target.closest('[data-chantab]');
            if (btn && !btn.disabled) this._switchChannelTab(btn.dataset.chantab);
        });
        root.querySelector('[data-dab-chantab-content]').addEventListener('click', (ev) => {
            const scanBtn = ev.target.closest('[data-dab-scan-channel]');
            if (scanBtn) {
                this._pendingPlay = null;
                this._tune(scanBtn.dataset.dabScanChannel);
                return;
            }
            const favRemoveBtn = ev.target.closest('[data-dab-fav-remove]');
            if (favRemoveBtn) {
                const fav = this._loadFavs()[parseInt(favRemoveBtn.dataset.dabFavRemove, 10)];
                if (fav) this._toggleFav(fav); // already a favorite -> this removes it
                return;
            }
            const favPlayBtn = ev.target.closest('[data-dab-fav-play]');
            if (favPlayBtn) {
                const fav = this._loadFavs()[parseInt(favPlayBtn.dataset.dabFavPlay, 10)];
                if (fav) {
                    const effectiveSid = this._favEffectiveSid(fav);
                    // effectiveSid can be null for a favorite added straight
                    // from the preset list (no sid decoded yet this
                    // session) -- null always means "not playing", never
                    // "playing nothing", so it must never match
                    // this._playingSid's own null/idle state below.
                    if (effectiveSid != null && this._playingSid === effectiveSid) this._playOrStop(effectiveSid);
                    else this._playFavorite(fav);
                }
                return;
            }
            const presetPlayBtn = ev.target.closest('[data-dab-preset-play]');
            if (presetPlayBtn) {
                this._pendingPlay = {
                    channel: presetPlayBtn.dataset.dabPresetChannel,
                    // A sid captured by the scan script (see
                    // dab_channel_scan.py) lets this resolve by
                    // exact identity below instead of the name-normalize
                    // fallback -- null for a station scanned before that
                    // change, or one welle-cli never handed a sid for.
                    sid: presetPlayBtn.dataset.dabPresetSid || null,
                    label: presetPlayBtn.dataset.dabPresetPlay,
                };
                this._pendingPlayAt = Date.now();
                this._tune(presetPlayBtn.dataset.dabPresetChannel);
                return;
            }
            const manualTuneBtn = ev.target.closest('[data-dab-manual-tune]');
            if (manualTuneBtn) {
                const sel = root.querySelector('[data-dab-manual-select]');
                const channel = sel && sel.value;
                if (channel) { this._pendingPlay = null; this._tune(channel); }
                return;
            }
            const favToggle = ev.target.closest('[data-dab-favtoggle]');
            if (favToggle) {
                this._toggleFav({
                    channel: favToggle.dataset.dabChannel,
                    sid: favToggle.dataset.dabSid,
                    label: favToggle.dataset.dabLabel,
                });
                return;
            }
            const playBtn = ev.target.closest('[data-dab-play]');
            if (playBtn) { this._pendingPlay = null; this._playOrStop(playBtn.dataset.dabPlay); }
        });
        this._renderChanTabContent();
        this._loadChannelPresets();
    }

    // Builds the Favorites / <scanned channels> / Manual tabbar markup --
    // used both for the initial mount and to refresh once scan results
    // have loaded, so there's a single source of truth for this markup.
    _chanTabsHtml() {
        const active = this._activeChannelTab;
        const esc = this._esc.bind(this);
        return `
            <button type="button" class="lsn-tabbar__btn${active === 'favorites' ? ' lsn-tabbar__btn--active' : ''}" data-chantab="favorites">★ Favorites</button>
            ${this._channelPresets.map((c) => `
                <button type="button" class="lsn-tabbar__btn${active === c.channel ? ' lsn-tabbar__btn--active' : ''}"
                        data-chantab="${esc(c.channel)}" title="${esc(c.channel)} : ${esc(c.name)}">${esc(c.name)}</button>
            `).join('')}
            <button type="button" class="lsn-tabbar__btn${active === 'manual' ? ' lsn-tabbar__btn--active' : ''}" data-chantab="manual">Manual…</button>
        `;
    }

    // Re-fetched on mount AND every time this tab becomes active (show())
    // -- not continuous polling, but not a one-shot either, so a scan run
    // on the device after the page was first loaded shows up next time
    // this tab is opened instead of being stuck at whatever was true at
    // mount time. A missing/unreadable scan-results file, or one with no
    // channels yet, surfaces a clear hint telling the operator to scan.
    async _loadChannelPresets() {
        let hint = '';
        try {
            const res = await fetch('/api/dab/scan-results');
            if (!res.ok) {
                this._channelPresets = [];
                hint = 'No preset channels found : run a scan from the DAB+ Config tab, then reopen this tab.';
            } else {
                const data = await res.json();
                this._channelPresets = (data.channels || [])
                    .filter((c) => c.ensemble || (c.stations || []).length)
                    .map((c) => ({
                        channel: c.channel,
                        name: c.custom_name || c.ensemble || c.channel,
                        // {name, sid} per station -- sid is the DAB SId
                        // captured by dab_channel_scan.py (may be
                        // null for a station scanned before that existed).
                        // A click here tunes in and resolves by sid when
                        // known, else by name once decoded -- same
                        // wait-and-match idea as a favorite.
                        stations: c.stations || [],
                    }));
                if (!this._channelPresets.length) {
                    hint = 'No preset channels found : run a scan from the DAB+ Config tab, then reopen this tab.';
                }
            }
        } catch (_e) {
            this._channelPresets = [];
            hint = 'No preset channels found : run a scan from the DAB+ Config tab, then reopen this tab.';
        }
        const bar = this._root && this._root.querySelector('[data-dab-chantabs]');
        if (bar) bar.innerHTML = this._chanTabsHtml();
        const hintEl = this._root && this._root.querySelector('[data-dab-chanhint]');
        if (hintEl) {
            hintEl.textContent = hint;
            hintEl.style.display = hint ? '' : 'none';
        }
    }

    /** Switch which sub-tab is shown -- a pure view switch, no tuning side
     * effect. Browsing a channel tab that isn't the one actually running
     * shows a Scan prompt instead of silently interrupting whatever's
     * currently playing; only pressing Scan/Rescan retunes. */
    _switchChannelTab(tab) {
        this._activeChannelTab = tab;
        const root = this._root;
        if (root) {
            root.querySelectorAll('[data-chantab]').forEach((btn) => {
                btn.classList.toggle('lsn-tabbar__btn--active', btn.dataset.chantab === tab);
            });
        }
        this._renderChanTabContent();
    }

    // Renders whichever sub-tab is active into the shared content
    // container -- favorites chips, the manual channel picker, or a
    // channel's station list (only ever one truly "live" at a time,
    // since the dongle can only be tuned to one channel).
    _renderChanTabContent() {
        const el = this._root && this._root.querySelector('[data-dab-chantab-content]');
        if (!el) return;
        const tab = this._activeChannelTab;
        const status = this._lastStatus;
        const busyOwner = status && status.dongle_owner && status.dongle_owner !== 'dab'
            ? status.dongle_owner : null;

        if (tab === 'favorites') {
            el.innerHTML = `<div data-dab-favbar>${this._renderFavBar()}</div>`;
            this._afterStationsRender(el);
            return;
        }

        if (tab === 'manual') {
            // Build the select/button shell only once per tab-switch;
            // poll-driven re-renders (every 2s) only touch the stations
            // sub-container below it, so an open dropdown or in-progress
            // pick survives a status refresh instead of getting wiped by
            // a full innerHTML rebuild.
            let manualEl = el.querySelector('[data-dab-manual]');
            if (!manualEl) {
                el.innerHTML = `
                    <div class="dab-manual" data-dab-manual>
                        <select class="dab-manual__select" data-dab-manual-select title="Manual channel entry">
                            <option value="">Manual channel…</option>
                            ${DAB_ALL_CHANNELS.map((ch) => `<option value="${ch}">${ch}</option>`).join('')}
                        </select>
                        <button type="button" class="terminal-button" data-dab-manual-tune>Tune</button>
                    </div>
                    <div data-dab-manual-stations></div>
                `;
            }
            const sel = el.querySelector('[data-dab-manual-select]');
            const tuneBtn = el.querySelector('[data-dab-manual-tune]');
            if (sel) {
                sel.disabled = !!busyOwner;
                if (document.activeElement !== sel && status && status.running) {
                    sel.value = status.channel || '';
                }
            }
            if (tuneBtn) tuneBtn.disabled = !!busyOwner;
            const stationsEl = el.querySelector('[data-dab-manual-stations]');
            if (stationsEl) {
                stationsEl.innerHTML = this._stationsSectionHtml(status, null);
                this._afterStationsRender(stationsEl);
            }
            return;
        }

        // tab is a channel code
        el.innerHTML = this._stationsSectionHtml(status, tab);
        this._afterStationsRender(el);
    }

    // forChannel: null means "show whatever is currently tuned" (the
    // Manual tab, which has no single channel identity of its own); a
    // channel code means "only show if that's the one actually tuned" --
    // otherwise browsing this tab is safe (no side effect) and shows a
    // Scan prompt instead of silently interrupting the current station.
    _stationsSectionHtml(status, forChannel) {
        const isActiveChannel = !forChannel || (status && status.running && status.channel === forChannel);

        if (forChannel && !isActiveChannel) {
            const preset = this._channelPresets.find((c) => c.channel === forChannel);
            const presetStations = (preset && preset.stations) || [];
            const list = presetStations.length
                ? `<div class="dab-stations" data-dab-stations>${presetStations.map((station) => this._presetStationRowHtml(station, forChannel)).join('')}</div>`
                : '';
            return `
                <div class="dab-scan-prompt">
                    <div class="pager-log__empty">Not currently tuned to ${this._esc(forChannel)}${presetStations.length ? ' : pick a station below to tune in and play it' : ''}.</div>
                    <button type="button" class="terminal-button" data-dab-scan-channel="${this._esc(forChannel)}">Scan ${this._esc(forChannel)}</button>
                    <div class="dab-scan-note">Stops the current station and retunes to this channel.</div>
                </div>
                ${list}
            `;
        }

        if (!status || !status.running) {
            return '<div class="pager-log__empty">Not tuned. Pick a channel above to scan for stations.</div>';
        }

        const rescan = forChannel
            ? `<div class="dab-chan-actions"><button type="button" class="terminal-button" data-dab-scan-channel="${this._esc(forChannel)}">Rescan</button></div>`
            : '';
        const services = status.services || [];
        if (!services.length) {
            // Still decoding -- rather than blanking to just "Scanning…",
            // keep showing the known-from-last-scan names (disabled, no
            // sid to act on yet) so the list doesn't visually empty out
            // for the several seconds welle-cli needs to lock and start
            // handing out real services; each row swaps to the live,
            // clickable one as soon as it actually decodes.
            const preset = status.channel ? this._channelPresets.find((c) => c.channel === status.channel) : null;
            const presetStations = (preset && preset.stations) || [];
            const pending = presetStations.length
                ? `<div class="dab-stations" data-dab-stations>${presetStations.map((station) => this._pendingStationRowHtml(station)).join('')}</div>`
                : '';
            return rescan + '<div class="pager-log__empty">Scanning… stations appear as they decode.</div>' + pending;
        }
        return rescan + `<div class="dab-stations" data-dab-stations>${services.map((s) => this._stationRowHtml(s, status.channel)).join('')}</div>`;
    }

    // Marquee for any label/DLS text that overflows -- mirrors the Radio
    // tab's RDS scroll logic (lsn-station__scroll/.scroll).
    _afterStationsRender(container) {
        container.querySelectorAll('[data-dab-scrolltext]').forEach((textEl) => {
            const scroll = textEl.parentElement;
            const overflow = scroll.scrollWidth - scroll.clientWidth;
            textEl.classList.remove('scroll');
            if (overflow > 8) {
                textEl.style.setProperty('--scroll-dist', `-${overflow + 16}px`);
                textEl.style.setProperty('--scroll-dur', `${Math.min(24, Math.max(6, (overflow + 16) / 22))}s`);
                void textEl.offsetWidth;
                textEl.classList.add('scroll');
            }
        });
    }

    // 32-segment VU bar (green/amber/red zones), same construction as
    // ListenerPanel's DigitalSkin.
    _buildVuSegments() {
        const bar = this._root && this._root.querySelector('[data-dab-vubar]');
        if (!bar) return;
        const n = 32;
        let html = '';
        for (let i = 0; i < n; i++) {
            const zone = i < n * 0.66 ? 'g' : i < n * 0.88 ? 'a' : 'r';
            html += `<span class="lsn-vu__seg" data-zone="${zone}"></span>`;
        }
        bar.innerHTML = html;
    }

    /* ── favorites (channel + station sid, so switching channel and
       playing the right station is one click) ────────────────────── */

    _loadFavs() {
        try { return JSON.parse(localStorage.getItem('meshpoint.dabFavs') || '[]'); }
        catch (_e) { return []; }
    }

    _saveFavs(favs) {
        try { localStorage.setItem('meshpoint.dabFavs', JSON.stringify(favs)); }
        catch (_e) { /* ignore */ }
    }

    // A station picked from a channel's scan-preset list (not yet tuned)
    // has no sid yet, so a favorite added from there is stored with
    // sid: null and matched by name instead -- falls back to a name match
    // whenever either side lacks a sid, so a favorite added before ever
    // tuning is still recognized once decoded live (and vice versa)
    // instead of creating a second, duplicate entry.
    _favMatches(f, channel, sid, label) {
        if (f.channel !== channel) return false;
        if (sid && f.sid && f.sid === sid) return true;
        return this._normalizeLabel(f.label) === this._normalizeLabel(label);
    }

    _isFav(channel, sid, label) {
        return this._loadFavs().some((f) => this._favMatches(f, channel, sid, label));
    }

    // Resolves a favorite's live service entry, if its channel is the one
    // currently tuned and welle-cli has decoded it -- matches by sid when
    // known, else by name (a favorite added from the preset list before
    // ever tuning starts life with sid: null).
    _favLiveService(fav) {
        const status = this._lastStatus;
        if (!status || !status.running || status.channel !== fav.channel) return null;
        return (status.services || []).find((s) => (
            fav.sid ? s.sid === fav.sid : this._normalizeLabel(s.label) === this._normalizeLabel(fav.label)
        )) || null;
    }

    // The sid to actually act on for this favorite right now: the live-
    // decoded one if its channel is tuned and it's shown up, else
    // whatever was stored (a real sid for an older favorite, or null for
    // one added straight from the preset list and not yet decoded this
    // session -- callers must treat null as "not currently playing",
    // never compare it directly against this._playingSid's own idle null).
    _favEffectiveSid(fav) {
        const live = this._favLiveService(fav);
        return live ? live.sid : fav.sid;
    }

    _toggleFav({ channel, sid, label }) {
        const favs = this._loadFavs();
        const idx = favs.findIndex((f) => this._favMatches(f, channel, sid, label));
        if (idx >= 0) favs.splice(idx, 1);
        else favs.push({ channel, sid: sid || null, label });
        this._saveFavs(favs);
        const bar = this._root && this._root.querySelector('[data-dab-favbar]');
        if (bar) bar.innerHTML = this._renderFavBar();
        this._repaintStationButtons();
    }

    _renderFavBar() {
        const favs = this._loadFavs();
        if (!favs.length) {
            return '<div class="pager-log__empty">No favorites yet : click the ☆ on any station to pin it here.</div>';
        }
        return `<div class="dab-stations">${favs.map((f, i) => this._favRowHtml(f, i)).join('')}</div>`;
    }

    // Same row shape as a channel tab's station list (star, scrolling
    // text, Play/Stop) so Favorites reads as just another station list
    // instead of a different-looking chip grid. A favorite only stores
    // {channel, sid, label} in localStorage -- no RadioText/DLS, since
    // that changes constantly and can't be saved statically -- but if
    // this favorite happens to be on the channel currently tuned, its
    // live label+DLS is already sitting in status.services, same data
    // a channel tab's own station row uses.
    _favRowHtml(f, i) {
        const esc = this._esc.bind(this);
        const live = this._favLiveService(f);
        // A favorite added before ever tuning has no sid, so "is this the
        // one currently playing" has to go through the live-resolved sid
        // once it's found, not the (possibly still null) stored one.
        const effectiveSid = live ? live.sid : f.sid;
        const playing = effectiveSid != null && this._playingSid === effectiveSid;
        const label = live ? live.label : f.label;
        const dls = live ? live.dls : '';
        const text = (dls && dls !== label) ? `${f.channel} · ${label} : ${dls}` : `${f.channel} · ${label}`;
        return `
            <div class="dab-station-row">
                <span class="lsn-fav on" data-dab-fav-remove="${i}" title="Remove favorite">★</span>
                <span class="lsn-station__scroll dab-station-row__text">
                    <span class="lsn-station__text" data-dab-scrolltext>${esc(text)}</span>
                </span>
                <button type="button" class="terminal-button${playing ? ' dab-station-row__playing' : ''}"
                        data-dab-fav-play="${i}">${playing ? 'Stop' : 'Play'}</button>
            </div>
        `;
    }

    /** Jump straight to a favorite: tune its channel if not already there
     * (or the station isn't decoded yet), then auto-play the moment its
     * sid shows up in the progressively-filled station list. */
    async _playFavorite(fav) {
        // Switch the view to this favorite's channel tab so its station
        // list (and the played station's Stop state) is actually visible,
        // rather than leaving the user looking at the Favorites tab while
        // a different channel tunes in the background.
        this._activeChannelTab = fav.channel;
        const root = this._root;
        if (root) {
            root.querySelectorAll('[data-chantab]').forEach((btn) => {
                btn.classList.toggle('lsn-tabbar__btn--active', btn.dataset.chantab === fav.channel);
            });
        }
        const st = this._lastStatus;
        if (st && st.running && st.channel === fav.channel) {
            const found = this._favLiveService(fav);
            if (found) { this._playOrStop(found.sid); return; }
            this._renderChanTabContent();
            return;
        }
        this._pendingPlay = { channel: fav.channel, sid: fav.sid, label: fav.label };
        this._pendingPlayAt = Date.now();
        await this._tune(fav.channel);
    }

    show() {
        this._refresh();
        this._loadChannelPresets();
        this._statusTimer = setInterval(() => this._refresh(), 2000);
    }

    hide() {
        clearInterval(this._statusTimer);
        this._statusTimer = null;
    }

    /** Public: what THIS browser tab is currently playing, if anything --
     * for SidebarTelemetryRail's mini-player, which has no reason to
     * duplicate DAB's own on-demand station-selection state (unlike FM,
     * "tuned" and "what's playing" aren't the same thing here). */
    getNowPlaying() {
        if (!this._playingSid || !this._lastStatus) return null;
        const svc = (this._lastStatus.services || []).find((s) => s.sid === this._playingSid);
        if (!svc) return null;
        return { label: svc.label, dls: svc.dls || '' };
    }

    /** Public: stop from outside this tab (e.g. the sidebar mini-player's
     * Stop button) -- tears down the ensemble and clears local playback
     * state exactly like the tab's own Stop button. */
    stopFromSidebar() {
        this._stopEnsemble();
    }

    async _tune(channel) {
        this._tuning = true;
        this._setLeds({ onair: false, tuning: true });
        this._setStatus(false, `tuning ${channel}…`);
        try {
            const r = await fetch('/api/dab/tune', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ channel }),
            });
            if (!r.ok) {
                const detail = (await r.json().catch(() => ({}))).detail;
                this._tuning = false;
                this._setLeds({ onair: false, tuning: false });
                this._setStatus(false, detail || `tune failed (${r.status})`);
                return;
            }
            this._tuning = false;
            this._render(await r.json());
        } catch (err) {
            this._tuning = false;
            this._setLeds({ onair: false, tuning: false });
            this._setStatus(false, 'tune request failed');
        }
    }

    async _stopEnsemble() {
        this._stopAudio();
        try {
            const r = await fetch('/api/dab/stop', { method: 'POST' });
            if (r.ok) this._render(await r.json());
        } catch (_e) { /* poll catches up */ }
    }

    _playOrStop(sid) {
        const audio = document.getElementById('dab-audio');
        if (!audio) return;
        if (this._playingSid === sid) {
            this._stopAudio();
        } else {
            audio.src = `/api/dab/stream/${encodeURIComponent(sid)}?t=${Date.now()}`;
            audio.play().catch(() => { /* user gesture (click) already present */ });
            this._playingSid = sid;
            if (this._ensureAudioGraph()) this._startVuLoop();
        }
        this._repaintStationButtons();
        this._renderNowPlaying(this._lastStatus);
    }

    _stopAudio() {
        const audio = document.getElementById('dab-audio');
        if (audio) { audio.pause(); audio.removeAttribute('src'); }
        this._playingSid = null;
        this._stopVuLoop();
    }

    _ensureAudioGraph() {
        const audio = document.getElementById('dab-audio');
        if (!audio) return false;
        try {
            if (!this._audioCtx) {
                const AC = window.AudioContext || window.webkitAudioContext;
                if (!AC) return false;
                this._audioCtx = new AC();
            }
            if (!this._srcNode) {
                this._srcNode = this._audioCtx.createMediaElementSource(audio);
                this._analyser = this._audioCtx.createAnalyser();
                this._analyser.fftSize = 1024;
                this._vuData = new Uint8Array(this._analyser.fftSize);
                this._srcNode.connect(this._analyser);
                this._analyser.connect(this._audioCtx.destination);
            }
            if (this._audioCtx.state === 'suspended') this._audioCtx.resume();
            return true;
        } catch (_e) {
            return false;
        }
    }

    _startVuLoop() {
        if (this._vuRaf || !this._analyser) return;
        const tick = () => {
            this._analyser.getByteTimeDomainData(this._vuData);
            let sum = 0;
            for (let i = 0; i < this._vuData.length; i++) {
                const x = (this._vuData[i] - 128) / 128;
                sum += x * x;
            }
            const rms = Math.sqrt(sum / this._vuData.length);
            const db = 20 * Math.log10(rms + 1e-6);
            const lvl = Math.max(0, Math.min(100, (db + 50) / 47 * 100));
            this._vuLevel = this._vuLevel * 0.4 + lvl * 0.6;
            this._setVu(this._vuLevel);
            this._vuRaf = requestAnimationFrame(tick);
        };
        this._vuRaf = requestAnimationFrame(tick);
    }

    _stopVuLoop() {
        if (this._vuRaf) cancelAnimationFrame(this._vuRaf);
        this._vuRaf = null;
        this._vuLevel = 0;
        this._setVu(0);
    }

    _setVu(level) {
        const bar = this._root && this._root.querySelector('[data-dab-vubar]');
        if (!bar) return;
        const segs = bar.children;
        const n = segs.length;
        const lit = Math.max(0, Math.min(n, Math.round((level / 100) * n)));
        for (let i = 0; i < n; i++) segs[i].classList.toggle('on', i < lit);
    }

    async _refresh() {
        try {
            const r = await fetch('/api/dab/status');
            if (!r.ok) return;
            this._render(await r.json());
        } catch (_e) { /* transient network hiccup -- next poll retries */ }
    }

    _render(status) {
        const root = this._root;
        if (!root) return;
        this._lastStatus = status;
        const busyOwner = (status.dongle_owner && status.dongle_owner !== 'dab') ? status.dongle_owner : null;

        root.querySelectorAll('[data-chantab]').forEach((btn) => {
            const isChannelCode = this._channelPresets.some((c) => c.channel === btn.dataset.chantab);
            if (isChannelCode) btn.disabled = !!busyOwner;
        });

        this._setLeds({ onair: status.running, tuning: this._tuning });

        // Small tag shows channel + a friendly name -- the scanned/custom
        // name from this._channelPresets (itself sourced from GET
        // /api/dab/scan-results, custom_name preferred over the raw
        // ensemble label) if this is a known channel, else whatever real
        // ensemble label welle-cli decoded live. The big VFD slot is
        // reserved for the now-playing station/RadioText instead -- that
        // space was originally sized for the Radio tab's frequency
        // digits, but a station name matters more to a listener here
        // than which channel it happens to be on.
        const chanTagEl = root.querySelector('[data-dab-chantag]');
        if (chanTagEl) {
            if (!status.running) {
                chanTagEl.textContent = '';
            } else {
                const preset = this._channelPresets.find((c) => c.channel === status.channel);
                const name = preset ? preset.name : status.ensemble_label;
                chanTagEl.textContent = name ? `${status.channel} · ${name}` : (status.channel || '');
            }
        }

        if (status.running) {
            this._setStatus(true, `tuned to ${status.channel}`);
        } else if (busyOwner) {
            this._setStatus(false, `busy : in use by ${_DAB_DONGLE_OWNER_LABELS[busyOwner] || busyOwner}`, true);
            this._stopAudio();
        } else if (status.last_error) {
            this._setStatus(false, `idle : ${status.last_error}`);
            this._stopAudio();
        } else {
            this._setStatus(false, 'idle');
            this._stopAudio();
        }

        this._renderNowPlaying(status);
        this._renderChanTabContent();
        this._resolvePendingPlay(status);
    }

    // Drives the big VFD "now playing" headline + SNR/PTY pills from
    // whichever station this browser session picked (this._playingSid) --
    // a purely client-side concept, since welle-cli can serve several
    // browser clients different stations from the same tuned ensemble at
    // once (unlike FM, where "tuned" and "what's playing" are the same
    // thing server-side).
    _renderNowPlaying(status) {
        const root = this._root;
        if (!root || !status) return;
        const snrEl = root.querySelector('[data-dab-snrtag]');
        const ptyEl = root.querySelector('[data-dab-ptytag]');
        const textEl = root.querySelector('[data-dab-nowplayingtext]');
        if (!textEl) return;

        const playing = this._playingSid
            && (status.services || []).find((s) => s.sid === this._playingSid);

        if (snrEl) {
            if (status.running && typeof status.snr === 'number') {
                snrEl.style.display = '';
                snrEl.textContent = `${status.snr.toFixed(1)} dB`;
                snrEl.classList.remove('q-good', 'q-mid', 'q-bad');
                snrEl.classList.add(status.snr >= 12 ? 'q-good' : status.snr >= 6 ? 'q-mid' : 'q-bad');
            } else {
                snrEl.style.display = 'none';
            }
        }
        if (ptyEl) {
            const pty = playing ? (playing.pty || '').trim() : '';
            ptyEl.style.display = pty ? '' : 'none';
            ptyEl.textContent = pty;
        }

        let text;
        if (playing) {
            text = (playing.dls && playing.dls !== playing.label)
                ? `${playing.label} : ${playing.dls}` : playing.label;
        } else if (this._pendingPlay && this._pendingPlay.channel === status.channel) {
            // A favorite click is waiting on this channel's station list to
            // decode its target sid/label (see _resolvePendingPlay) -- say
            // so, instead of the generic "select a station below" prompt,
            // which reads as if nothing was chosen when a specific station
            // is in fact already queued up.
            text = `finding ${this._pendingPlay.label}…`;
        } else if (status.running) {
            text = 'select a station below';
        } else {
            text = ': : :';
        }
        this._setNowPlayingText(text);
    }

    // Marquee for now-playing text, same measure/toggle approach as
    // ListenerPanel's setStation().
    _setNowPlayingText(text) {
        const textEl = this._root && this._root.querySelector('[data-dab-nowplayingtext]');
        if (!textEl || this._nowPlayingTextCache === text) return;
        this._nowPlayingTextCache = text;
        textEl.textContent = text;
        const scroll = textEl.parentElement;
        const overflow = scroll.scrollWidth - scroll.clientWidth;
        textEl.classList.remove('scroll');
        if (overflow > 8) {
            textEl.style.setProperty('--scroll-dist', `-${overflow + 16}px`);
            textEl.style.setProperty('--scroll-dur', `${Math.min(24, Math.max(6, (overflow + 16) / 22))}s`);
            void textEl.offsetWidth;
            textEl.classList.add('scroll');
        } else {
            textEl.style.removeProperty('--scroll-dist');
            textEl.style.removeProperty('--scroll-dur');
        }
    }

    _setLeds({ onair, tuning }) {
        const root = this._root;
        if (!root) return;
        const onairEl = root.querySelector('[data-dab-onair]');
        const tuneEl = root.querySelector('[data-dab-tuning]');
        if (onairEl) onairEl.classList.toggle('on', !!onair);
        if (tuneEl) tuneEl.classList.toggle('on', !!tuning);
    }

    /** If a favorite (or scan-preset station) jump is waiting on a channel
     * switch, check whether its sid has shown up in the (progressively-
     * decoded) station list yet; give up after _DAB_PENDING_PLAY_TIMEOUT_MS
     * (channel might genuinely not carry that station anymore, or be too
     * weak to lock in time) rather than waiting forever. A preset station
     * scanned before sid-capture existed (or one welle-cli didn't report a
     * sid for) has no sid -- matched by name instead, case/whitespace-
     * insensitive. */
    _resolvePendingPlay(status) {
        const pending = this._pendingPlay;
        if (!pending) return;
        if (!status.running || status.channel !== pending.channel) {
            if (Date.now() - this._pendingPlayAt > _DAB_PENDING_PLAY_TIMEOUT_MS) this._pendingPlay = null;
            return;
        }
        const found = (status.services || []).find((s) => (
            pending.sid ? s.sid === pending.sid : this._normalizeLabel(s.label) === this._normalizeLabel(pending.label)
        ));
        if (found) {
            this._pendingPlay = null;
            this._playOrStop(found.sid);
        } else if (Date.now() - this._pendingPlayAt > _DAB_PENDING_PLAY_TIMEOUT_MS) {
            this._pendingPlay = null;
            this._setStatus(true, `tuned to ${status.channel} : station not found`);
        }
    }

    _normalizeLabel(label) {
        return (label || '').trim().toLowerCase();
    }

    _stationRowHtml(s, channel) {
        const esc = this._esc.bind(this);
        const playing = this._playingSid === s.sid;
        const isFav = this._isFav(channel, s.sid, s.label);
        const text = (s.dls && s.dls !== s.label) ? `${s.label} : ${s.dls}` : s.label;
        return `
            <div class="dab-station-row">
                <span class="lsn-fav${isFav ? ' on' : ''}" data-dab-favtoggle title="Favorite"
                      data-dab-channel="${esc(channel)}" data-dab-sid="${esc(s.sid)}" data-dab-label="${esc(s.label)}">
                    ${isFav ? '★' : '☆'}
                </span>
                <span class="lsn-station__scroll dab-station-row__text">
                    <span class="lsn-station__text" data-dab-scrolltext>${esc(text)}</span>
                </span>
                <button type="button" class="terminal-button${playing ? ' dab-station-row__playing' : ''}"
                        data-dab-play="${esc(s.sid)}">${playing ? 'Stop' : 'Play'}</button>
            </div>
        `;
    }

    // A station known from the last scan, on a channel not currently
    // tuned. `station` is {name, sid} -- sid is the DAB SId captured by
    // dab_channel_scan.py (broadcaster-assigned, stable across
    // scans/days), so favoriting/playing from here can match by exact
    // identity below instead of only the name-normalize fallback (still
    // used for a station scanned before sid capture existed, or one
    // welle-cli didn't report a sid for). Play has no Stop state to
    // reflect since nothing on this channel can be playing yet.
    _presetStationRowHtml(station, channel) {
        const esc = this._esc.bind(this);
        const { name, sid } = station;
        const isFav = this._isFav(channel, sid, name);
        return `
            <div class="dab-station-row">
                <span class="lsn-fav${isFav ? ' on' : ''}" data-dab-favtoggle title="Favorite"
                      data-dab-channel="${esc(channel)}" data-dab-sid="${esc(sid || '')}" data-dab-label="${esc(name)}">
                    ${isFav ? '★' : '☆'}
                </span>
                <span class="lsn-station__scroll dab-station-row__text">
                    <span class="lsn-station__text" data-dab-scrolltext>${esc(name)}</span>
                </span>
                <button type="button" class="terminal-button"
                        data-dab-preset-play="${esc(name)}" data-dab-preset-channel="${esc(channel)}"
                        data-dab-preset-sid="${esc(sid || '')}">Play</button>
            </div>
        `;
    }

    // A known-from-last-scan station shown while the channel is tuned but
    // welle-cli hasn't decoded it (back) yet -- purely a placeholder, so
    // no star/Play interactivity, just a dimmed row that gets replaced by
    // the real, clickable one once it actually decodes. `station` is
    // {name, sid} -- sid unused here, display-only row.
    _pendingStationRowHtml(station) {
        const esc = this._esc.bind(this);
        return `
            <div class="dab-station-row dab-station-row--pending">
                <span class="lsn-station__scroll dab-station-row__text">
                    <span class="lsn-station__text" data-dab-scrolltext>${esc(station.name)}</span>
                </span>
                <button type="button" class="terminal-button" disabled>Play</button>
            </div>
        `;
    }

    _repaintStationButtons() {
        const el = this._root && this._root.querySelector('[data-dab-stations]');
        if (el) {
            el.querySelectorAll('[data-dab-play]').forEach((btn) => {
                const playing = this._playingSid === btn.dataset.dabPlay;
                btn.textContent = playing ? 'Stop' : 'Play';
                btn.classList.toggle('dab-station-row__playing', playing);
            });
            el.querySelectorAll('[data-dab-favtoggle]').forEach((star) => {
                const isFav = this._isFav(star.dataset.dabChannel, star.dataset.dabSid, star.dataset.dabLabel);
                star.textContent = isFav ? '★' : '☆';
                star.classList.toggle('on', isFav);
            });
        }
        // Favorites tab's own Play/Stop buttons -- same playingSid check,
        // different markup/attributes (data-dab-fav-play, not
        // data-dab-play), so it needs its own pass.
        const favBar = this._root && this._root.querySelector('[data-dab-favbar]');
        if (favBar) {
            favBar.querySelectorAll('[data-dab-fav-play]').forEach((btn) => {
                const fav = this._loadFavs()[parseInt(btn.dataset.dabFavPlay, 10)];
                if (!fav) return;
                const effectiveSid = this._favEffectiveSid(fav);
                const playing = effectiveSid != null && this._playingSid === effectiveSid;
                btn.textContent = playing ? 'Stop' : 'Play';
                btn.classList.toggle('dab-station-row__playing', playing);
            });
        }
    }

    _setStatus(running, text, busy = false) {
        const dot = this._root && this._root.querySelector('[data-dab-dot]');
        const label = this._root && this._root.querySelector('[data-dab-status-text]');
        if (dot) {
            dot.classList.toggle('lsn-status__dot--on', !!running);
            dot.classList.toggle('lsn-status__dot--busy', !!busy);
        }
        if (label) label.textContent = text;
    }

    _esc(str) {
        const el = document.createElement('span');
        el.textContent = str == null ? '' : String(str);
        return el.innerHTML;
    }
}

window.DabPanel = DabPanel;

// Lives on the RTL-SDR Plugins page (plugins/apps/rtlsdr/) via the "hook"
// seam, not the built-in Listener page's tabbar -- moved wholesale rather
// than duplicated, since dab-audio (the <audio> element id below) is
// looked up via a global document.getElementById, not scoped to this
// panel's own root; two live instances at once would fight over it.
if (typeof window.registerPageHook === 'function') {
    window.registerPageHook({
        host: 'rtlsdr',
        label: 'DAB+',
        make: () => {
            const panel = new DabPanel();
            // Exposed for SidebarTelemetryRail's mini-player
            // (getNowPlaying()/stopFromSidebar()) -- previously set by the
            // Listener page's own shell when DAB+ was one of its tabs.
            window.dabPanel = panel;
            return panel;
        },
    });
} else {
    console.warn('DAB+ plugin: page hook registry missing');
}
