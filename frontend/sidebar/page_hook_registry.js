/*
 * Plugin seam for injecting content into ANOTHER plugin's already-rendered
 * page, instead of owning a page/tab of your own -- "panel" (a Listener
 * sub-tab) and "sidebar" (a whole top-level page) both give a plugin its
 * OWN space; "hook" instead lets a plugin attach into a HOST's space.
 *
 * A host page opts in by calling window.mountPageHooks(hostId, containerEl)
 * once from inside its own mount(rootEl) -- typically after rendering its
 * own content, passing an element for hook content to render into. Nothing
 * else is required of a host, and it costs nothing when zero hook plugins
 * target it (mountPageHooks returns a no-op {show,hide} then). hostId is
 * whatever id the host's own page is known by -- for a "sidebar" plugin,
 * that's its plugin.toml [sidebar].route.
 *
 * A hook plugin registers via:
 *
 *   window.registerPageHook({
 *       host: 'hello-world',     // must match plugin.toml's [hook].host
 *       label: 'My Plugin',      // optional -- only shown if >1 hook targets
 *                                 // the same host (see below); a single hook
 *                                 // renders directly, no tab chrome at all
 *       make: () => ({
 *           mount(el) { el.innerHTML = '<p>Hello from a hook.</p>'; },
 *           show() {},
 *           hide() {},
 *       }),
 *   });
 *
 * Ordering: every plugin's frontend script runs before app.js (see
 * src/plugins/assets.py's injection-marker comment) -- so every
 * registerPageHook() call has already landed in the queue below by the
 * time any host's own mount() runs and calls mountPageHooks(), even
 * though mount() itself is only called later (e.g. a "sidebar" host's
 * mount() runs from window.mountPluginSidebarPages(), itself called from
 * app.js).
 *
 * Multiple hooks on one host: a single hook renders directly into the
 * container, same as always. Two or more get a small internal tabbar
 * (built automatically, no host-side code needed) -- only the active
 * tab's panel is mounted-visible and receiving show()/hide(), matching
 * how the old Listener page's own tabbar only kept one sub-panel "live"
 * at a time (no point polling a DAB+ status endpoint while looking at an
 * unrelated tab). First real user: the DAB+ plugin's player + Config
 * panel, both hooking into the same "rtlsdr" host.
 */

window.MESHPOINT_PAGE_HOOKS = window.MESHPOINT_PAGE_HOOKS || [];

window.registerPageHook = function registerPageHook({ host, label, make }) {
    window.MESHPOINT_PAGE_HOOKS.push({ host, label, make });
};

const _NOOP_HOOK_GROUP = { show() {}, hide() {} };

/**
 * Mounts every hook registered for *hostId* under *containerEl*.
 *
 * Returns {show(), hide()} -- call these from your own page's show()/hide()
 * (the router calls those on navigation, unlike mount() which runs once at
 * boot regardless of visibility) so a hook whose own show() kicks off data
 * loading or status polling actually gets to. With one hook this just
 * forwards to it directly; with several, it forwards to whichever tab is
 * currently active (switching tabs handles hide()/show() on the old/new
 * tab itself).
 */
window.mountPageHooks = function mountPageHooks(hostId, containerEl) {
    if (!containerEl) return _NOOP_HOOK_GROUP;
    const hooks = window.MESHPOINT_PAGE_HOOKS.filter((h) => h.host === hostId);
    if (hooks.length === 0) return _NOOP_HOOK_GROUP;

    if (hooks.length === 1) {
        let panel = null;
        try {
            panel = hooks[0].make();
            const wrapper = document.createElement('div');
            containerEl.appendChild(wrapper);
            if (panel && typeof panel.mount === 'function') panel.mount(wrapper);
        } catch (err) {
            console.error(`Page hook for host "${hostId}" failed to mount:`, err);
            panel = null;
        }
        return {
            show() { if (panel && typeof panel.show === 'function') panel.show(); },
            hide() { if (panel && typeof panel.hide === 'function') panel.hide(); },
        };
    }

    const tabbar = document.createElement('div');
    tabbar.className = 'page-hook-tabbar';
    containerEl.appendChild(tabbar);

    const entries = []; // { btn, wrapper, panel }
    let activeIndex = 0;

    function activate(i) {
        entries.forEach((e, j) => {
            const active = j === i;
            e.wrapper.style.display = active ? '' : 'none';
            e.btn.classList.toggle('page-hook-tabbar__btn--active', active);
        });
        activeIndex = i;
    }

    hooks.forEach(({ make, label }, i) => {
        let panel = null;
        const wrapper = document.createElement('div');
        wrapper.className = 'page-hook-tabpanel';
        try {
            panel = make();
            containerEl.appendChild(wrapper);
            if (panel && typeof panel.mount === 'function') panel.mount(wrapper);
        } catch (err) {
            console.error(`Page hook for host "${hostId}" failed to mount:`, err);
        }

        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'page-hook-tabbar__btn';
        btn.textContent = label || `Plugin ${i + 1}`;
        btn.addEventListener('click', () => {
            if (i === activeIndex) return;
            const prev = entries[activeIndex];
            if (prev.panel && typeof prev.panel.hide === 'function') prev.panel.hide();
            activate(i);
            if (panel && typeof panel.show === 'function') panel.show();
        });
        tabbar.appendChild(btn);
        entries.push({ btn, wrapper, panel });
    });

    activate(0);

    return {
        show() {
            const e = entries[activeIndex];
            if (e.panel && typeof e.panel.show === 'function') e.panel.show();
        },
        hide() {
            const e = entries[activeIndex];
            if (e.panel && typeof e.panel.hide === 'function') e.panel.hide();
        },
    };
};
