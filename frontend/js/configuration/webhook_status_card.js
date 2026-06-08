/**
 * Configuration → Advanced — webhook rules status and test panel (PR 11).
 *
 * Read-only view of ``webhooks.rules`` from config plus live last-fired
 * timestamps from ``GET /api/webhooks/status``. Test sends a dummy POST
 * via ``POST /api/webhooks/test/{rule_name}``.
 */

class WebhookStatusCard {
    constructor(api) {
        this._api = api;
        this._root = null;
        this._status = null;
        this._refreshTimer = null;
    }

    mount(root) {
        this._root = root;
        this._root.innerHTML = `
            <article class="cfg-card" id="cfg-webhooks">
                <header class="cfg-card__head">
                    <h3 class="cfg-card__title">Webhooks</h3>
                    <p class="cfg-card__hint">
                        Outbound HTTP rules are defined in <code>local.yaml</code>
                        under <code>webhooks</code>. This panel shows live status
                        and lets you send a <strong>dummy test POST</strong> to
                        verify each URL from the Pi.
                    </p>
                </header>
                <div class="cfg-webhook-summary" data-wh-summary></div>
                <div class="cfg-webhook-table-wrap">
                    <table class="cfg-webhook-table" data-wh-table>
                        <thead>
                            <tr>
                                <th>Rule</th>
                                <th>Event</th>
                                <th>Host</th>
                                <th>Last fired</th>
                                <th>Result</th>
                                <th></th>
                            </tr>
                        </thead>
                        <tbody data-wh-body>
                            <tr><td colspan="6">Loading…</td></tr>
                        </tbody>
                    </table>
                </div>
                <p class="cfg-status" data-wh-status aria-live="polite"></p>
            </article>
        `;
        this._summaryEl = this._root.querySelector('[data-wh-summary]');
        this._bodyEl = this._root.querySelector('[data-wh-body]');
        this._statusEl = this._root.querySelector('[data-wh-status]');
        this._wireActions();
    }

    async render(_config) {
        await this._loadStatus();
        this._renderSummary();
        this._renderTable();
        this._startRefresh();
    }

    _wireActions() {
        this._root.addEventListener('click', (e) => {
            const btn = e.target.closest('[data-wh-test]');
            if (!btn) return;
            e.preventDefault();
            const name = btn.dataset.whTest;
            if (name) this._runTest(name, btn);
        });
    }

    async _loadStatus() {
        const data = await this._api.get('/api/webhooks/status');
        this._status = data || { enabled: false, engine_running: false, rules: [] };
    }

    _renderSummary() {
        const s = this._status || {};
        const enabled = s.enabled ? 'enabled' : 'disabled';
        const running = s.engine_running ? 'running' : 'stopped';
        const count = (s.rules || []).length;
        this._summaryEl.innerHTML = `
            <p class="cfg-card__hint">
                Engine: <strong>${this._api.escape(enabled)}</strong>
                · worker: <strong>${this._api.escape(running)}</strong>
                · ${count} rule${count === 1 ? '' : 's'} in config
            </p>
        `;
    }

    _renderTable() {
        const rules = (this._status && this._status.rules) || [];
        if (!rules.length) {
            this._bodyEl.innerHTML = `
                <tr><td colspan="6" class="cfg-webhook-empty">
                    No webhook rules in config. Add rules under
                    <code>webhooks.rules</code> in <code>local.yaml</code>.
                </td></tr>
            `;
            return;
        }

        this._bodyEl.innerHTML = rules.map((rule) => {
            const last = this._formatLastFired(rule);
            const result = this._formatResult(rule);
            const badge = rule.deferred
                ? '<span class="cfg-webhook-badge cfg-webhook-badge--muted">reserved</span>'
                : (rule.active
                    ? '<span class="cfg-webhook-badge cfg-webhook-badge--ok">active</span>'
                    : '<span class="cfg-webhook-badge cfg-webhook-badge--muted">inactive</span>');
            const testLabel = rule.deferred ? '—' : (
                `<button type="button" class="terminal-button terminal-button--small"
                    data-wh-test="${this._api.escape(rule.name)}">Test</button>`
            );
            return `<tr>
                <td>${this._api.escape(rule.name)} ${badge}</td>
                <td><code>${this._api.escape(rule.event)}</code></td>
                <td>${this._api.escape(rule.url_host || '—')}</td>
                <td>${this._api.escape(last)}</td>
                <td>${result}</td>
                <td>${testLabel}</td>
            </tr>`;
        }).join('');
    }

    _formatLastFired(rule) {
        if (!rule.last_fired_at) return '—';
        try {
            const d = new Date(rule.last_fired_at);
            const stamp = d.toLocaleString();
            return rule.last_was_test ? `${stamp} (test)` : stamp;
        } catch (_e) {
            return rule.last_fired_at;
        }
    }

    _formatResult(rule) {
        if (!rule.last_result) return '—';
        const cls = rule.last_result === 'success'
            ? 'cfg-webhook-result--ok'
            : 'cfg-webhook-result--err';
        const code = rule.last_status_code != null
            ? ` HTTP ${rule.last_status_code}`
            : '';
        const err = rule.last_error
            ? ` — ${this._api.escape(rule.last_error)}`
            : '';
        return `<span class="${cls}">${this._api.escape(rule.last_result)}${code}</span>${err}`;
    }

    async _runTest(ruleName, btn) {
        btn.disabled = true;
        this._setStatus('Sending dummy test POST…', '');
        const result = await this._api.post(
            `/api/webhooks/test/${encodeURIComponent(ruleName)}`,
            {},
        );
        if (result) {
            const ok = result.result === 'success';
            this._setStatus(
                ok
                    ? `Test OK for ${ruleName} (HTTP ${result.status_code ?? '—'})`
                    : `Test failed for ${ruleName}: ${result.error || result.result}`,
                ok ? 'ok' : 'err',
            );
            await this._loadStatus();
            this._renderTable();
        } else {
            this._setStatus(`Test request failed for ${ruleName}`, 'err');
        }
        btn.disabled = false;
    }

    _setStatus(msg, kind) {
        this._statusEl.textContent = msg;
        this._statusEl.className = 'cfg-status'
            + (kind === 'ok' ? ' cfg-status--ok' : '')
            + (kind === 'err' ? ' cfg-status--err' : '');
    }

    _startRefresh() {
        if (this._refreshTimer) return;
        this._refreshTimer = setInterval(async () => {
            const section = document.querySelector('[data-section="configuration/advanced"]');
            if (!section || !section.classList.contains('section--active')) {
                clearInterval(this._refreshTimer);
                this._refreshTimer = null;
                return;
            }
            await this._loadStatus();
            this._renderTable();
        }, 15_000);
    }
}

window.WebhookStatusCard = WebhookStatusCard;
