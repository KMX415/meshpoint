/**
 * Floating Ctrl+F search overlay for the terminal.
 *
 * Single responsibility: own the small floating search bar that
 * appears over the xterm host when the user hits Ctrl+Shift+F (or
 * clicks the toolbar Find button), drive ``xterm-addon-search`` from
 * the input box, and surface match navigation buttons.
 *
 * The overlay is a self-contained DOM fragment built from
 * ``buildOverlay`` so the host page only needs an empty positioned
 * container; everything else is created here. This keeps the
 * overlay reusable in other "section over xterm" contexts later
 * (e.g. a logs viewer) without having to template the markup in
 * ``index.html``.
 */

class TerminalSearchOverlay {
    constructor(containerEl, getSearchAddon) {
        this.container = containerEl;
        this._getSearchAddon = getSearchAddon;
        this._open = false;
        this._lastQuery = '';
        this._buildOverlay();
    }

    isOpen() {
        return this._open;
    }

    open() {
        if (this._open) {
            this.input.focus();
            this.input.select();
            return;
        }
        this._open = true;
        this.root.classList.add('terminal-search--open');
        this.root.setAttribute('aria-hidden', 'false');
        requestAnimationFrame(() => {
            this.input.focus();
            this.input.select();
        });
    }

    close() {
        if (!this._open) return;
        this._open = false;
        this.root.classList.remove('terminal-search--open');
        this.root.setAttribute('aria-hidden', 'true');
        this._clearHighlight();
    }

    toggle() {
        if (this._open) this.close();
        else this.open();
    }

    _buildOverlay() {
        this.root = document.createElement('div');
        this.root.className = 'terminal-search';
        this.root.setAttribute('role', 'search');
        this.root.setAttribute('aria-hidden', 'true');
        this.root.innerHTML = `
            <span class="terminal-search__icon" aria-hidden="true">⌕</span>
            <input
                class="terminal-search__input"
                type="text"
                placeholder="Find in terminal"
                autocomplete="off"
                spellcheck="false"
                aria-label="Search terminal"
            />
            <div class="terminal-search__count" data-search-count></div>
            <div class="terminal-search__buttons">
                <button type="button" class="terminal-search__btn" data-search-prev aria-label="Previous match">↑</button>
                <button type="button" class="terminal-search__btn" data-search-next aria-label="Next match">↓</button>
                <button type="button" class="terminal-search__btn terminal-search__btn--close" data-search-close aria-label="Close search">✕</button>
            </div>
        `;
        this.container.appendChild(this.root);

        this.input = this.root.querySelector('.terminal-search__input');
        this.countEl = this.root.querySelector('[data-search-count]');
        this.prevBtn = this.root.querySelector('[data-search-prev]');
        this.nextBtn = this.root.querySelector('[data-search-next]');
        this.closeBtn = this.root.querySelector('[data-search-close]');

        this.input.addEventListener('input', () => this._onQueryChange());
        this.input.addEventListener('keydown', (e) => this._onKey(e));
        this.prevBtn.addEventListener('click', () => this._findPrev());
        this.nextBtn.addEventListener('click', () => this._findNext());
        this.closeBtn.addEventListener('click', () => this.close());
    }

    _onQueryChange() {
        const query = this.input.value || '';
        this._lastQuery = query;
        if (!query) {
            this._clearHighlight();
            this._setCount('');
            return;
        }
        this._findNext({ incremental: true });
    }

    _onKey(event) {
        if (event.key === 'Escape') {
            event.preventDefault();
            this.close();
            return;
        }
        if (event.key === 'Enter') {
            event.preventDefault();
            if (event.shiftKey) this._findPrev();
            else this._findNext();
        }
    }

    _findNext({ incremental } = {}) {
        const addon = this._getSearchAddon();
        if (!addon || !this._lastQuery) return;
        const found = addon.findNext(this._lastQuery, this._opts(incremental));
        this._setCount(found ? '' : 'no matches');
    }

    _findPrev() {
        const addon = this._getSearchAddon();
        if (!addon || !this._lastQuery) return;
        const found = addon.findPrevious(this._lastQuery, this._opts());
        this._setCount(found ? '' : 'no matches');
    }

    _opts(incremental = false) {
        return {
            caseSensitive: false,
            incremental,
            decorations: {
                matchBackground: 'rgba(255, 184, 77, 0.45)',
                matchBorder: 'rgba(255, 184, 77, 0.85)',
                matchOverviewRuler: '#ffb84d',
                activeMatchBackground: 'rgba(255, 184, 77, 0.75)',
                activeMatchBorder: '#ffb84d',
                activeMatchColorOverviewRuler: '#ffb84d',
            },
        };
    }

    _clearHighlight() {
        const addon = this._getSearchAddon();
        try { addon?.clearDecorations(); } catch (_) {}
        try { addon?.clearActiveDecoration(); } catch (_) {}
    }

    _setCount(text) {
        if (this.countEl) this.countEl.textContent = text;
    }
}

window.TerminalSearchOverlay = TerminalSearchOverlay;
