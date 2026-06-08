/**
 * Confirmation modal for high-impact terminal commands.
 *
 * Single responsibility: when the operator clicks a command that needs
 * extra confirmation, render a modal showing the command and a description
 * with a Confirm/Cancel pair. Enter confirms, Esc cancels.
 *
 * The class is self-contained: it injects its own DOM on first use,
 * so the rest of the dashboard does not need to ship matching markup.
 */

class DangerousModal {
    constructor() {
        this._root = null;
        this._titleEl = null;
        this._descEl = null;
        this._codeEl = null;
        this._confirmBtn = null;
        this._cancelBtn = null;
        this._typedWrap = null;
        this._typedInput = null;
        this._typedToken = null;
        this._currentResolver = null;
    }

    _ensureMounted() {
        if (this._root) return;
        const root = document.createElement('div');
        root.className = 'danger-modal';
        root.setAttribute('aria-hidden', 'true');
        root.innerHTML = `
            <div class="danger-modal__backdrop" data-danger-backdrop></div>
            <div class="danger-modal__sheet" role="dialog" aria-modal="true">
                <h3 class="danger-modal__title" data-danger-title>Confirm</h3>
                <p class="danger-modal__desc" data-danger-desc></p>
                <pre class="danger-modal__code" data-danger-code></pre>
                <label class="danger-modal__typed" data-danger-typed-wrap hidden>
                    <span data-danger-typed-label></span>
                    <input type="text" class="danger-modal__typed-input" data-danger-typed-input autocomplete="off" spellcheck="false" />
                </label>
                <div class="danger-modal__actions">
                    <button type="button" class="terminal-button terminal-button--ghost" data-danger-cancel>Cancel</button>
                    <button type="button" class="terminal-button terminal-button--danger" data-danger-confirm>Confirm</button>
                </div>
            </div>
        `;
        document.body.appendChild(root);
        this._root = root;
        this._titleEl = root.querySelector('[data-danger-title]');
        this._descEl = root.querySelector('[data-danger-desc]');
        this._codeEl = root.querySelector('[data-danger-code]');
        this._confirmBtn = root.querySelector('[data-danger-confirm]');
        this._cancelBtn = root.querySelector('[data-danger-cancel]');
        this._typedWrap = root.querySelector('[data-danger-typed-wrap]');
        this._typedInput = root.querySelector('[data-danger-typed-input]');
        this._typedLabel = root.querySelector('[data-danger-typed-label]');
        const backdrop = root.querySelector('[data-danger-backdrop]');

        this._confirmBtn.addEventListener('click', () => this._resolve(true));
        this._typedInput.addEventListener('input', () => this._syncTypedConfirm());
        this._cancelBtn.addEventListener('click', () => this._resolve(false));
        backdrop.addEventListener('click', () => this._resolve(false));
        document.addEventListener('keydown', (event) => {
            if (!this._currentResolver) return;
            if (event.key === 'Escape') {
                this._resolve(false);
            } else if (event.key === 'Enter' && !this._confirmBtn.disabled) {
                event.preventDefault();
                this._resolve(true);
            }
        });
    }

    /**
     * Returns a Promise that resolves to ``true`` when the user
     * clicks Confirm (or presses Enter), ``false`` otherwise.
     */
    confirm({ label, command, description, typedPhrase }) {
        this._ensureMounted();
        const labelText = (label || '').trim() || 'Confirm';
        this._titleEl.textContent = `Confirm: ${labelText}`;
        this._descEl.textContent = description || 'This command can leave the host in a degraded state.';
        this._codeEl.textContent = command || '';
        this._codeEl.style.display = command ? '' : 'none';
        this._typedToken = (typedPhrase || '').trim() || null;
        if (this._typedToken) {
            this._typedWrap.hidden = false;
            this._typedLabel.textContent = `Type ${this._typedToken} to confirm:`;
            this._typedInput.value = '';
            this._confirmBtn.disabled = true;
        } else {
            this._typedWrap.hidden = true;
            this._typedInput.value = '';
            this._confirmBtn.disabled = false;
        }
        this._show();
        setTimeout(() => {
            if (this._typedToken) this._typedInput.focus();
            else this._confirmBtn.focus();
        }, 50);
        return new Promise((resolve) => { this._currentResolver = resolve; });
    }

    _syncTypedConfirm() {
        if (!this._typedToken) {
            this._confirmBtn.disabled = false;
            return;
        }
        this._confirmBtn.disabled = this._typedInput.value.trim() !== this._typedToken;
    }

    _show() {
        this._root.setAttribute('aria-hidden', 'false');
        this._root.classList.add('danger-modal--open');
    }

    _hide() {
        this._root.setAttribute('aria-hidden', 'true');
        this._root.classList.remove('danger-modal--open');
    }

    _resolve(value) {
        if (value && this._typedToken
            && this._typedInput.value.trim() !== this._typedToken) {
            return;
        }
        const resolver = this._currentResolver;
        this._currentResolver = null;
        this._typedToken = null;
        this._hide();
        if (resolver) resolver(value);
    }
}

window.DangerousModal = DangerousModal;
