/**
 * Ctrl+K command palette.
 *
 * Modal overlay that fuzzy-filters a registered command list and
 * runs the selected command on Enter. Items can be:
 *
 *   - route shortcuts (e.g. "Go to Dashboard")
 *   - actions (e.g. "Toggle sounds", "Refresh dashboard")
 *
 * Extensible by external code: window.commandPalette.register(item)
 * after boot. Keyboard-only by design — Esc closes, ↑/↓ navigate,
 * Enter runs.
 *
 * Single responsibility: the palette UI + keyboard binding. The
 * commands themselves are owned by their feature modules.
 */
class CommandPalette {
    constructor() {
        this._items = [];
        this._root = null;
        this._inputEl = null;
        this._listEl = null;
        this._filtered = [];
        this._activeIndex = 0;
        this._open = false;
        this._onKeydown = this._onKeydown.bind(this);
    }

    init() {
        document.addEventListener('keydown', (event) => {
            if (this._isPaletteShortcut(event)) {
                event.preventDefault();
                this.toggle();
            }
        });
    }

    register(item) {
        if (!item || !item.id || !item.label) return;
        this._items.push(item);
    }

    registerAll(items) {
        (items || []).forEach((item) => this.register(item));
    }

    toggle() {
        if (this._open) this.close();
        else this.open();
    }

    open() {
        if (this._open) return;
        this._mount();
        this._open = true;
        this._root.classList.add('cmd-palette--open');
        this._inputEl.value = '';
        this._activeIndex = 0;
        this._render('');
        this._inputEl.focus();
        document.addEventListener('keydown', this._onKeydown, true);
    }

    close() {
        if (!this._open) return;
        this._open = false;
        if (this._root) this._root.classList.remove('cmd-palette--open');
        document.removeEventListener('keydown', this._onKeydown, true);
    }

    _isPaletteShortcut(event) {
        const ctrlOrMeta = event.ctrlKey || event.metaKey;
        return ctrlOrMeta && (event.key === 'k' || event.key === 'K');
    }

    _onKeydown(event) {
        if (event.key === 'Escape') {
            event.preventDefault();
            this.close();
        } else if (event.key === 'ArrowDown') {
            event.preventDefault();
            this._move(1);
        } else if (event.key === 'ArrowUp') {
            event.preventDefault();
            this._move(-1);
        } else if (event.key === 'Enter') {
            event.preventDefault();
            this._runActive();
        }
    }

    _move(delta) {
        if (this._filtered.length === 0) return;
        const len = this._filtered.length;
        this._activeIndex = (this._activeIndex + delta + len) % len;
        this._highlight();
    }

    _runActive() {
        const item = this._filtered[this._activeIndex];
        if (!item) return;
        this.close();
        try { item.run(); } catch (e) { console.error('palette command failed:', e); }
    }

    _mount() {
        if (this._root) return;
        const root = document.createElement('div');
        root.className = 'cmd-palette';
        root.setAttribute('role', 'dialog');
        root.setAttribute('aria-modal', 'true');
        root.setAttribute('aria-label', 'Command palette');
        root.innerHTML = `
            <div class="cmd-palette__backdrop" data-cmd-close></div>
            <div class="cmd-palette__panel">
                <div class="cmd-palette__hint">⌘K · Type to search · ↵ to run · Esc to close</div>
                <input type="text" class="cmd-palette__input" placeholder="Search commands…" autocomplete="off" spellcheck="false" />
                <ul class="cmd-palette__list" role="listbox"></ul>
            </div>
        `;
        document.body.appendChild(root);
        this._root = root;
        this._inputEl = root.querySelector('.cmd-palette__input');
        this._listEl = root.querySelector('.cmd-palette__list');
        this._inputEl.addEventListener('input', () => {
            this._activeIndex = 0;
            this._render(this._inputEl.value);
        });
        root.querySelector('[data-cmd-close]').addEventListener('click', () => this.close());
        this._listEl.addEventListener('click', (e) => {
            const li = e.target.closest('li[data-cmd-id]');
            if (!li) return;
            const id = li.dataset.cmdId;
            const idx = this._filtered.findIndex((it) => it.id === id);
            if (idx < 0) return;
            this._activeIndex = idx;
            this._runActive();
        });
    }

    _render(query) {
        const q = (query || '').trim().toLowerCase();
        this._filtered = q
            ? this._items.filter((it) => _fuzzyMatch(it, q))
            : this._items.slice();
        this._listEl.innerHTML = this._filtered.map((it, idx) => `
            <li role="option" data-cmd-id="${it.id}"
                class="${idx === this._activeIndex ? 'cmd-palette__row--active' : ''}">
                <span class="cmd-palette__row-icon">${it.icon || '›'}</span>
                <span class="cmd-palette__row-body">
                    <span class="cmd-palette__row-label">${_escapeHtml(it.label)}</span>
                    ${it.hint ? `<span class="cmd-palette__row-hint">${_escapeHtml(it.hint)}</span>` : ''}
                </span>
                ${it.group ? `<span class="cmd-palette__row-group">${_escapeHtml(it.group)}</span>` : ''}
            </li>
        `).join('') || `<li class="cmd-palette__empty">No matches.</li>`;
    }

    _highlight() {
        const rows = this._listEl.querySelectorAll('li[data-cmd-id]');
        rows.forEach((row, idx) => {
            row.classList.toggle('cmd-palette__row--active', idx === this._activeIndex);
            if (idx === this._activeIndex) row.scrollIntoView({ block: 'nearest' });
        });
    }
}

function _fuzzyMatch(item, query) {
    const haystack = `${item.label} ${item.hint || ''} ${item.group || ''}`.toLowerCase();
    if (haystack.includes(query)) return true;
    let i = 0;
    for (const ch of haystack) {
        if (ch === query[i]) i++;
        if (i === query.length) return true;
    }
    return false;
}

function _isEditingTarget(el) {
    if (!el || !el.tagName) return false;
    const tag = el.tagName.toLowerCase();
    if (tag === 'input' || tag === 'textarea' || tag === 'select') return true;
    return !!el.isContentEditable;
}

function _escapeHtml(str) {
    const span = document.createElement('span');
    span.textContent = str || '';
    return span.innerHTML;
}

window.CommandPalette = CommandPalette;
