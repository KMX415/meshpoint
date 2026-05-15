/**
 * Topbar — right-side action group.
 *
 * Anchors quick-action buttons that live on every page (refresh,
 * command palette, theme toggle). For v0.7.4 Sprint A we ship a
 * Refresh action only; sprint D adds the command palette and theme
 * toggle by appending more buttons through register().
 *
 * Single responsibility: own the action-row DOM, expose register()
 * so other features can plug their own buttons in without coupling
 * to the topbar template.
 */
class TopbarActions {
    constructor(rootEl) {
        this._root = rootEl;
        this._buttons = new Map();
        this._registerRefresh();
    }

    register({ id, label, icon, onClick, hotkey }) {
        if (this._buttons.has(id)) return;
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'topbar-action';
        btn.dataset.actionId = id;
        btn.setAttribute('aria-label', label);
        if (hotkey) btn.setAttribute('title', `${label} · ${hotkey}`);
        else btn.setAttribute('title', label);
        btn.innerHTML = icon;
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            try { onClick(e); } catch (err) { console.error('action error:', err); }
        });
        this._root.appendChild(btn);
        this._buttons.set(id, btn);
        return btn;
    }

    _registerRefresh() {
        this.register({
            id: 'refresh',
            label: 'Refresh page data',
            hotkey: 'F5',
            icon: `
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
                     stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
                     width="16" height="16" aria-hidden="true">
                    <polyline points="23 4 23 10 17 10"/>
                    <polyline points="1 20 1 14 7 14"/>
                    <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
                </svg>
            `,
            onClick: () => location.reload(),
        });
    }
}

window.TopbarActions = TopbarActions;
