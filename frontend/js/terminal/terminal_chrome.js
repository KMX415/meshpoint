/**
 * Terminal title bar chrome.
 *
 * Single responsibility: render the small "tab strip" above the
 * xterm host that shows the live session metadata (hostname, PID,
 * shell, connection state) and the toast that fires when the user
 * copies a selection. No xterm interaction; the panel controller
 * pushes session info in via :meth:`setSession` and the renderer
 * forwards copy events via :meth:`flashCopyToast`.
 *
 * The chrome owns these hooks:
 *
 *   - hostname badge   : ``data-term-host``
 *   - PID badge        : ``data-term-pid``
 *   - shell label      : ``data-term-shell``
 *   - copy toast       : ``data-term-toast``  (transient, ARIA-live)
 *
 * Status pill state ('idle' | 'connecting' | 'connected' | 'error')
 * is owned by the panel controller via the existing
 * ``[data-term-status]`` element so we keep a single source of
 * truth and the chrome never disagrees with the panel.
 */

class TerminalChrome {
    constructor(rootEl) {
        this.root = rootEl;
        this.hostBadge = rootEl.querySelector('[data-term-host]');
        this.pidBadge = rootEl.querySelector('[data-term-pid]');
        this.shellBadge = rootEl.querySelector('[data-term-shell]');
        this.toastEl = rootEl.querySelector('[data-term-toast]');
        this._toastTimer = null;
        this.reset();
    }

    reset() {
        this._setBadge(this.hostBadge, '--');
        this._setBadge(this.pidBadge, '--');
        this._setBadge(this.shellBadge, '--');
    }

    setSession({ hostname, pid, shell, user } = {}) {
        if (hostname) {
            const label = user ? `${user}@${hostname}` : hostname;
            this._setBadge(this.hostBadge, label);
        }
        if (pid != null) {
            this._setBadge(this.pidBadge, `pid ${pid}`);
        }
        if (shell) {
            this._setBadge(this.shellBadge, this._shellLabel(shell));
        }
    }

    flashCopyToast(byteCount = 0) {
        if (!this.toastEl) return;
        const label = byteCount
            ? `copied ${byteCount} char${byteCount === 1 ? '' : 's'}`
            : 'nothing selected';
        this.toastEl.textContent = label;
        this.toastEl.classList.add('terminal-toast--visible');
        if (this._toastTimer) clearTimeout(this._toastTimer);
        this._toastTimer = setTimeout(() => {
            this.toastEl.classList.remove('terminal-toast--visible');
        }, 1400);
    }

    _setBadge(badgeEl, text) {
        if (!badgeEl) return;
        badgeEl.textContent = text;
    }

    _shellLabel(shell) {
        if (!shell) return '--';
        const trimmed = String(shell).split('/').pop() || shell;
        return trimmed;
    }
}

window.TerminalChrome = TerminalChrome;
