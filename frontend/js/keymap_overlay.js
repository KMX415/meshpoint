/**
 * Keyboard shortcut overlay (press ? anywhere).
 *
 * Renders a centered modal listing every registered keyboard shortcut
 * grouped by section. Items are registered by feature modules at boot:
 *
 *     window.keymapOverlay.register({
 *         keys: ['Ctrl', 'K'], label: 'Open command palette',
 *         group: 'Global',
 *     });
 *
 * Activation: the literal `?` keypress, only when the user is not
 * editing a text field. Esc or click-outside dismisses.
 *
 * Single responsibility: render the registered list. Each shortcut's
 * actual handler lives in the feature module that owns it.
 */
class KeymapOverlay {
    constructor() {
        this._items = [];
        this._root = null;
        this._open = false;
        this._onKeydown = this._onKeydown.bind(this);
    }

    init() {
        document.addEventListener('keydown', (event) => {
            if (!this._isOverlayShortcut(event)) return;
            event.preventDefault();
            this.toggle();
        });
    }

    register(item) {
        if (!item || !Array.isArray(item.keys) || !item.label) return;
        this._items.push(item);
    }

    registerAll(items) { (items || []).forEach((it) => this.register(it)); }

    toggle() { this._open ? this.close() : this.open(); }

    open() {
        this._mount();
        this._open = true;
        this._root.classList.add('keymap--open');
        document.addEventListener('keydown', this._onKeydown, true);
    }

    close() {
        if (!this._open) return;
        this._open = false;
        if (this._root) this._root.classList.remove('keymap--open');
        document.removeEventListener('keydown', this._onKeydown, true);
    }

    _isOverlayShortcut(event) {
        if (event.ctrlKey || event.metaKey || event.altKey) return false;
        if (_isEditingTarget(event.target)) return false;
        return event.key === '?';
    }

    _onKeydown(event) {
        if (event.key === 'Escape') {
            event.preventDefault();
            this.close();
        }
    }

    _mount() {
        if (this._root) {
            this._render();
            return;
        }
        const root = document.createElement('div');
        root.className = 'keymap';
        root.setAttribute('role', 'dialog');
        root.setAttribute('aria-modal', 'true');
        root.setAttribute('aria-label', 'Keyboard shortcuts');
        root.innerHTML = `
            <div class="keymap__backdrop" data-keymap-close></div>
            <div class="keymap__panel" data-keymap-body></div>
        `;
        document.body.appendChild(root);
        this._root = root;
        root.querySelector('[data-keymap-close]').addEventListener('click', () => this.close());
        this._render();
    }

    _render() {
        const body = this._root.querySelector('[data-keymap-body]');
        const groups = new Map();
        for (const item of this._items) {
            const group = item.group || 'Global';
            if (!groups.has(group)) groups.set(group, []);
            groups.get(group).push(item);
        }
        const html = [
            `<header class="keymap__header">
                <span class="keymap__title">Keyboard shortcuts</span>
                <span class="keymap__hint">press <kbd>?</kbd> or <kbd>Esc</kbd> to close</span>
            </header>`,
        ];
        for (const [group, items] of groups) {
            html.push(`<section class="keymap__group">
                <h3>${_escape(group)}</h3>
                <ul>
                    ${items.map((it) => `
                        <li>
                            <span class="keymap__keys">${it.keys.map((k) => `<kbd>${_escape(k)}</kbd>`).join('<span class="keymap__plus">+</span>')}</span>
                            <span class="keymap__label">${_escape(it.label)}</span>
                        </li>
                    `).join('')}
                </ul>
            </section>`);
        }
        body.innerHTML = html.join('');
    }
}

function _isEditingTarget(el) {
    if (!el || !el.tagName) return false;
    const tag = el.tagName.toLowerCase();
    if (tag === 'input' || tag === 'textarea' || tag === 'select') return true;
    return !!el.isContentEditable;
}

function _escape(str) {
    const span = document.createElement('span');
    span.textContent = str || '';
    return span.innerHTML;
}

window.KeymapOverlay = KeymapOverlay;
