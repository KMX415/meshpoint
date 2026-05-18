/**
 * Reusable per-page init checklist.
 *
 * Renders a small console-style checklist that ticks through a list
 * of named tasks while the page boots. Each task fades in, runs its
 * (async) work, then gets its check mark and dims. When the last
 * task settles, the whole checklist fades out and reveals the page
 * content underneath.
 *
 * Why: pages that quietly snap into populated content feel dead.
 * 200-400 ms of narration ("Initializing... Drawing... Ready.")
 * masks first-load latency we already pay and signals that the
 * system is alive.
 *
 * Usage:
 *
 *     const checklist = new InitChecklist(hostEl, [
 *         { label: 'Reading config',    run: () => api.config() },
 *         { label: 'Parsing presets',   run: () => Promise.resolve() },
 *         { label: 'Drawing readouts',  run: () => paint() },
 *     ]);
 *     await checklist.run();
 *
 * Each `run` callback can be async or sync. Errors are caught and
 * surfaced as a red 'x' on the failing line; subsequent steps still
 * execute so the page is never left half-booted.
 */
class InitChecklist {
    constructor(hostEl, items, options = {}) {
        this._host = hostEl;
        this._items = items || [];
        this._minStepDelay = options.minStepDelay ?? 80;
        this._fadeOutDelay = options.fadeOutDelay ?? 220;
        this._root = null;
    }

    async run() {
        if (!this._host || this._items.length === 0) return;
        this._mount();
        for (let i = 0; i < this._items.length; i++) {
            const item = this._items[i];
            const row = this._root.children[i];
            if (!row) continue;
            row.classList.add('init-checklist__row--active');
            const start = performance.now();
            let ok = true;
            try {
                if (typeof item.run === 'function') await item.run();
            } catch (err) {
                console.error('Init step failed:', item.label, err);
                ok = false;
            }
            const elapsed = performance.now() - start;
            if (elapsed < this._minStepDelay) {
                await _wait(this._minStepDelay - elapsed);
            }
            row.classList.remove('init-checklist__row--active');
            row.classList.add(
                ok
                    ? 'init-checklist__row--done'
                    : 'init-checklist__row--error',
            );
            const mark = row.querySelector('.init-checklist__mark');
            if (mark) mark.textContent = ok ? '✓' : '✕';
        }
        await _wait(this._fadeOutDelay);
        this._root.classList.add('init-checklist--leaving');
        setTimeout(() => this._unmount(), 240);
    }

    _mount() {
        const root = document.createElement('div');
        root.className = 'init-checklist';
        root.setAttribute('role', 'status');
        root.setAttribute('aria-live', 'polite');
        root.innerHTML = this._items.map((item) => `
            <div class="init-checklist__row">
                <span class="init-checklist__mark" aria-hidden="true"></span>
                <span class="init-checklist__label">${_escapeHtml(item.label)}</span>
            </div>
        `).join('');
        // Stagger the row fade-in via per-row animation-delay.
        Array.from(root.children).forEach((row, i) => {
            row.style.animationDelay = `${i * 35}ms`;
        });
        this._host.appendChild(root);
        this._root = root;
    }

    _unmount() {
        if (this._root && this._root.parentNode) {
            this._root.parentNode.removeChild(this._root);
            this._root = null;
        }
    }
}

function _wait(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}

function _escapeHtml(str) {
    const el = document.createElement('span');
    el.textContent = str || '';
    return el.innerHTML;
}

window.InitChecklist = InitChecklist;
