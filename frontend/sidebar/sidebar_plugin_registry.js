/*
 * Plugin seam for top-level sidebar pages.
 *
 * Two halves feed this, both injected before app.js runs (server-side, from
 * src/plugins/assets.py):
 *
 *   1. A <script> per sidebar-capable plugin, generated from its
 *      plugin.toml [sidebar] table, pushing a descriptor onto
 *      window.MESHPOINT_SIDEBAR_PLUGINS -- {id, route, label, category, icon}.
 *   2. The plugin's own frontend script, calling:
 *
 *        window.registerSidebarPage({
 *            route: 'hello-world',      // must match plugin.toml's sidebar.route
 *            make: () => ({
 *                mount(rootEl) { rootEl.innerHTML = '<p>Hello, world.</p>'; },
 *                show() {},
 *                hide() {},
 *            }),
 *        });
 *
 * window.mountPluginSidebarPages(), called once from app.js *before* the
 * Router/SidebarController are constructed, builds the actual sidebar <li>
 * + content <section> for every descriptor that also got a matching
 * factory, mounts it, and returns [{routeId, panel}] so app.js can fold the
 * route ids into the Router's allowedRoutes and wire show/hide.
 *
 * category placement mirrors the real sidebar sections in index.html:
 *   "networks" / "radio" / "ops" -- flat item runs, identified by a
 *     data-category attribute on that section's <li class="sidebar__group-header">.
 *   "configuration" / "settings" -- the two collapsible submenus
 *     (<li class="sidebar__group" data-group="...">); the route is nested
 *     as "<category>/<route>", same convention as the built-in subitems
 *     (e.g. "settings/plugins").
 */

window.MESHPOINT_SIDEBAR_PLUGINS = window.MESHPOINT_SIDEBAR_PLUGINS || [];

(function () {
    const factories = Object.create(null);

    window.registerSidebarPage = function registerSidebarPage({ route, make }) {
        factories[route] = make;
    };

    function _iconSvg() {
        return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true">'
            + '<path d="M4 18v-4M8 18V8M12 18v-6M16 18V4M20 18v-9"/></svg>';
    }

    function _escape(value) {
        return String(value || '').replace(/[&<>"']/g, (c) => (
            { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
        ));
    }

    function _isNested(category) {
        return category === 'configuration' || category === 'settings';
    }

    /** Where to insert this category's new <li> -- {parent, before} (before
     * may be null, meaning "append at the end of parent"), or null if the
     * category's own anchor isn't in the DOM (shouldn't happen; every
     * KNOWN_SIDEBAR_CATEGORIES value has one in index.html). */
    function _findInsertionTarget(category) {
        if (category === "radio" || category === "ops") category = "networks";
        if (_isNested(category)) {
            const sublist = document.querySelector(
                `.sidebar__group[data-group="${category}"] .sidebar__sublist`,
            );
            return sublist ? { parent: sublist, before: null } : null;
        }
        const list = document.querySelector('.sidebar__nav .sidebar__list');
        const header = list && list.querySelector(
            `.sidebar__group-header[data-category="${category}"]`,
        );
        if (!header) return null;
        // Walk to the end of this section's run of items (next header/group
        // starts the next section; end of list = last section).
        let node = header.nextElementSibling;
        while (
            node
            && !node.classList.contains('sidebar__group-header')
            && !node.classList.contains('sidebar__group')
        ) {
            node = node.nextElementSibling;
        }
        return { parent: list, before: node };
    }

    function _buildLink(routeId, label, nested, icon) {
        const li = document.createElement('li');
        li.className = nested ? 'sidebar__subitem' : 'sidebar__item';
        const iconHtml = nested ? '' : `<span class="sidebar__icon">${_iconSvg(icon)}</span>`;
        // Same data-badge-for convention as the built-in sidebar items
        // (messages/radio/settings-updates in index.html) -- gives every
        // plugin sidebar page a status-badge slot via
        // SidebarController.setStatusBadge(routeId, ...), even though
        // only the rtlsdr plugin actually populates one today (see
        // sdr_status_badge.js). Hidden until a badge script sets it.
        li.innerHTML = `<a href="#/${routeId}" class="sidebar__link" data-route="${routeId}">` +
            `${iconHtml}<span class="sidebar__label">${_escape(label)}</span>` +
            `<span class="sidebar__badge" data-badge-for="${routeId}" style="display:none"></span></a>`;
        return li;
    }

    window.mountPluginSidebarPages = function mountPluginSidebarPages() {
        const mounted = [];
        const content = document.getElementById('app-content');
        if (!content) return mounted;

        window.MESHPOINT_SIDEBAR_PLUGINS.forEach((desc) => {
            const make = factories[desc.route];
            if (!make) {
                console.warn(
                    `Plugin sidebar page "${desc.route}" (${desc.id}) is declared in ` +
                    `plugin.toml but its frontend script never called registerSidebarPage().`,
                );
                return;
            }
            const target = _findInsertionTarget(desc.category);
            if (!target) {
                console.warn(
                    `Plugin sidebar page "${desc.route}" (${desc.id}): unknown category ` +
                    `"${desc.category}" -- not mounted.`,
                );
                return;
            }

            const nested = _isNested(desc.category);
            const routeId = nested ? `${desc.category}/${desc.route}` : desc.route;

            if (Array.from(document.querySelectorAll("[data-section]")).some(el => el.dataset.section === routeId)) return;
            const li = _buildLink(routeId, desc.label, nested, desc.icon);
            if (target.before) target.parent.insertBefore(li, target.before);
            else target.parent.appendChild(li);

            const section = document.createElement('section');
            section.className = 'section';
            section.dataset.pluginPage = desc.id;
            section.dataset.section = routeId;
            section.style.display = 'none';
            content.appendChild(section);

            let panel = null;
            try {
                panel = make();
                if (panel && typeof panel.mount === 'function') panel.mount(section);
            } catch (err) {
                console.error(`Plugin sidebar page "${routeId}" (${desc.id}) failed to mount:`, err);
            }

            mounted.push({ routeId, panel });
        });

        return mounted;
    };
})();
