/**
 * RTL-SDR -- the shared host page every RTL-SDR plugin hooks a tab into.
 *
 * The old built-in Listener page (which used to own Radio directly plus
 * every other RTL-SDR plugin's tab via window.registerListenerPanel) is
 * gone. Every RTL-SDR plugin, Radio included, now injects its own tab into
 * THIS page instead via window.registerPageHook() (see
 * frontend/sidebar/page_hook_registry.js and docs/PLUGINS.md). DAB+
 * (plugins/apps/dab/) was the first to move -- see its own README for why.
 */
window.registerSidebarPage({
    route: 'rtlsdr',
    make: () => {
        // mountPageHooks() returns {show(), hide()} -- kept in this closure
        // so our own show()/hide() (called by the router on navigation,
        // unlike mount() which runs once at boot regardless of visibility)
        // can forward into it. Required, not optional: a hook whose own
        // show() kicks off data loading or status polling (e.g. DAB+'s
        // panels) never would otherwise, since mount() alone never calls
        // it. With multiple hooks sharing this page (auto-tabbed), this
        // only ever reaches whichever tab is currently active.
        let hookGroup = null;
        return {
            mount(rootEl) {
                const hasHooks = (window.MESHPOINT_PAGE_HOOKS || [])
                    .some((h) => h.host === 'rtlsdr');
                const emptyState = `
                    <p>No RTL-SDR plugins enabled yet. Enable one --
                    Radio, DAB+, P2000, Pagers, POCSAG, RTL433, ACARS, or
                    ADS-B -- in Settings &rarr; Plugins to see its tab
                    here.</p>
                `;
                rootEl.innerHTML = `
                    <div class="plugin-page">
                        <h2>RTL-SDR</h2>
                        ${hasHooks ? '<div class="rtlsdr-hooks" data-rtlsdr-hooks></div>' : emptyState}
                    </div>
                `;
                if (hasHooks && typeof window.mountPageHooks === 'function') {
                    hookGroup = window.mountPageHooks('rtlsdr', rootEl.querySelector('[data-rtlsdr-hooks]'));
                }
            },
            show() { if (hookGroup) hookGroup.show(); },
            hide() { if (hookGroup) hookGroup.hide(); },
        };
    },
});
