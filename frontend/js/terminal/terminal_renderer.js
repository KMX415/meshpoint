/**
 * Terminal renderer.
 *
 * Single responsibility: own the xterm.js Terminal instance, all of
 * its addons, the active theme, the keyboard map, and the
 * clipboard glue. Everything visual about the shell lives here so
 * the panel controller stays a pure orchestrator and so the renderer
 * can be swapped or restyled without touching the WebSocket layer.
 *
 * Built around a small set of pluggable addons:
 *
 *   - FitAddon       : auto-fits rows/cols to the host element
 *   - WebglAddon     : GPU-accelerated rendering, with a canvas
 *                      fallback if the GPU/context is unavailable
 *   - SearchAddon    : Ctrl+F overlay; the search UI itself lives in
 *                      ``TerminalSearchOverlay`` and just calls into
 *                      this addon
 *   - WebLinksAddon  : URL detection + Ctrl-click to open
 *   - Unicode11Addon : modern emoji / CJK width tables
 *
 * Clipboard:
 *
 *   - ``Ctrl+Shift+C`` copies the current selection (or the cursor's
 *     line if nothing selected) using the Async Clipboard API
 *   - ``Ctrl+Shift+V`` pastes from the clipboard via ``term.paste``
 *   - ``copyOnSelect: true`` mirrors iTerm2-style "drag to copy"
 *
 * The class never touches the WebSocket; ``input`` events surface as
 * ``onInput`` callbacks that the panel forwards.
 */

class TerminalRenderer {
    constructor(hostEl, callbacks = {}) {
        this.hostEl = hostEl;
        this.term = null;
        this.fitAddon = null;
        this.webglAddon = null;
        this.searchAddon = null;
        this.unicodeAddon = null;
        this.webLinksAddon = null;
        this._resizeBound = false;
        this.onInput = callbacks.onInput || (() => {});
        this.onResize = callbacks.onResize || (() => {});
        this.onSelectionCopy = callbacks.onSelectionCopy || (() => {});
        this.onSearchToggle = callbacks.onSearchToggle || (() => {});
    }

    init() {
        if (this.term) return this.term;
        if (!window.Terminal) {
            console.warn('xterm.js not loaded; terminal will not initialize');
            return null;
        }
        this.term = new window.Terminal({
            cursorBlink: true,
            cursorStyle: 'bar',
            cursorWidth: 2,
            fontFamily: '"JetBrains Mono", "JetBrainsMono Nerd Font", Menlo, Consolas, monospace',
            fontSize: 13,
            fontWeight: 400,
            fontWeightBold: 600,
            letterSpacing: 0,
            lineHeight: 1.25,
            scrollback: 5000,
            copyOnSelect: true,
            macOptionIsMeta: true,
            allowProposedApi: true,
            convertEol: false,
            theme: this._tokyoNightStorm(),
        });

        this._loadAddons();
        this.term.open(this.hostEl);
        this._activateWebgl();
        this._activateUnicode11();

        this.term.onData((data) => this.onInput(data));
        this.term.onResize(({ rows, cols }) => this.onResize(rows, cols));
        this.term.attachCustomKeyEventHandler((event) => this._handleKey(event));

        if (this.fitAddon) {
            requestAnimationFrame(() => this.fitAddon.fit());
        }
        if (!this._resizeBound) {
            this._resizeBound = true;
            window.addEventListener('resize', () => this.fit());
        }
        return this.term;
    }

    fit() {
        try { this.fitAddon?.fit(); } catch (_) {}
    }

    focus() {
        this.term?.focus();
    }

    write(text) {
        this.term?.write(text);
    }

    writeln(text) {
        this.term?.writeln(text);
    }

    clear() {
        this.term?.clear();
    }

    dispose() {
        try { this.webglAddon?.dispose(); } catch (_) {}
        try { this.term?.dispose(); } catch (_) {}
        this.term = null;
    }

    /** Expose the search addon so the search overlay can drive it. */
    getSearchAddon() {
        return this.searchAddon;
    }

    /** Current viewport size, useful for sending an initial resize. */
    getDimensions() {
        return this.term ? { rows: this.term.rows, cols: this.term.cols } : null;
    }

    _loadAddons() {
        if (window.FitAddon) {
            this.fitAddon = new window.FitAddon.FitAddon();
            this.term.loadAddon(this.fitAddon);
        }
        if (window.SearchAddon) {
            this.searchAddon = new window.SearchAddon.SearchAddon();
            this.term.loadAddon(this.searchAddon);
        }
        if (window.WebLinksAddon) {
            this.webLinksAddon = new window.WebLinksAddon.WebLinksAddon();
            this.term.loadAddon(this.webLinksAddon);
        }
        if (window.Unicode11Addon) {
            this.unicodeAddon = new window.Unicode11Addon.Unicode11Addon();
            this.term.loadAddon(this.unicodeAddon);
        }
    }

    _activateWebgl() {
        if (!window.WebglAddon) return;
        try {
            this.webglAddon = new window.WebglAddon.WebglAddon();
            this.webglAddon.onContextLoss(() => {
                try { this.webglAddon.dispose(); } catch (_) {}
                this.webglAddon = null;
            });
            this.term.loadAddon(this.webglAddon);
        } catch (err) {
            console.info('WebGL renderer unavailable, falling back to canvas:', err);
            this.webglAddon = null;
        }
    }

    _activateUnicode11() {
        if (!this.unicodeAddon) return;
        try {
            this.term.unicode.activeVersion = '11';
        } catch (_) {}
    }

    _handleKey(event) {
        if (event.type !== 'keydown') return true;
        if (event.ctrlKey && event.shiftKey) {
            const key = event.key.toLowerCase();
            if (key === 'c' || key === 'v' || key === 'f') {
                // xterm returns false to skip its handler but does not call
                // preventDefault; Chrome/Cursor still bind Ctrl+Shift+C to
                // devtools unless we block the browser default here.
                event.preventDefault();
                event.stopPropagation();
                if (key === 'c') return this._copySelection();
                if (key === 'v') return this._pasteFromClipboard();
                if (key === 'f') return this._toggleSearch();
            }
        }
        return true;
    }

    _copySelection() {
        const selection = this._readSelectionText();
        if (!selection) {
            this.onSelectionCopy(0);
            return false;
        }
        try {
            navigator.clipboard.writeText(selection).then(() => {
                this.onSelectionCopy(selection.length);
            }).catch(() => {
                this.onSelectionCopy(0);
            });
        } catch (_) {
            this.onSelectionCopy(0);
        }
        return false;
    }

    /** xterm selection first; fall back to DOM selection inside the host. */
    _readSelectionText() {
        const fromTerm = (this.term?.getSelection() || '').trim();
        if (fromTerm) return fromTerm;
        try {
            const dom = window.getSelection();
            if (!dom || dom.isCollapsed || !dom.toString().trim()) return '';
            const anchor = dom.anchorNode;
            const focus = dom.focusNode;
            if (!this.hostEl) return '';
            if (anchor && !this.hostEl.contains(anchor)) return '';
            if (focus && !this.hostEl.contains(focus)) return '';
            return dom.toString();
        } catch (_) {
            return '';
        }
    }

    _pasteFromClipboard() {
        try {
            navigator.clipboard.readText().then((text) => {
                if (text) this.term?.paste(text);
            }).catch(() => {});
        } catch (_) {}
        return false;
    }

    _toggleSearch() {
        this.onSearchToggle();
        return false;
    }

    /**
     * Tokyo Night Storm palette tuned to Meshpoint's amber accent.
     * Full 16-color ANSI palette so colorized tools (`ls --color`,
     * `git`, `journalctl`) render properly instead of falling back
     * to the xterm defaults' muddy primaries.
     */
    _tokyoNightStorm() {
        return {
            background: '#16181f',
            foreground: '#c0caf5',
            cursor: '#ffb84d',
            cursorAccent: '#16181f',
            selectionBackground: 'rgba(255, 184, 77, 0.28)',
            selectionForeground: '#1a1d24',
            black:         '#1d202f',
            red:           '#f7768e',
            green:         '#9ece6a',
            yellow:        '#e0af68',
            blue:          '#7aa2f7',
            magenta:       '#bb9af7',
            cyan:          '#7dcfff',
            white:         '#a9b1d6',
            brightBlack:   '#414868',
            brightRed:     '#ff8b96',
            brightGreen:   '#b9f27c',
            brightYellow:  '#ffb84d',
            brightBlue:    '#9aa9f7',
            brightMagenta: '#c8b5ff',
            brightCyan:    '#a4dfff',
            brightWhite:   '#c0caf5',
        };
    }
}

window.TerminalRenderer = TerminalRenderer;
