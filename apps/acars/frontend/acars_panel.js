/*
 * ACARS plugin -- Listener tab.
 *
 * Loaded (as <script defer>) into the dashboard by Meshpoint's plugin asset
 * injector when plugins.acars.enabled is set. Registers an "ACARS" tab on the
 * Listener page that reuses the core PagerPanel with a custom row renderer.
 */
(function () {
    'use strict';

    // ACARS compact lat/lon strings: N52233E004447 = N 52°23.3' E 4°44.7'
    // (5-7 digits after N/S = ddmm[m], 6-8 after E/W = dddmm[m]).
    function _acarsLatLon(s) {
        const m = /([NS])(\d{2})(\d{2})(\d?)([EW])(\d{3})(\d{2})(\d?)/.exec(s || '');
        if (!m) return null;
        const frac = (t) => (t ? Number(t) / 10 : 0);
        let lat = Number(m[2]) + (Number(m[3]) + frac(m[4])) / 60;
        let lon = Number(m[6]) + (Number(m[7]) + frac(m[8])) / 60;
        if (m[1] === 'S') lat = -lat;
        if (m[5] === 'W') lon = -lon;
        return { lat, lon };
    }

    function _acarsCoordHtml(lat, lon, esc) {
        const t = `${Math.abs(lat).toFixed(4)}°${lat >= 0 ? 'N' : 'S'} ${Math.abs(lon).toFixed(4)}°${lon >= 0 ? 'E' : 'W'}`;
        const url = `https://www.openstreetmap.org/?mlat=${lat.toFixed(5)}&mlon=${lon.toFixed(5)}#map=9/${lat.toFixed(4)}/${lon.toFixed(4)}`;
        return `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer" class="acars-coord">${esc(t)}</a>`;
    }

    // acarsdec --output json: one object per decoded ACARS message. Fixed
    // envelope fields (timestamp/tail/flight/label/text). When acarsdec was
    // built with libacars, standard types carry an expanded sub-object --
    // ADS-C position contracts (label B6) get a summary line; plain-text
    // POS reports (label H1) get their coordinate lifted out and linked.
    // Everything else shows the raw text (airline-proprietary telemetry).
    function _acarsRowHtml(m, esc) {
        const ts = m.timestamp || m.received_at;
        const time = ts
            ? new Date(ts * 1000).toLocaleTimeString([], {
                hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
            })
            : '';
        const who = [m.flight, m.tail].filter(Boolean).join('  ');
        const label = m.label ? `[${m.label}]` : '';
        const decoded = (m.acars && m.acars.libacars) || m.libacars;
        const raw = (m.text || '').trim();

        let body;

        // --- ADS-C position report (libacars-decoded) ---
        const tags = decoded && decoded.arinc622 && decoded.arinc622.adsc
            && decoded.arinc622.adsc.tags;
        const rep = Array.isArray(tags)
            && (tags.find((t) => t && t.basic_report) || {}).basic_report;
        if (rep && rep.lat != null && rep.lon != null) {
            const bits = [_acarsCoordHtml(rep.lat, rep.lon, esc)];
            if (rep.alt != null) bits.push(`${esc(String(rep.alt))} ft`);
            if (rep.pos_accuracy_nm != null) bits.push(`±${esc(String(rep.pos_accuracy_nm))} nm`);
            body = `<span class="acars-summary"><span class="acars-kind">ADS-C</span> ${bits.join(' · ')}</span>`
                + `<details class="acars-raw"><summary>details</summary><pre class="pager-row__decoded">${esc(JSON.stringify(decoded, null, 1))}</pre></details>`;
        } else if (/^POS/.test(raw)) {
            // --- plain-text POS report ---
            const c = _acarsLatLon(raw.slice(3));
            const rw = (raw.match(/\bRW(\d{1,2}[LRC]?)\b/) || [])[1];
            const parts = [];
            if (c) parts.push(_acarsCoordHtml(c.lat, c.lon, esc));
            if (rw) parts.push(`RW ${esc(rw)}`);
            body = parts.length
                ? `<span class="acars-summary"><span class="acars-kind">POS</span> ${parts.join(' · ')}</span>`
                  + `<details class="acars-raw"><summary>raw</summary><pre class="pager-row__decoded">${esc(raw)}</pre></details>`
                : esc(raw);
        } else if (decoded) {
            body = `<span>${esc(raw || '(no text)')}</span>`
                + `<details class="acars-raw"><summary>decoded</summary><pre class="pager-row__decoded">${esc(JSON.stringify(decoded, null, 1))}</pre></details>`;
        } else {
            body = esc(raw || '(no text)');
        }

        return `
            <div class="pager-row pager-row--acars">
                <span class="pager-row__time">${esc(time)}</span>
                <span class="pager-row__proto">${esc(who || '--')} <span class="acars-label">${esc(label)}</span></span>
                <span class="pager-row__msg">${body}</span>
            </div>
        `;
    }

    if (typeof window.registerPageHook !== 'function' || !window.PagerPanel) {
        console.warn('ACARS plugin: page hook registry or PagerPanel missing');
        return;
    }

    // Lives on the RTL-SDR Plugins page (plugins/apps/rtlsdr/) via the
    // "hook" seam, not the built-in Listener page's tabbar.
    window.registerPageHook({
        host: 'rtlsdr',
        label: 'ACARS',
        make: () => new window.PagerPanel('acars', '/api/acars', 'ACARS', _acarsRowHtml),
    });
})();
