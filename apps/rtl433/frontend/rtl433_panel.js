/*
 * RTL433 plugin -- Listener tab.
 *
 * Loaded (as <script defer>) into the dashboard by Meshpoint's plugin asset
 * injector when plugins.rtl433.enabled is set. Registers an "RTL433" tab on
 * the Listener page that reuses the core PagerPanel with a custom row
 * renderer.
 */
(function () {
    'use strict';

    // rtl_433's decoded field set varies wildly by device model (a
    // temperature sensor and a remote control share almost no fields), so
    // unlike the fixed protocol/capcode/message row PagerPanel renders by
    // default, this just shows the model name plus whatever other keys a
    // given event happens to carry.
    function _rtl433RowHtml(m, esc) {
        const time = m.received_at
            ? new Date(m.received_at * 1000).toLocaleTimeString([], {
                hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
            })
            : '';
        const skip = new Set(['time', 'model', 'received_at']);
        const fields = Object.keys(m)
            .filter((k) => !skip.has(k) && m[k] !== null && m[k] !== undefined && m[k] !== '')
            .map((k) => `${k}: ${m[k]}`)
            .join('  ·  ');
        return `
            <div class="pager-row">
                <span class="pager-row__time">${esc(time)}</span>
                <span class="pager-row__proto">${esc(m.model || '')}</span>
                <span class="pager-row__msg">${esc(fields)}</span>
            </div>
        `;
    }

    if (typeof window.registerPageHook !== 'function' || !window.PagerPanel) {
        console.warn('RTL433 plugin: page hook registry or PagerPanel missing');
        return;
    }

    // Lives on the RTL-SDR Plugins page (plugins/apps/rtlsdr/) via the
    // "hook" seam, not the built-in Listener page's tabbar.
    window.registerPageHook({
        host: 'rtlsdr',
        label: 'RTL433',
        make: () => new window.PagerPanel('rtl433', '/api/rtl433', 'RTL433', _rtl433RowHtml),
    });
})();
