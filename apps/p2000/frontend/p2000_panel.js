/*
 * P2000 plugin -- Listener tab.
 *
 * Loaded (as <script defer>) into the dashboard by Meshpoint's plugin asset
 * injector when plugins.p2000.enabled is set. Registers a "P2000" tab on
 * the Listener page that reuses the core PagerPanel (its default
 * protocol/capcode/message row shape fits FLEX pages as-is, no custom row
 * renderer needed) -- same as how Pagers/POCSAG (still core) and the
 * ACARS/RTL433 plugins all reuse it.
 */
(function () {
    'use strict';

    if (typeof window.registerPageHook !== 'function' || !window.PagerPanel) {
        console.warn('P2000 plugin: page hook registry or PagerPanel missing');
        return;
    }

    // Lives on the RTL-SDR Plugins page (plugins/apps/rtlsdr/) via the
    // "hook" seam, not the built-in Listener page's tabbar.
    window.registerPageHook({
        host: 'rtlsdr',
        label: 'P2000',
        make: () => new window.PagerPanel('p2000', '/api/p2000', 'P2000'),
    });
})();
