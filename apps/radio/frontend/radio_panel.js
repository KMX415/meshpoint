/**
 * Radio -- FM/AM/SSB broadcast & utility radio listener.
 *
 * Architecture: one shared CONTROLLER (state, tune/stop, status poll, RDS,
 * Web Audio VU) drives a swappable DISPLAY SKIN. Two skins implement the same
 * interface { mount, setFreq, setMode, setLeds, setStation, setRdsQual, setVu,
 * reset }: DigitalSkin (VFD-style readout + segmented VU) and AnalogueSkin
 * (slide-rule dial + swinging needle VU). The <audio> element lives in the
 * shell (not a skin) so the Web Audio graph survives skin switches.
 *
 * Lives on the RTL-SDR Plugins page (plugins/apps/rtlsdr/) via the "hook"
 * seam, not a built-in Listener page -- that page no longer exists. Radio
 * was the last RTL-SDR listener still built into core; this plugin closes
 * out that migration (see plugins/apps/rtlsdr/README.md for the full
 * history: DAB+ moved first and proved the mechanism/found two real bugs
 * in it, then Pagers/POCSAG/P2000/RTL433/ACARS/ADS-B followed).
 *
 * Unlike those, `mount(rootEl)` here builds its DOM eagerly and every
 * element lookup is scoped to `this._root` (`this._root.querySelector`),
 * not `document.getElementById` -- the original built-in version used
 * bare ids since there was only ever one Listener page in the whole app;
 * scoping properly here costs nothing and matches how every other
 * migrated panel already works.
 */

function fmtFreq4(mhz) {
    return Number.isFinite(mhz) ? mhz.toFixed(4) : '--.----';
}

/* ───────────────────────── Digital skin ───────────────────────── */

class DigitalSkin {
    constructor() {
        this._stationTextCache = null;
        this._vuPeak = 0;
        this._vuLast = 0;
    }

    mount(container) {
        container.innerHTML = `
            <div class="lsn-leds">
                <span class="lsn-badge" data-mode
                      title="Demodulation mode : WFM (wide FM/broadcast), NFM (narrow FM), AM, USB, LSB">:</span>
                <span class="lsn-led lsn-led--onair" data-onair
                      title="On air : the receiver is running and streaming live audio"><i></i>ON AIR</span>
                <span class="lsn-led lsn-led--tune" data-tuning
                      title="Tuning : switching frequency and restarting the receiver"><i></i>TUNING</span>
            </div>
            <div class="lsn-freq">
                <span class="lsn-freq__num" data-freq>--.----</span>
                <span class="lsn-freq__unit">MHz</span>
            </div>
            <div class="lsn-station" data-station>
                <span class="lsn-tag lsn-tag--rds" data-rdstag
                      title="RDS : Radio Data System: digital station info carried on the FM signal">RDS</span>
                <span class="lsn-tag lsn-tag--qual" data-qual
                      title="RDS signal quality : 100 minus the block error rate (higher = cleaner reception)"></span>
                <span class="lsn-tag lsn-tag--pty" data-pty
                      title="Program Type (RDS) : the station's content category, e.g. Pop Music, News, Sport"></span>
                <span class="lsn-station__scroll">
                    <span class="lsn-station__text" data-stationtext>: : :</span>
                </span>
            </div>
            <div class="lsn-vu" title="Audio level (real-time, post-demod)">
                <span class="lsn-vu__label">VU</span>
                <div class="lsn-vu__bar" data-vubar></div>
            </div>
        `;
        const q = (s) => container.querySelector(s);
        this._el = {
            mode: q('[data-mode]'), onair: q('[data-onair]'), tune: q('[data-tuning]'),
            freq: q('[data-freq]'), station: q('[data-station]'),
            stationText: q('[data-stationtext]'), rdsTag: q('[data-rdstag]'),
            qual: q('[data-qual]'), pty: q('[data-pty]'), vubar: q('[data-vubar]'),
        };
        // Build 32 VU segments (green/amber/red zones).
        const N = 32;
        let html = '';
        for (let i = 0; i < N; i++) {
            const zone = i < N * 0.66 ? 'g' : i < N * 0.88 ? 'a' : 'r';
            html += `<span class="lsn-vu__seg" data-zone="${zone}"></span>`;
        }
        this._el.vubar.innerHTML = html;
        this._stationTextCache = null;
    }

    setFreq(freq) { this._el.freq.textContent = fmtFreq4(freq); }
    setMode(mode) { if (mode) this._el.mode.textContent = String(mode).toUpperCase(); }

    setLeds({ onair, tuning }) {
        this._el.onair.classList.toggle('on', !!onair);
        this._el.tune.classList.toggle('on', !!tuning);
    }

    setRdsQual(bler, running) {
        const el = this._el.qual;
        if (!running || typeof bler !== 'number' || bler < 0) { el.style.display = 'none'; return; }
        const qual = Math.max(0, Math.min(100, Math.round(100 - bler)));
        el.style.display = '';
        el.textContent = `${qual}%`;
        el.classList.remove('q-good', 'q-mid', 'q-bad');
        el.classList.add(qual >= 90 ? 'q-good' : qual >= 70 ? 'q-mid' : 'q-bad');
    }

    setStation(text, { rds = false, pty = '' } = {}) {
        this._el.rdsTag.style.display = rds ? '' : 'none';
        const p = (pty || '').trim();
        this._el.pty.style.display = (rds && p) ? '' : 'none';
        this._el.pty.textContent = p;
        this._el.station.classList.toggle('lsn-station--rds', !!rds);

        if (this._stationTextCache === text) return;
        this._stationTextCache = text;
        const textEl = this._el.stationText;
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

    setVu(level) {
        const segs = this._el.vubar.children;
        const n = segs.length;
        const lit = Math.max(0, Math.min(n, Math.round((level / 100) * n)));
        const now = performance.now();
        const dt = this._vuLast ? (now - this._vuLast) / 1000 : 0;
        this._vuLast = now;
        this._vuPeak = Math.max(lit, this._vuPeak - dt * 14);
        const peakSeg = Math.round(this._vuPeak);
        for (let i = 0; i < n; i++) {
            segs[i].classList.toggle('on', i < lit);
            segs[i].classList.toggle('peak', (i === peakSeg - 1) && peakSeg > lit);
        }
    }

    reset() {
        this.setLeds({ onair: false, tuning: false });
        this.setRdsQual(-1, false);
        this.setStation(': : :', {});
        this.setVu(0);
    }
}

/* ───────────────────────── Analogue skin ──────────────────────── */

class AnalogueSkin {
    static get BANDS() {
        return [
            { min: 76, max: 108, step: 0.5, labelStep: 2, name: 'FM' },
            { min: 108, max: 137, step: 1, labelStep: 5, name: 'AIR' },
            { min: 144, max: 148, step: 0.25, labelStep: 1, name: '144-148 MHz' },
            { min: 156, max: 163, step: 0.5, labelStep: 2, name: 'MARINE' },
            { min: 420, max: 450, step: 1, labelStep: 5, name: '420-450 MHz' },
        ];
    }

    mount(container) {
        container.innerHTML = `
            <div class="lsn-ana">
                <div class="lsn-leds">
                    <span class="lsn-badge" data-mode
                          title="Demodulation mode">:</span>
                    <span class="lsn-led lsn-led--onair" data-onair title="On air"><i></i>ON AIR</span>
                    <span class="lsn-led lsn-led--tune" data-tuning title="Tuning"><i></i>TUNING</span>
                    <span class="lsn-ana__band" data-band></span>
                </div>
                <div class="lsn-ana__dial">
                    <div class="lsn-ana__scale" data-scale></div>
                    <div class="lsn-ana__needle" data-needle></div>
                </div>
                <div class="lsn-ana__row">
                    <div class="lsn-ana__vu" title="Audio level (real-time)">
                        ${AnalogueSkin._vuGaugeMarkup()}
                        <span class="lsn-ana__vulabel">VU</span>
                    </div>
                    <div class="lsn-station lsn-ana__display" data-station>
                        <div class="lsn-ana__tags">
                            <span class="lsn-tag lsn-tag--rds" data-rdstag title="RDS">RDS</span>
                            <span class="lsn-tag lsn-tag--qual" data-qual title="RDS signal quality"></span>
                            <span class="lsn-tag lsn-tag--pty" data-pty title="Program Type"></span>
                        </div>
                        <span class="lsn-station__scroll">
                            <span class="lsn-station__text" data-stationtext>: : :</span>
                        </span>
                        <div class="lsn-ana__freq"><span data-freq>--.----</span> <em>MHz</em></div>
                    </div>
                </div>
            </div>
        `;
        const q = (s) => container.querySelector(s);
        this._el = {
            mode: q('[data-mode]'), onair: q('[data-onair]'), tune: q('[data-tuning]'),
            band: q('[data-band]'), scale: q('[data-scale]'), needle: q('[data-needle]'),
            freq: q('[data-freq]'), vuNeedle: q('[data-vuneedle]'),
            station: q('[data-station]'), stationText: q('[data-stationtext]'),
            rdsTag: q('[data-rdstag]'), qual: q('[data-qual]'), pty: q('[data-pty]'),
        };
        this._curBand = null;
        this._stationTextCache = null;
    }

    _bandFor(freq) {
        for (const b of AnalogueSkin.BANDS) if (freq >= b.min && freq <= b.max) return b;
        return { min: freq - 1, max: freq + 1, step: 0.2, labelStep: 0.5, name: '' };
    }

    // Swinging-needle VU gauge as an SVG: green/yellow/red arc + ticks +
    // needle. Pivot (70,64); needle sweeps -52°..+52° for level 0..100.
    static _vuGaugeMarkup() {
        const cx = 70, cy = 64, r = 52;
        const A0 = -52, A1 = 52, gEnd = 12, yEnd = 34;
        const pt = (deg, rr) => {
            const a = deg * Math.PI / 180;
            return [cx + rr * Math.sin(a), cy - rr * Math.cos(a)];
        };
        const arc = (a, b) => {
            const [x1, y1] = pt(a, r), [x2, y2] = pt(b, r);
            return `M ${x1.toFixed(1)} ${y1.toFixed(1)} A ${r} ${r} 0 0 1 ${x2.toFixed(1)} ${y2.toFixed(1)}`;
        };
        let ticks = '';
        for (let d = A0; d <= A1 + 0.1; d += 13) {
            const [x1, y1] = pt(d, r - 5), [x2, y2] = pt(d, r + 1);
            ticks += `<line x1="${x1.toFixed(1)}" y1="${y1.toFixed(1)}" x2="${x2.toFixed(1)}" y2="${y2.toFixed(1)}" class="lsn-ana__vutick"/>`;
        }
        const nyTop = (cy - (r - 6)).toFixed(1);  // needle drawn straight up
        return `
            <svg viewBox="0 0 140 74" class="lsn-ana__vusvg">
                <path class="vz vz-g" d="${arc(A0, gEnd)}"/>
                <path class="vz vz-y" d="${arc(gEnd, yEnd)}"/>
                <path class="vz vz-r" d="${arc(yEnd, A1)}"/>
                <g>${ticks}</g>
                <line class="lsn-ana__vuneedle" data-vuneedle
                      x1="${cx}" y1="${cy}" x2="${cx}" y2="${nyTop}"
                      transform="rotate(${A0} ${cx} ${cy})"/>
                <circle class="lsn-ana__vuhub" cx="${cx}" cy="${cy}" r="3.5"/>
            </svg>`;
    }

    _renderScale(band) {
        const span = band.max - band.min;
        let html = '';
        const nTicks = Math.round(span / band.step);
        for (let i = 0; i <= nTicks; i++) {
            const pos = (i * band.step / span) * 100;
            html += `<div class="lsn-ana__tick" style="left:${pos}%"></div>`;
        }
        const nLab = Math.round(span / band.labelStep);
        for (let i = 0; i <= nLab; i++) {
            const t = band.min + i * band.labelStep;
            const pos = ((t - band.min) / span) * 100;
            const txt = band.labelStep < 1 ? t.toFixed(1) : Math.round(t);
            html += `<div class="lsn-ana__tick major" style="left:${pos}%"></div>`;
            html += `<div class="lsn-ana__tlabel" style="left:${pos}%">${txt}</div>`;
        }
        // Preset flags: any preset frequency that falls inside this band.
        for (const g of RadioPanel.PRESET_GROUPS) {
            for (const [label, freq] of g.items) {
                if (freq >= band.min && freq <= band.max) {
                    const pos = ((freq - band.min) / span) * 100;
                    html += `<div class="lsn-ana__flag" style="left:${pos}%"`
                          + ` title="${label} · ${freq} MHz"></div>`;
                }
            }
        }
        this._el.scale.innerHTML = html;
        this._el.band.textContent = band.name;
    }

    setFreq(freq) {
        this._el.freq.textContent = fmtFreq4(freq);
        if (!Number.isFinite(freq)) return;
        const band = this._bandFor(freq);
        if (!this._curBand || band.min !== this._curBand.min || band.max !== this._curBand.max) {
            this._renderScale(band);
            this._curBand = band;
        }
        const pos = Math.max(0, Math.min(1, (freq - band.min) / (band.max - band.min))) * 100;
        this._el.needle.style.left = pos + '%';
    }

    setMode(mode) { if (mode) this._el.mode.textContent = String(mode).toUpperCase(); }

    setLeds({ onair, tuning }) {
        this._el.onair.classList.toggle('on', !!onair);
        this._el.tune.classList.toggle('on', !!tuning);
    }

    setRdsQual(bler, running) {
        const el = this._el.qual;
        const locked = running && typeof bler === 'number' && bler >= 0 && (100 - bler) >= 80;
        // Tuning-lock feel: the dial pointer greens up on a clean RDS lock.
        this._el.needle.classList.toggle('locked', locked);
        if (!running || typeof bler !== 'number' || bler < 0) { el.style.display = 'none'; return; }
        const qual = Math.max(0, Math.min(100, Math.round(100 - bler)));
        el.style.display = '';
        el.textContent = `${qual}%`;
        el.classList.remove('q-good', 'q-mid', 'q-bad');
        el.classList.add(qual >= 90 ? 'q-good' : qual >= 70 ? 'q-mid' : 'q-bad');
    }

    setStation(text, { rds = false, pty = '' } = {}) {
        this._el.rdsTag.style.display = rds ? '' : 'none';
        const p = (pty || '').trim();
        this._el.pty.style.display = (rds && p) ? '' : 'none';
        this._el.pty.textContent = p;
        this._el.station.classList.toggle('lsn-station--rds', !!rds);
        if (this._stationTextCache === text) return;
        this._stationTextCache = text;
        const textEl = this._el.stationText;
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

    setVu(level) {
        // Swing the SVG needle around the hub (70,64): 0 -> -52°, 100 -> +52°.
        const deg = -52 + Math.max(0, Math.min(100, level)) / 100 * 104;
        if (this._el.vuNeedle) {
            this._el.vuNeedle.setAttribute('transform', `rotate(${deg.toFixed(1)} 70 64)`);
        }
    }

    reset() {
        this.setLeds({ onair: false, tuning: false });
        this.setRdsQual(-1, false);
        this.setStation(': : :', {});
        this.setVu(0);
    }
}

/* ───────────────────────── Controller ─────────────────────────── */

class RadioPanel {
    constructor() {
        this._root = null;
        this._statusTimer = null;
        this._playing = false;
        this._station = '';
        this._tuning = false;
        this._lastStatus = null;
        // Whether THIS page's <audio> element currently has an active
        // stream attached. Tracked separately from st.running (the
        // backend's own state) because they can genuinely disagree: a
        // fresh page load (or a plain browser reload) starts with an
        // empty, disconnected <audio> element even though the backend
        // pipeline may already be running from before -- _applyStatus()
        // uses this to auto-reconnect rather than just mirroring
        // st.running in the UI while silently playing nothing.
        this._audioConnected = false;
        // Web Audio VU
        this._audioCtx = null;
        this._analyser = null;
        this._srcNode = null;
        this._vuData = null;
        this._vuRaf = null;
        this._vuLevel = 0;
        this._vuFromWebAudio = false;
        // Skin
        this._skinName = (() => {
            try { return localStorage.getItem('meshpoint.listenerSkin') || 'digital'; }
            catch (_e) { return 'digital'; }
        })();
        this._skin = null;
        // Station presets: active category tab. 'fav' = Favorites.
        this._activeCat = (() => {
            try {
                const v = localStorage.getItem('meshpoint.presetCat');
                return v === 'fav' ? 'fav' : (parseInt(v, 10) || 0);
            } catch (_e) { return 0; }
        })();
        this._tunedCat = null;   // category index of the currently-tuned preset
        this._tunedKey = null;   // "freq|mode" of the currently-tuned preset
    }

    _loadFavs() {
        try { return new Set(JSON.parse(localStorage.getItem('meshpoint.presetFavs') || '[]')); }
        catch (_e) { return new Set(); }
    }

    _toggleFav(freq, mode) {
        const key = `${freq}|${mode}`;
        const favs = this._loadFavs();
        if (favs.has(key)) favs.delete(key); else favs.add(key);
        try { localStorage.setItem('meshpoint.presetFavs', JSON.stringify([...favs])); }
        catch (_e) { /* ignore */ }
    }

    show() {
        this._refreshStatus();
        this._statusTimer = setInterval(() => this._refreshStatus(), 500);
    }

    /**
     * Reconcile audio connection state from a status object polled by
     * something OTHER than this panel's own (visibility-gated) poll loop --
     * specifically SidebarTelemetryRail, which polls /api/listener/status
     * continuously regardless of which page is showing. mount() has
     * already run by the time this is ever externally reachable (the hook
     * mechanism calls it synchronously right after constructing this
     * panel, before anything else gets a chance to run), so there's no
     * "not mounted yet" case to guard here the way the old built-in
     * Listener page's lazy-mount version had to.
     */
    syncAudioFromStatus(status) {
        if (status.running) {
            if (!this._audioConnected) this._startAudio();
        } else {
            this._audioConnected = false;
        }
    }

    hide() {
        clearInterval(this._statusTimer);
        this._statusTimer = null;
    }

    mount(rootEl) {
        this._root = rootEl;
        const root = rootEl;
        root.innerHTML = `
            <section class="lsn-section">
                <div class="panel lsn-radio">
                    <div class="panel__header">
                        <span>Radio</span>
                        <div class="lsn-head-right">
                            <div class="lsn-skins" id="lsn-skins">
                                <button type="button" data-skin="digital">Digital</button>
                                <button type="button" data-skin="analogue">Analogue</button>
                            </div>
                            <div class="lsn-status" id="lsn-status">
                                <span class="lsn-status__dot" id="lsn-status-dot"></span>
                                <span id="lsn-status-text">idle</span>
                            </div>
                        </div>
                    </div>
                    <div class="panel__body lsn-radio__body">
                        <div class="lsn-display" id="lsn-display"></div>
                        <audio id="lsn-audio" controls preload="none"></audio>
                    </div>
                </div>
            </section>

            <section class="lsn-section">
                <div class="panel">
                    <div class="panel__header">Tuner</div>
                    <div class="panel__body lsn-controls">
                        <div class="lsn-field lsn-field--freq">
                            <label for="lsn-freq">Frequency (MHz)</label>
                            <input id="lsn-freq" type="number" min="24" max="1766"
                                   step="0.001" value="98.000" inputmode="decimal">
                        </div>
                        <div class="lsn-field">
                            <label for="lsn-mode">Mode</label>
                            <select id="lsn-mode">
                                <option value="nfm">NFM (narrow FM)</option>
                                <option value="am">AM</option>
                                <option value="wfm" selected>WFM (broadcast)</option>
                                <option value="usb">USB</option>
                                <option value="lsb">LSB</option>
                            </select>
                        </div>
                        <div class="lsn-field">
                            <label for="lsn-deemphasis">FM audio correction</label>
                            <select id="lsn-deemphasis"><option value="">Choose for your region</option><option value="75">75 microseconds (US)</option><option value="50">50 microseconds (Europe)</option></select>
                        </div><div class="lsn-field">
                            <label for="lsn-squelch">Squelch</label>
                            <input id="lsn-squelch" type="number" min="0" max="1000" step="10" value="0">
                        </div>
                        <div class="lsn-field">
                            <label for="lsn-gain">Gain</label>
                            <select id="lsn-gain">
                                <option value="">Auto (AGC)</option>
                                <option value="19.7">19.7 dB</option>
                                <option value="29.7">29.7 dB</option>
                                <option value="38.6">38.6 dB</option>
                                <option value="44.5">44.5 dB</option>
                                <option value="49.6">49.6 dB</option>
                            </select>
                        </div>
                        <div class="lsn-field lsn-field--level">
                            <label for="lsn-volume">Level <span id="lsn-volume-val">0.45</span></label>
                            <input id="lsn-volume" type="range" min="0.05" max="1.5" step="0.05" value="0.45">
                        </div>
                        <div class="lsn-field lsn-field--buttons">
                            <button class="terminal-button" type="button" id="lsn-tune-btn">Tune &amp; Listen</button>
                            <button class="terminal-button" type="button" id="lsn-stop-btn">Stop</button>
                        </div>
                    </div>
                </div>
            </section>

            <section class="lsn-section">
                <div class="panel">
                    <div class="panel__header">Presets</div>
                    <div class="lsn-controls"><label class="lsn-field">Preset library<select id="lsn-preset-library"><option value="manual">Manual tuning (all regions)</option><option value="nl">Netherlands examples (opt in)</option></select></label></div>
                    <div class="panel__body lsn-panel-body">
                        <div class="lsn-preset-bar">
                            <input type="search" id="lsn-preset-search" class="lsn-preset-search"
                                   placeholder="Search presets…" autocomplete="off">
                        </div>
                        <div class="lsn-preset-tabs" id="lsn-preset-tabs">${this._renderPresetTabs()}</div>
                        <div class="lsn-presets-view" id="lsn-presets">${this._renderPresetChannels()}</div>
                    </div>
                </div>
            </section>
        `;

        const library = root.querySelector('#lsn-preset-library');
        try { library.value = localStorage.getItem('meshpoint.presetLibrary') || 'manual'; } catch (_) {}
        library.addEventListener('change', () => {
            try { localStorage.setItem('meshpoint.presetLibrary', library.value); } catch (_) {}
            this._activeCat = 0; this._repaintPresets();
        });
        this._mountSkin(this._skinName);

        root.querySelector('#lsn-tune-btn').addEventListener('click', () => {
            this._station = '';
            this._tunedKey = null;
            this._tunedCat = null;
            this._repaintPresets();
            this._tune();
        });
        root.querySelector('#lsn-stop-btn').addEventListener('click', () => this._stop());

        const vol = root.querySelector('#lsn-volume');
        const volVal = root.querySelector('#lsn-volume-val');
        vol.addEventListener('input', () => { volVal.textContent = (+vol.value).toFixed(2); });
        vol.addEventListener('change', () => { if (this._playing) this._tune(); });

        const tabsEl = root.querySelector('#lsn-preset-tabs');
        const searchEl = root.querySelector('#lsn-preset-search');
        const viewEl = root.querySelector('#lsn-presets');

        viewEl.addEventListener('click', (ev) => {
            const btn = ev.target.closest('button[data-freq]');
            if (!btn) return;
            if (ev.target.closest('[data-fav]')) {   // star toggle, don't tune
                this._toggleFav(btn.dataset.freq, btn.dataset.mode);
                this._repaintPresets();
                return;
            }
            root.querySelector('#lsn-freq').value = btn.dataset.freq;
            root.querySelector('#lsn-mode').value = btn.dataset.mode;
            this._station = btn.dataset.label || btn.textContent.trim();
            this._tunedKey = `${btn.dataset.freq}|${btn.dataset.mode}`;
            this._tunedCat = btn.dataset.cat != null ? parseInt(btn.dataset.cat, 10) : null;
            this._repaintPresets();
            this._resetLevel();
            this._tune();
        });

        tabsEl.addEventListener('click', (ev) => {
            const b = ev.target.closest('button[data-cat]');
            if (!b) return;
            const c = b.dataset.cat;
            this._activeCat = (c === 'fav') ? 'fav' : (parseInt(c, 10) || 0);
            try { localStorage.setItem('meshpoint.presetCat', this._activeCat); } catch (_e) { /* */ }
            searchEl.value = '';
            tabsEl.classList.remove('dimmed');
            this._repaintPresets();
        });

        searchEl.addEventListener('input', () => {
            viewEl.innerHTML = this._renderPresetChannels(searchEl.value);
            tabsEl.classList.toggle('dimmed', !!searchEl.value.trim());
        });

        root.querySelector('#lsn-skins').addEventListener('click', (ev) => {
            const btn = ev.target.closest('button[data-skin]');
            if (!btn) return;
            this._mountSkin(btn.dataset.skin);
        });
    }

    _mountSkin(name) {
        const container = this._root.querySelector('#lsn-display');
        if (!container) return;
        this._skinName = (name === 'analogue') ? 'analogue' : 'digital';
        try { localStorage.setItem('meshpoint.listenerSkin', this._skinName); } catch (_e) { /* ignore */ }
        this._skin = this._skinName === 'analogue' ? new AnalogueSkin() : new DigitalSkin();
        this._skin.mount(container);
        // Highlight the active toggle button.
        this._root.querySelectorAll('#lsn-skins button').forEach((b) =>
            b.classList.toggle('active', b.dataset.skin === this._skinName));
        // Repaint the new skin from the last known state.
        if (this._lastStatus) this._applyStatus(this._lastStatus);
        else this._skin.setFreq(parseFloat(this._root.querySelector('#lsn-freq')?.value));
    }

    _resetLevel() {
        const vol = this._root.querySelector('#lsn-volume');
        const volVal = this._root.querySelector('#lsn-volume-val');
        if (vol) vol.value = RadioPanel.DEFAULT_LEVEL;
        if (volVal) volVal.textContent = RadioPanel.DEFAULT_LEVEL.toFixed(2);
    }

    async _tune() {
        const freq = parseFloat(this._root.querySelector('#lsn-freq').value);
        if (!Number.isFinite(freq)) { this._setStatus(false, 'enter a frequency'); return; }
        const gainRaw = this._root.querySelector('#lsn-gain').value;
        const body = {
            frequency_mhz: freq,
            mode: this._root.querySelector('#lsn-mode').value,
            squelch: parseInt(this._root.querySelector('#lsn-squelch').value, 10) || 0,
            volume: parseFloat(this._root.querySelector('#lsn-volume').value) || RadioPanel.DEFAULT_LEVEL,
            station_label: this._station || '',
            deemphasis_us: Number(this._root.querySelector('#lsn-deemphasis').value) || null,
        };
        if (gainRaw !== '') body.gain = parseFloat(gainRaw);

        this._stopAudio();
        this._tuning = true;
        this._skin.setFreq(freq);
        this._skin.setMode(body.mode);
        this._skin.setLeds({ onair: true, tuning: true });
        this._skin.setStation(this._station || `${fmtFreq4(freq)} MHz`, {});
        this._setStatus(true, 'tuning…');
        try {
            const r = await fetch('/api/listener/tune', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            if (!r.ok) {
                const detail = (await r.json().catch(() => ({}))).detail;
                this._tuning = false;
                this._skin.setLeds({ onair: false, tuning: false });
                this._setStatus(false, detail || `tune failed (${r.status})`);
                return;
            }
            this._playing = true;
            this._tuning = false;
            this._applyStatus(await r.json());
            this._startAudio();
        } catch (err) {
            this._tuning = false;
            this._skin.setLeds({ onair: false, tuning: false });
            this._setStatus(false, 'tune request failed');
        }
    }

    async _stop() {
        this._playing = false;
        this._tuning = false;
        this._station = '';
        this._tunedKey = null;
        this._tunedCat = null;
        this._repaintPresets();
        this._stopAudio();
        this._stopVuLoop();
        this._skin.reset();
        try {
            const r = await fetch('/api/listener/stop', { method: 'POST' });
            if (r.ok) this._applyStatus(await r.json());
        } catch (err) { /* poll catches up */ }
    }

    _startAudio() {
        const audio = this._root.querySelector('#lsn-audio');
        if (!audio) return;
        this._audioConnected = true;
        audio.src = '/api/listener/stream?t=' + Date.now();
        audio.play().catch(() => { /* user can press play manually */ });
        if (this._ensureAudioGraph()) this._startVuLoop();
    }

    _stopAudio() {
        const audio = this._root.querySelector('#lsn-audio');
        this._audioConnected = false;
        if (!audio) return;
        audio.pause();
        audio.removeAttribute('src');
        audio.load();
    }

    _ensureAudioGraph() {
        const audio = this._root.querySelector('#lsn-audio');
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
        this._vuFromWebAudio = true;
        const tick = () => {
            this._analyser.getByteTimeDomainData(this._vuData);
            let sum = 0;
            for (let i = 0; i < this._vuData.length; i++) {
                const x = (this._vuData[i] - 128) / 128;
                sum += x * x;
            }
            const rms = Math.sqrt(sum / this._vuData.length);
            const db = 20 * Math.log10(rms + 1e-6);
            let lvl = Math.max(0, Math.min(100, (db + 50) / 47 * 100));
            this._vuLevel = this._vuLevel * 0.4 + lvl * 0.6;
            if (this._skin) this._skin.setVu(this._vuLevel);
            this._vuRaf = requestAnimationFrame(tick);
        };
        this._vuRaf = requestAnimationFrame(tick);
    }

    _stopVuLoop() {
        if (this._vuRaf) cancelAnimationFrame(this._vuRaf);
        this._vuRaf = null;
        this._vuFromWebAudio = false;
        this._vuLevel = 0;
    }

    async _refreshStatus() {
        try {
            const r = await fetch('/api/listener/status');
            if (!r.ok) return;
            this._applyStatus(await r.json());
        } catch (err) { /* transient */ }
    }

    _applyStatus(st) {
        this._lastStatus = st;
        if (!this._emphasisLoaded && st.deemphasis_us) {
            const control = this._root.querySelector('#lsn-deemphasis');
            if (control && !control.value) control.value = String(st.deemphasis_us);
            this._emphasisLoaded = true;
        }
        // Sync the preset label from the backend (single source of truth
        // now -- see plugins/apps/radio/backend/listener.py's
        // station_label) so a page reload restores it instead of falling
        // back to bare frequency for stations without RDS. Harmless to
        // keep re-syncing after a local preset click too, since tune()'s
        // own response already echoes back the exact label just sent.
        if (st.running && typeof st.station_label === 'string') {
            this._station = st.station_label;
        }
        // Volume slider sync (skip while the user is dragging it).
        if (typeof st.volume === 'number') {
            const vol = this._root.querySelector('#lsn-volume');
            const volVal = this._root.querySelector('#lsn-volume-val');
            if (vol && document.activeElement !== vol) {
                vol.value = st.volume;
                if (volVal) volVal.textContent = (+st.volume).toFixed(2);
            }
        }

        const freq = st.running
            ? st.frequency_mhz
            : parseFloat(this._root.querySelector('#lsn-freq')?.value);
        if (this._skin) {
            this._skin.setFreq(freq);
            this._skin.setMode(st.mode);
            this._skin.setLeds({ onair: st.running, tuning: this._tuning });
            this._skin.setRdsQual(st.rds_bler, st.running);
            if (st.running && st.rds_ps) {
                const ps = st.rds_ps.trim();
                const rt = (st.rds_rt || '').trim();
                const text = (rt && rt !== ps) ? `${ps} : ${rt}` : ps;
                this._skin.setStation(text, { rds: true, pty: st.rds_pty });
            } else {
                this._skin.setStation(
                    this._station || (st.running ? `${fmtFreq4(freq)} MHz` : ': : :'), {});
            }
            if (!this._vuFromWebAudio) {
                const lvl = st.running && typeof st.audio_level === 'number'
                    ? Math.max(0, Math.min(100, st.audio_level)) : 0;
                this._skin.setVu(lvl);
            }
        }

        // Only P2000/Pagers can be "in the way" from Radio's point of view --
        // dongle_owner === 'radio' just means we're the one running.
        const busyOwner = (st.dongle_owner && st.dongle_owner !== 'radio') ? st.dongle_owner : null;
        const tuneBtn = this._root.querySelector('#lsn-tune-btn');
        if (tuneBtn) tuneBtn.disabled = !!busyOwner;

        if (st.running) {
            const label = `${fmtFreq4(st.frequency_mhz)} MHz ${st.mode.toUpperCase()}`
                + (st.listeners ? ` • ${st.listeners} listening` : '');
            this._setStatus(true, label);
            this._playing = true;
            // Backend is running but this page has no active audio
            // connection yet (fresh page load, or a plain browser
            // reload while the pipeline kept running from before) --
            // reconnect rather than leaving the UI showing "on air"
            // while actually silent.
            if (!this._audioConnected) this._startAudio();
        } else {
            this._playing = false;
            this._audioConnected = false;
            if (busyOwner) {
                const labels = { p2000: 'P2000', pagers: 'Pagers', pocsag: 'POCSAG', rtl433: 'RTL433', adsb: 'ADS-B', dab: 'DAB+' };
                this._setStatus(false, `busy : in use by ${labels[busyOwner] || busyOwner}`, true);
            } else {
                this._setStatus(false, st.last_error ? `idle : ${st.last_error}` : 'idle');
            }
        }
    }

    _setStatus(running, text, busy = false) {
        const dot = this._root.querySelector('#lsn-status-dot');
        const label = this._root.querySelector('#lsn-status-text');
        if (dot) {
            dot.classList.toggle('lsn-status__dot--on', !!running);
            dot.classList.toggle('lsn-status__dot--busy', !!busy);
        }
        if (label) label.textContent = text;
    }

    _setActivePreset(btn) {
        this._root.querySelectorAll('#lsn-presets .lsn-preset--active')
            .forEach((b) => b.classList.remove('lsn-preset--active'));
        if (btn) btn.classList.add('lsn-preset--active');
    }

    _clearActivePreset() { this._setActivePreset(null); }

    static get DEFAULT_LEVEL() { return 0.45; }

    static get PRESET_GROUPS() {
        try { return localStorage.getItem('meshpoint.presetLibrary') === 'nl' ? RadioPanel.NL_PRESET_GROUPS : []; }
        catch (_) { return []; }
    }

    static get NL_PRESET_GROUPS() {
        return [
            {
                name: 'Amsterdam FM Radio', mode: 'wfm', items: [
                    ['NPO Radio 1', 98.6], ['NPO Radio 2', 92.3], ['NPO 3FM', 96.5],
                    ['NPO Klassiek', 94.3], ['NPO FunX', 96.1], ['Qmusic', 100.4],
                    ['Radio 538', 102.4], ['Radio 10', 91.6], ['Sky Radio', 101.5],
                    ['Joe', 103.8], ['Radio Veronica', 95.3], ['100% NL', 89.6],
                    ['SLAM!', 98.0], ['BNR Nieuwsradio', 101.8],
                ],
            },
            {
                name: 'PMR446 (analog, 12.5 kHz NFM)', mode: 'nfm', items: [
                    ['Ch 1', 446.00625], ['Ch 2', 446.01875], ['Ch 3', 446.03125],
                    ['Ch 4', 446.04375], ['Ch 5', 446.05625], ['Ch 6', 446.06875],
                    ['Ch 7', 446.08125], ['Ch 8', 446.09375], ['Ch 9', 446.10625],
                    ['Ch 10', 446.11875], ['Ch 11', 446.13125], ['Ch 12', 446.14375],
                    ['Ch 13', 446.15625], ['Ch 14', 446.16875], ['Ch 15', 446.18125],
                    ['Ch 16', 446.19375],
                ],
            },
            {
                name: 'Marine VHF (marifoon)', mode: 'nfm', items: [
                    ['Ch 10 intership', 156.500], ['Ch 16 distress/call', 156.800],
                    ['Ch 31 marina (ship)', 156.550], ['Ch 31 marina (coast)', 161.150],
                    ['Ch 67 rec. block', 156.375], ['Ch 77 boat-to-boat', 156.875],
                ],
            },
            {
                name: 'Marine UHF on-board (457/467)', mode: 'nfm', items: [
                    ['Ch 1', 457.5250], ['Ch 2 social', 457.5375], ['Ch 3', 457.5500],
                    ['Ch 4 social', 457.5625], ['Ch 5', 457.5750], ['Ch 6', 467.5250],
                    ['Ch 7', 467.5375], ['Ch 8', 467.5500], ['Ch 9', 467.5625],
                    ['Ch 10', 467.5750],
                ],
            },
            {
                name: 'Schiphol Tower (AM)', mode: 'am', items: [
                    ['Zwanenburgbaan 18C/36C', 118.100], ['Polderbaan 18R/36L', 118.275],
                    ['Kaagbaan 06/24', 135.108], ['East/Aalsmeer 04/22·18L', 119.225],
                ],
            },
            {
                name: 'Schiphol Approach & Radar (AM)', mode: 'am', items: [
                    ['Arrival (primary)', 118.400], ['Approach/Dep TMA East', 119.050],
                    ['Approach TMA West', 121.200], ['Arrival', 131.150],
                    ['Approach', 118.075], ['Approach', 126.675],
                    ['Radar ARTIP', 120.550], ['Radar RIVER', 127.775], ['Radar SUGOL', 118.805],
                ],
            },
            {
                name: 'Schiphol Ground & Delivery (AM)', mode: 'am', items: [
                    ['Ground North/east', 121.800], ['Ground South', 121.700],
                    ['Ground West', 121.900], ['Ground Polderbaan', 121.568],
                    ['Delivery', 121.975], ['Planner', 121.650],
                ],
            },
            {
                name: 'Schiphol ATIS & Emergency (AM)', mode: 'am', items: [
                    ['Arrival ATIS', 132.975], ['Departure ATIS', 122.200],
                    ['Emergency 121.5', 121.500],
                ],
            },
            {
                name: 'Ham & Utility', mode: 'nfm', items: [
                    ['2m calling 145.500', 145.500], ['70cm ISM 433.500', 433.500],
                ],
            },
        ];
    }

    // Short label for a category tab, derived from the group name.
    static _tabLabel(name) {
        return name.replace(/\s*\(.*?\)\s*/g, ' ')
                   .replace(/\bon-board\b.*/i, '')
                   .replace(/\bRadio\b/i, '')
                   .replace(/\s+/g, ' ')
                   .trim();
    }

    // One preset row, with a ☆/★ favorite toggle and the frequency shown
    // on the right -- same row shape as the DAB+ tab's station list.
    _btn(label, freq, mode, catIndex, favs) {
        const key = `${freq}|${mode}`;
        const on = favs.has(key);
        const active = key === this._tunedKey ? ' lsn-preset--active' : '';
        return `<button type="button" class="${active.trim()}" data-freq="${freq}" data-mode="${mode}" data-cat="${catIndex}" data-label="${label}">`
             + `<span class="lsn-fav${on ? ' on' : ''}" data-fav title="Favorite">${on ? '★' : '☆'}</span>`
             + `<span class="lsn-preset-row__label">${label}</span>`
             + `<span class="lsn-preset-row__freq">${freq} MHz</span>`
             + `</button>`;
    }

    _repaintPresets() {
        const tabs = this._root.querySelector('#lsn-preset-tabs');
        const view = this._root.querySelector('#lsn-presets');
        const search = this._root.querySelector('#lsn-preset-search');
        if (tabs) tabs.innerHTML = this._renderPresetTabs();
        if (view) view.innerHTML = this._renderPresetChannels(search ? search.value : '');
    }

    _btnList(items, defMode, catIndex, favs) {
        return items.map(([label, freq, mode]) =>
            this._btn(label, freq, mode || defMode, catIndex, favs)).join('');
    }

    _renderPresetTabs() {
        const favCount = this._loadFavs().size;
        let html = `<button type="button" data-cat="fav" class="lsn-preset-tab lsn-preset-tab--fav`
            + `${this._activeCat === 'fav' ? ' active' : ''}">★ Favorites`
            + `${favCount ? ` (${favCount})` : ''}</button>`;
        html += RadioPanel.PRESET_GROUPS.map((g, i) => {
            const dot = (i === this._tunedCat) ? '<span class="lsn-preset-tab__dot"></span>' : '';
            return `<button type="button" data-cat="${i}" class="lsn-preset-tab`
                 + `${i === this._activeCat ? ' active' : ''}">${RadioPanel._tabLabel(g.name)}${dot}</button>`;
        }).join('');
        return html;
    }

    // No filter -> the active category (or Favorites). With a filter -> matching
    // station presets across every category, grouped for context.
    _renderPresetChannels(filter) {
        const groups = RadioPanel.PRESET_GROUPS;
        if (!groups.length) return '<p class="lsn-preset-empty">Enter a local frequency in the tuner. The optional Netherlands library contains location-specific examples; verify channels before use.</p>';
        const favs = this._loadFavs();
        const f = (filter || '').trim().toLowerCase();
        if (f) {
            let html = '';
            groups.forEach((g, i) => {
                const items = g.items.filter(([label, freq]) =>
                    label.toLowerCase().includes(f) ||
                    String(freq).includes(f) ||
                    g.name.toLowerCase().includes(f));
                if (!items.length) return;
                html += `<div class="lsn-preset-group"><div class="lsn-preset-group__name">${g.name}</div>`
                      + `<div class="lsn-presets">${this._btnList(items, g.mode, i, favs)}</div></div>`;
            });
            return html || '<div class="lsn-preset-empty">No matching presets</div>';
        }
        if (this._activeCat === 'fav') {
            let html = '';
            groups.forEach((g, i) => {
                g.items.forEach(([label, freq, mode]) => {
                    const m = mode || g.mode;
                    if (favs.has(`${freq}|${m}`)) html += this._btn(label, freq, m, i, favs);
                });
            });
            return html
                ? `<div class="lsn-presets">${html}</div>`
                : '<div class="lsn-preset-empty">No favorites yet : click the ☆ on any preset to pin it here.</div>';
        }
        const idx = Math.min(Math.max(0, this._activeCat), groups.length - 1);
        const g = groups[idx];
        return `<div class="lsn-presets">${this._btnList(g.items, g.mode, idx, favs)}</div>`;
    }
}

window.RadioPanel = RadioPanel;

if (typeof window.registerPageHook === 'function') {
    window.registerPageHook({
        host: 'rtlsdr',
        label: 'Radio',
        make: () => {
            const panel = new RadioPanel();
            // Exposed for SidebarTelemetryRail's mini-player
            // (syncAudioFromStatus, called on every /api/listener/status
            // poll regardless of which page is showing) -- previously set
            // by app.js's _bootListenerPanel() when Radio was the
            // built-in Listener page.
            window.radioPanel = panel;
            return panel;
        },
    });
} else {
    console.warn('Radio plugin: page hook registry missing');
}
