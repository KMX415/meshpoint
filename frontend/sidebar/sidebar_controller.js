/**
 * Sidebar controller: viewport-aware navigation rail.
 *
 * Responsibilities (kept small on purpose):
 *  - Toggle between expanded / rail / mobile-drawer states based on
 *    viewport width and user override (persisted in localStorage).
 *  - Drive the active accent bar via FLIP so navigation feels like
 *    one continuous element sliding between items.
 *  - Show / hide content sections based on the current route id.
 *  - Expose surface for status-badge updates (unread, NodeInfo TX
 *    countdown, update-available pill).
 *  - Keyboard navigation (arrow keys, Enter, "g d" / "g s" shortcuts).
 *
 * Does NOT own the URL: that's Router's job. The controller simply
 * subscribes to route changes.
 */

class SidebarController {
    constructor({ router, app, identity = null }) {
        this._router = router;
        this._app = app || document.querySelector('.app');
        this._sidebar = document.querySelector('.sidebar');
        this._navEl = this._sidebar?.querySelector('.sidebar__nav') || null;
        this._activeBar = document.querySelector('.sidebar__active-bar');
        this._allLinks = Array.from(document.querySelectorAll('.sidebar__link[data-route], .sidebar__group-toggle[data-group]'));
        this._sectionEls = Array.from(document.querySelectorAll('[data-section]'));
        this._identity = identity;
        this._storageKey = 'meshpoint.sidebar.preference';
        this._gPressedAt = 0;
        this._handleKeydown = this._handleKeydown.bind(this);
        this._handleResize = this._handleResize.bind(this);
        this._handleHamburger = this._handleHamburger.bind(this);
        this._handleBackdrop = this._handleBackdrop.bind(this);
        this._handleCollapseToggle = this._handleCollapseToggle.bind(this);
        this._handleGroupToggle = this._handleGroupToggle.bind(this);
        this._handleNavClick = this._handleNavClick.bind(this);
        this._handleDocumentClick = this._handleDocumentClick.bind(this);
    }

    bind() {
        this._applyViewportState();
        this._wireEvents();
        this._wireRouterSubscription();
        this._applyIdentity();
        this._refreshCollapseAffordance();
        requestAnimationFrame(() => {
            requestAnimationFrame(() => this._refreshAccentBar());
        });
        if (this._navEl && typeof ResizeObserver !== 'undefined') {
            this._navResizeObserver = new ResizeObserver(() => this._refreshAccentBar());
            this._navResizeObserver.observe(this._navEl);
        }
    }

    setIdentity(identity) {
        this._identity = identity;
        this._applyIdentity();
    }

    setStatusBadge(routeId, value, variant = '') {
        const badge = this._sidebar.querySelector(`[data-badge-for="${routeId}"]`);
        if (!badge) return;
        if (value === null || value === undefined || value === '' || value === 0) {
            badge.style.display = 'none';
            badge.textContent = '';
            return;
        }
        badge.style.display = '';
        badge.textContent = String(value);
        badge.className = 'sidebar__badge' + (variant ? ` sidebar__badge--${variant}` : '');
    }

    _wireEvents() {
        const collapseBtn = document.getElementById('sidebar-collapse-btn');
        if (collapseBtn) collapseBtn.addEventListener('click', this._handleCollapseToggle);

        const hamburger = document.getElementById('sidebar-hamburger');
        if (hamburger) hamburger.addEventListener('click', this._handleHamburger);

        const backdrop = document.getElementById('sidebar-backdrop');
        if (backdrop) backdrop.addEventListener('click', this._handleBackdrop);

        this._allLinks.forEach((el) => {
            if (el.classList.contains('sidebar__group-toggle')) {
                el.addEventListener('click', this._handleGroupToggle);
            } else {
                el.addEventListener('click', this._handleNavClick);
            }
        });

        window.addEventListener('resize', this._handleResize);
        window.addEventListener('keydown', this._handleKeydown);

        // Tablet click-outside-to-collapse: when the rail has been
        // expanded transiently and the operator clicks anywhere outside
        // the sidebar, snap it back to icon-only rail. Desktop is not
        // affected (sidebar is meant to be persistent there) and mobile
        // already has its own dedicated backdrop element.
        document.addEventListener('click', this._handleDocumentClick);

        if (this._navEl) {
            this._navEl.addEventListener('scroll', () => {
                const route = this._router.currentRoute();
                if (route) this._slideAccentBar(route);
            }, { passive: true });
        }
    }

    _wireRouterSubscription() {
        this._router.onRouteChange((route) => this._renderActive(route));
    }

    _renderActive(route) {
        this._sectionEls.forEach((el) => {
            const matches = el.dataset.section === route;
            el.style.display = matches ? '' : 'none';
            el.classList.toggle('section--active', matches);
        });

        document.querySelectorAll('.sidebar__link[data-route]').forEach((el) => {
            const isActive = el.dataset.route === route;
            if (isActive) el.setAttribute('aria-current', 'page');
            else el.removeAttribute('aria-current');
            el.parentElement.dataset.active = isActive ? 'true' : 'false';
        });

        const parentGroup = route.split('/')[0];
        document.querySelectorAll('.sidebar__group').forEach((g) => {
            if (g.dataset.group === parentGroup && route.includes('/')) {
                g.dataset.expanded = 'true';
            }
        });

        this._slideAccentBar(route);
        this._notifyActivation(route);
    }

    _slideAccentBar(route) {
        if (!this._activeBar) return;
        if (this._app?.dataset.sidebar === 'rail') {
            this._activeBar.dataset.visible = 'false';
            return;
        }
        const nav = this._navEl || this._activeBar.parentElement;
        if (!nav) return;
        const link = nav.querySelector(`.sidebar__link[data-route="${route}"]`);
        if (!link) {
            this._activeBar.dataset.visible = 'false';
            return;
        }
        // Bar is the last child of .sidebar__nav (after the long <ul>). Without
        // top:0 in CSS its static position sits at the bottom of the list, which
        // made translateY look ~one header/list too low. Measure from nav top.
        const offsetTop = this._linkOffsetInNav(link, nav);
        const itemHeight = link.offsetHeight || link.getBoundingClientRect().height;
        const barHeight = parseInt(getComputedStyle(this._activeBar).height, 10) || 22;
        const yCenter = offsetTop + (itemHeight - barHeight) / 2;
        this._activeBar.style.transform = `translateY(${Math.round(yCenter)}px)`;
        this._activeBar.dataset.visible = 'true';
    }

    /** Offset from top of .sidebar__nav content box to the active link row. */
    _linkOffsetInNav(link, nav) {
        const navRect = nav.getBoundingClientRect();
        const linkRect = link.getBoundingClientRect();
        return linkRect.top - navRect.top + nav.scrollTop;
    }

    _refreshAccentBar() {
        const route = this._router.currentRoute();
        if (route) this._slideAccentBar(route);
    }

    _notifyActivation(route) {
        const root = route.split('/')[0];
        if (root === 'messages' && window.messagingPanel) {
            window.messagingPanel.onActivated();
            window.messagingPanel.resetUnreadBadge();
        }
        if (root === 'radio' && window.radioSettings) {
            window.radioSettings.onActivated();
        }
        if (root === 'stats' && window.statsTab) {
            window.statsTab.refresh();
        }
        if (route === 'terminal' && window.terminalController) {
            window.terminalController.onActivated();
        }
        if (root === 'configuration' && window.configurationController) {
            window.configurationController.onActivated(route);
        }
        if (root === 'settings' && window.settingsController) {
            window.settingsController.onActivated(route);
        }
        document.dispatchEvent(new CustomEvent('sidebar:routeActivated', { detail: { route } }));
    }

    _handleNavClick(event) {
        const route = event.currentTarget.dataset.route;
        if (!route) return;
        event.preventDefault();
        this._router.navigate(route);
        if (window.matchMedia('(max-width: 767px)').matches) {
            this._app.dataset.sidebar = 'expanded';
        }
    }

    _handleGroupToggle(event) {
        const group = event.currentTarget.closest('.sidebar__group');
        if (!group) return;
        const expanded = group.dataset.expanded === 'true';
        group.dataset.expanded = expanded ? 'false' : 'true';
        requestAnimationFrame(() => this._refreshAccentBar());
    }

    _handleCollapseToggle() {
        const current = this._app.dataset.sidebar;
        const next = current === 'rail' ? 'expanded' : 'rail';
        this._app.dataset.sidebar = next;
        try { localStorage.setItem(this._storageKey, next); } catch (_) {}
        this._refreshCollapseAffordance();
        requestAnimationFrame(() => this._refreshAccentBar());
    }

    _refreshCollapseAffordance() {
        const btn = document.getElementById('sidebar-collapse-btn');
        if (!btn) return;
        const isRail = this._app.dataset.sidebar === 'rail';
        const label = isRail ? 'Expand sidebar' : 'Collapse sidebar';
        btn.setAttribute('aria-label', label);
        btn.title = `${label} ([)`;
    }

    _handleHamburger() {
        this._app.dataset.sidebar = 'drawer-open';
    }

    _handleBackdrop() {
        this._app.dataset.sidebar = 'expanded';
    }

    /**
     * Document-level click handler that collapses an expanded rail
     * back to icon-only when the operator clicks outside the sidebar.
     *
     * Tablet-only by design: the sidebar default at 768-1023px is
     * rail, and the toggle button is treated as a transient expand.
     * Clicking elsewhere should feel like dismissing a popover.
     *
     * Skipped at:
     *   - desktop (>=1024px): sidebar is persistent there, by design
     *   - mobile (<768px): dedicated backdrop element handles the
     *     drawer dismissal already
     *   - when click target is inside the sidebar itself or the
     *     collapse-toggle button (the toggle has its own handler)
     *
     * Persists 'rail' to localStorage so the next reload also lands
     * on rail, matching the "click outside == I'm done with this"
     * mental model.
     */
    _handleDocumentClick(event) {
        const w = window.innerWidth;
        if (w < 768 || w >= 1024) return;
        if (this._app.dataset.sidebar !== 'expanded') return;
        const target = event.target;
        if (!target) return;
        if (this._sidebar && this._sidebar.contains(target)) return;
        const collapseBtn = document.getElementById('sidebar-collapse-btn');
        if (collapseBtn && collapseBtn.contains(target)) return;
        const hamburger = document.getElementById('sidebar-hamburger');
        if (hamburger && hamburger.contains(target)) return;

        this._app.dataset.sidebar = 'rail';
        try { localStorage.setItem(this._storageKey, 'rail'); } catch (_) {}
        this._refreshCollapseAffordance();
    }

    _applyViewportState() {
        const stored = (() => {
            try { return localStorage.getItem(this._storageKey); } catch (_) { return null; }
        })();
        const w = window.innerWidth;
        if (w < 768) {
            this._app.dataset.sidebar = 'expanded';
        } else if (w < 1024) {
            this._app.dataset.sidebar = stored === 'expanded' ? 'expanded' : 'rail';
        } else {
            this._app.dataset.sidebar = stored === 'rail' ? 'rail' : 'expanded';
        }
    }

    _handleResize() {
        const wasDrawerOpen = this._app.dataset.sidebar === 'drawer-open';
        if (wasDrawerOpen && window.innerWidth >= 768) {
            this._app.dataset.sidebar = 'expanded';
            this._refreshCollapseAffordance();
            return;
        }
        this._applyViewportState();
        this._refreshCollapseAffordance();
        const route = this._router.currentRoute();
        if (route) this._slideAccentBar(route);
    }

    _handleKeydown(event) {
        if (event.target && /input|textarea|select/i.test(event.target.tagName)) return;
        if (event.target && event.target.isContentEditable) return;

        if (event.key === '[' && !event.metaKey && !event.ctrlKey && !event.altKey) {
            const current = this._app.dataset.sidebar;
            if (current === 'rail' || current === 'expanded') {
                event.preventDefault();
                this._handleCollapseToggle();
                return;
            }
        }

        const now = Date.now();
        if (event.key === 'g' && !event.metaKey && !event.ctrlKey && !event.altKey) {
            this._gPressedAt = now;
            return;
        }
        if (this._gPressedAt && now - this._gPressedAt < 1000) {
            const map = { d: 'dashboard', s: 'stats', m: 'messages', r: 'radio', t: 'terminal' };
            if (map[event.key]) {
                this._gPressedAt = 0;
                this._router.navigate(map[event.key]);
                event.preventDefault();
                return;
            }
        }
        this._gPressedAt = 0;
    }

    _applyIdentity() {
        if (!this._identity) return;
        const role = this._identity.role || 'admin';
        const username = this._identity.username || '--';
        const rolePill = document.getElementById('sidebar-role-pill');
        const userEl = document.getElementById('sidebar-username');
        if (rolePill) {
            rolePill.textContent = role;
            rolePill.className = 'sidebar__role-pill' + (role === 'viewer' ? ' sidebar__role-pill--viewer' : '');
        }
        if (userEl) userEl.textContent = username;

        const allowed = new Set(this._identity.available_sections || []);
        if (!allowed.size) return;
        document.querySelectorAll('[data-requires-section]').forEach((el) => {
            const need = el.dataset.requiresSection;
            const visible = allowed.has(need);
            el.style.display = visible ? '' : 'none';
        });
    }
}

window.SidebarController = SidebarController;
