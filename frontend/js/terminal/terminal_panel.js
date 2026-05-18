/**
 * Terminal panel orchestrator.
 *
 * Single responsibility: glue the renderer, search overlay, chrome,
 * command drawer, and WebSocket client into one cooperating bundle.
 * No DOM authoring, no xterm config, no theme decisions -- those all
 * live in their dedicated component classes.
 *
 * Lifecycle is lazy: the controller is constructed once at app boot,
 * but the renderer + WebSocket only spin up the first time the
 * operator clicks Connect. That keeps the dashboard responsive for
 * users who never visit the Terminal section.
 */

class TerminalPanelController {
    constructor(rootEl) {
        this.root = rootEl;
        this.hostEl = rootEl.querySelector('#terminal-host');
        this.searchHostEl = rootEl.querySelector('[data-term-search-host]') || rootEl;
        this.statusEl = rootEl.querySelector('[data-term-status]');
        this.connectBtn = rootEl.querySelector('[data-term-connect]');
        this.disconnectBtn = rootEl.querySelector('[data-term-disconnect]');
        this.clearBtn = rootEl.querySelector('[data-term-clear]');
        this.searchBtn = rootEl.querySelector('[data-term-search]');
        this.copyBtn = rootEl.querySelector('[data-term-copy]');
        this.toggleBtn = rootEl.querySelector('[data-term-toggle-drawer]');
        this.closeBtn = rootEl.querySelector('[data-term-close-drawer]');
        this.drawerEl = rootEl.querySelector('[data-term-drawer]');
        this.hintEl = rootEl.querySelector('[data-term-hint]');

        this.client = new window.TerminalClient();
        this.renderer = null;
        this.search = null;
        this.chrome = new window.TerminalChrome(rootEl);
        this.splash = window.TerminalSplash ? new window.TerminalSplash() : null;
        this.drawer = new window.CommandDrawer(this.drawerEl, {
            toggleBtn: this.toggleBtn,
            closeBtn: this.closeBtn,
            onInsert: (cmd) => this._insertCommand(cmd),
        });
        this._loadedCommands = false;
    }

    bind() {
        this.drawer.bind();
        this.connectBtn?.addEventListener('click', () => this.connect());
        this.disconnectBtn?.addEventListener('click', () => this.disconnect());
        this.clearBtn?.addEventListener('click', () => this.renderer?.clear());
        this.searchBtn?.addEventListener('click', () => this._toggleSearch());
        this.copyBtn?.addEventListener('click', () => this._copySelection());
        this._wireClientCallbacks();
        document.addEventListener('keydown', (event) => this._maybeGlobalShortcut(event));
    }

    async refresh() {
        if (this._loadedCommands) return;
        this._loadedCommands = true;
        await this.drawer.load();
    }

    onSectionEnter() {
        this.renderer?.fit();
    }

    connect() {
        if (this.client.connected) return;
        this._ensureRenderer();
        this._setStatus('connecting', 'connecting…');
        this.client.connect();
    }

    disconnect() {
        this.client.disconnect();
    }

    _ensureRenderer() {
        if (this.renderer) return;
        if (!window.TerminalRenderer) {
            this._setStatus('error', 'renderer not loaded');
            return;
        }
        this.renderer = new window.TerminalRenderer(this.hostEl, {
            onInput: (data) => this.client.sendInput(data),
            onResize: (rows, cols) => this.client.sendResize(rows, cols),
            onSelectionCopy: (n) => this.chrome.flashCopyToast(n),
            onSearchToggle: () => this._toggleSearch(),
        });
        this.renderer.init();
        if (window.TerminalSearchOverlay) {
            this.search = new window.TerminalSearchOverlay(
                this.searchHostEl,
                () => this.renderer.getSearchAddon(),
            );
        }
    }

    _wireClientCallbacks() {
        this.client.onOpen = () => {
            this._setStatus('connected', 'connected');
            this._setButtonState(true);
            requestAnimationFrame(() => {
                this.renderer?.fit();
                const dims = this.renderer?.getDimensions();
                if (dims) this.client.sendResize(dims.rows, dims.cols);
            });
            this.renderer?.focus();
        };
        this.client.onReady = (info) => {
            this.chrome.setSession(info);
            if (this.splash && this.renderer) {
                this.splash.render(this.renderer, info);
            }
        };
        this.client.onOutput = (bytes) => {
            this.renderer?.write(new TextDecoder('utf-8', { fatal: false }).decode(bytes));
        };
        this.client.onExit = (code) => {
            this.renderer?.writeln(`\r\n\x1b[2m[session exited (code ${code})]\x1b[0m`);
            this._handleDisconnected('idle', 'session exited');
        };
        this.client.onError = (message) => {
            this.renderer?.writeln(`\r\n\x1b[31m[error: ${message}]\x1b[0m`);
            this._handleDisconnected('error', `error: ${message}`);
        };
        this.client.onClose = () => {
            this._handleDisconnected('idle', 'disconnected');
            this.chrome.reset();
            if (this.splash) this.splash.reset();
        };
    }

    _handleDisconnected(state, label) {
        this._setStatus(state, label);
        this._setButtonState(false);
    }

    _setButtonState(connected) {
        if (this.connectBtn) this.connectBtn.disabled = connected;
        if (this.disconnectBtn) this.disconnectBtn.disabled = !connected;
        if (this.searchBtn) this.searchBtn.disabled = !connected;
        if (this.copyBtn) this.copyBtn.disabled = !connected;
    }

    _setStatus(state, label) {
        if (!this.statusEl) return;
        this.statusEl.dataset.state = state;
        this.statusEl.textContent = label;
    }

    _insertCommand(commandText) {
        if (!commandText) return;
        if (!this.client.connected) {
            this._setStatus('idle', 'connect to insert');
            return;
        }
        this.client.sendInput(commandText);
    }

    _toggleSearch() {
        if (!this.search) return;
        this.search.toggle();
    }

    _copySelection() {
        if (!this.renderer) return;
        const sel = this.renderer.term?.getSelection();
        if (!sel) {
            this.chrome.flashCopyToast(0);
            return;
        }
        navigator.clipboard.writeText(sel).then(() => {
            this.chrome.flashCopyToast(sel.length);
        }).catch(() => {});
    }

    _maybeGlobalShortcut(event) {
        if (!this.renderer) return;
        if (!this.root.contains(document.activeElement) && document.activeElement !== document.body) {
            return;
        }
        if (event.ctrlKey && event.shiftKey && event.key.toLowerCase() === 'f') {
            event.preventDefault();
            this._toggleSearch();
        }
    }
}

window.TerminalPanelController = TerminalPanelController;
