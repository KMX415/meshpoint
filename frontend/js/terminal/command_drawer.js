/**
 * Command drawer renderer for the terminal.
 *
 * Single responsibility: pull the curated command catalog from
 * ``GET /api/terminal/commands``, group by category, render a list
 * of buttons, and emit an ``insert`` callback when the operator picks
 * one. Dangerous entries route through ``DangerousModal`` for typed
 * confirmation before the callback fires.
 */

class CommandDrawer {
    constructor(rootEl, options = {}) {
        this.root = rootEl;
        this.toggleBtn = options.toggleBtn || null;
        this.closeBtn = options.closeBtn || null;
        this.listEl = rootEl.querySelector('[data-term-command-list]');
        this.modal = options.modal || new window.DangerousModal();
        this.onInsert = options.onInsert || (() => {});
        this._open = false;
    }

    bind() {
        this.toggleBtn?.addEventListener('click', () => this.toggle());
        this.closeBtn?.addEventListener('click', () => this.close());
    }

    toggle() {
        this._open ? this.close() : this.open();
    }

    open() {
        this._open = true;
        this.root.setAttribute('aria-hidden', 'false');
        this.root.classList.add('terminal-drawer--open');
        this.toggleBtn?.setAttribute('aria-expanded', 'true');
    }

    close() {
        this._open = false;
        this.root.setAttribute('aria-hidden', 'true');
        this.root.classList.remove('terminal-drawer--open');
        this.toggleBtn?.setAttribute('aria-expanded', 'false');
    }

    async load() {
        try {
            const response = await fetch('/api/terminal/commands', {
                credentials: 'same-origin',
            });
            if (!response.ok) {
                this._renderError(`Could not load commands (HTTP ${response.status})`);
                return;
            }
            const body = await response.json();
            this._render(body.commands || [], body.categories || []);
        } catch (_e) {
            this._renderError('Network error loading commands.');
        }
    }

    _render(commands, categories) {
        this.listEl.innerHTML = '';
        const grouped = new Map(categories.map((cat) => [cat, []]));
        commands.forEach((cmd) => {
            if (!grouped.has(cmd.category)) grouped.set(cmd.category, []);
            grouped.get(cmd.category).push(cmd);
        });

        grouped.forEach((entries, cat) => {
            if (!entries.length) return;
            const group = document.createElement('div');
            group.className = 'terminal-drawer__group';
            group.innerHTML = `<h4 class="terminal-drawer__category">${this._escape(cat)}</h4>`;
            const list = document.createElement('div');
            list.className = 'terminal-drawer__buttons';
            entries.forEach((entry) => list.appendChild(this._renderEntry(entry)));
            group.appendChild(list);
            this.listEl.appendChild(group);
        });
    }

    _renderEntry(entry) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'terminal-drawer__button'
            + (entry.dangerous ? ' terminal-drawer__button--danger' : '');
        button.title = entry.description || entry.command;
        button.innerHTML = `
            <span class="terminal-drawer__button-label">${this._escape(entry.label)}</span>
            <span class="terminal-drawer__button-cmd"><code>${this._escape(entry.command)}</code></span>
            <span class="terminal-drawer__button-desc">${this._escape(entry.description || '')}</span>
        `;
        button.addEventListener('click', () => this._handleClick(entry));
        return button;
    }

    async _handleClick(entry) {
        if (entry.dangerous) {
            const ok = await this.modal.confirm(entry);
            if (!ok) return;
        }
        this.onInsert(entry.command);
    }

    _renderError(message) {
        this.listEl.innerHTML = `<p class="terminal-drawer__error">${this._escape(message)}</p>`;
    }

    _escape(value) {
        return String(value || '').replace(/[&<>"']/g, (c) => (
            { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
        ));
    }
}

window.CommandDrawer = CommandDrawer;
