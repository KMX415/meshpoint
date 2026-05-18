/**
 * Settings → Dangerous panel controller.
 *
 * Single responsibility: load the action catalog from
 * ``GET /api/dangerous/actions``, render one card per action, and
 * route every press through ``DangerousModal`` (typed-confirmation)
 * before invoking ``POST /api/dangerous/invoke``. Live result is
 * surfaced inline next to the action so the operator sees the
 * outcome without leaving the panel.
 */

class DangerousPanelController {
    constructor(rootEl) {
        this.root = rootEl;
        this.listEl = rootEl.querySelector('[data-dangerous-list]');
        this.statusEl = rootEl.querySelector('[data-dangerous-status]');
        this.modal = new window.DangerousModal();
        this._actions = [];
    }

    bind() {}

    async refresh() {
        try {
            const response = await fetch('/api/dangerous/actions', {
                credentials: 'same-origin',
            });
            if (!response.ok) {
                this._setStatus('error', `Could not load actions (HTTP ${response.status}).`);
                return;
            }
            const body = await response.json();
            this._actions = body.actions || [];
            this._render();
        } catch (_e) {
            this._setStatus('error', 'Network error loading actions.');
        }
    }

    _render() {
        if (!this.listEl) return;
        this.listEl.innerHTML = '';
        this._actions.forEach((action) => {
            this.listEl.appendChild(this._renderCard(action));
        });
    }

    _renderCard(action) {
        const card = document.createElement('article');
        card.className = 'dangerous-card';
        card.innerHTML = `
            <header class="dangerous-card__head">
                <h3 class="dangerous-card__title">${this._escape(action.label)}</h3>
                <span class="dangerous-card__pill">irreversible</span>
            </header>
            <p class="dangerous-card__description">${this._escape(action.description)}</p>
            <div class="dangerous-card__actions">
                <button class="terminal-button terminal-button--danger" type="button" data-invoke>${this._escape(action.label)}</button>
            </div>
            <p class="dangerous-card__result" data-result aria-live="polite"></p>
        `;
        const button = card.querySelector('[data-invoke]');
        const resultEl = card.querySelector('[data-result]');
        button.addEventListener('click', () => this._invoke(action, button, resultEl));
        return card;
    }

    async _invoke(action, button, resultEl) {
        const ok = await this.modal.confirm({
            label: action.confirmation_text,
            command: action.label,
            description: action.description,
        });
        if (!ok) return;
        button.disabled = true;
        resultEl.dataset.kind = 'pending';
        resultEl.textContent = 'Invoking…';
        try {
            const response = await fetch('/api/dangerous/invoke', {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action_id: action.id }),
            });
            if (!response.ok) {
                resultEl.dataset.kind = 'error';
                resultEl.textContent = `Failed (HTTP ${response.status}).`;
                return;
            }
            const body = await response.json();
            resultEl.dataset.kind = body.success ? 'success' : 'error';
            resultEl.textContent = body.message || (body.success ? 'Done.' : 'Failed.');
        } catch (_e) {
            resultEl.dataset.kind = 'error';
            resultEl.textContent = 'Network error.';
        } finally {
            button.disabled = false;
        }
    }

    _setStatus(kind, message) {
        if (!this.statusEl) return;
        this.statusEl.dataset.kind = kind;
        this.statusEl.textContent = message;
    }

    _escape(value) {
        return String(value || '').replace(/[&<>"']/g, (c) => (
            { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
        ));
    }
}

window.DangerousPanelController = DangerousPanelController;
