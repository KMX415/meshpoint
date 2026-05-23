/**
 * Live progress UI for Settings → Updates apply / rollback.
 *
 * Driven by NDJSON stream events from the apply/rollback stream endpoints
 * (``/api/update/apply/stream``, ``/api/update/rollback/stream``) so each
 * git/install step lights up as it runs on the Pi. After the final
 * result, we poll ``/api/device/status`` when the service restarts.
 */

const APPLY_STEP_DEFS = [
    { key: 'git fetch', label: 'Fetch latest code from GitHub' },
    { key: 'git checkout', label: 'Check out release branch' },
    { key: 'git reset', label: 'Sync install tree to remote' },
    { key: 'install.sh', label: 'Run installer' },
    { key: 'restart service', label: 'Restart Meshpoint service' },
];

const ROLLBACK_STEP_DEFS = [
    { key: 'git reset', label: 'Reset install tree to prior commit' },
    { key: 'restart service', label: 'Restart Meshpoint service' },
];

class UpdateProgressView {
    constructor(rootEl) {
        this.root = rootEl;
        this._elapsedTimer = null;
        this._startedAt = 0;
        this._stepDefs = APPLY_STEP_DEFS;
    }

    start({ mode = 'apply', channelLabel = '', branch = '' } = {}) {
        if (!this.root) return;
        this._stepDefs = mode === 'rollback' ? ROLLBACK_STEP_DEFS : APPLY_STEP_DEFS;
        this._startedAt = Date.now();
        this.root.hidden = false;
        this.root.dataset.state = 'running';
        const headline = mode === 'rollback'
            ? 'Rolling back install tree'
            : `Applying update from ${this._escape(channelLabel || 'selected channel')}`;
        const branchLine = branch
            ? `<p class="update-progress__branch">Branch: <code>${this._escape(branch)}</code></p>`
            : '';
        const steps = this._stepDefs.map((def) => (
            `<li class="update-progress__step" data-step="${this._escape(def.key)}" data-status="pending">
                <span class="update-progress__step-icon" aria-hidden="true"></span>
                <span class="update-progress__step-label">${this._escape(def.label)}</span>
                <span class="update-progress__step-hint"></span>
            </li>`
        )).join('');
        this.root.innerHTML = `
            <div class="update-progress__panel">
                <header class="update-progress__head">
                    <p class="update-progress__eyebrow">Update in progress</p>
                    <h3 class="update-progress__title">${headline}</h3>
                    ${branchLine}
                </header>
                <div class="update-progress__meter" role="progressbar" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100" aria-valuetext="Update running">
                    <span class="update-progress__meter-fill" data-update-meter-fill></span>
                </div>
                <p class="update-progress__elapsed" data-update-elapsed>Elapsed: 0s</p>
                <p class="update-progress__hint">
                    Do not refresh this page. The Meshpoint is updating on the Pi; this usually takes 20–30 seconds. The connection may drop during install or restart; the page will wait for the service to come back.
                </p>
                <ol class="update-progress__steps">${steps}</ol>
            </div>
        `;
        this._startElapsedClock();
    }

    onStreamEvent(event) {
        if (!this.root || !event || event.type !== 'step') return;
        const phase = event.phase;
        const stepKey = event.step;
        if (phase === 'started') {
            this._setActiveStep(stepKey);
            return;
        }
        if (phase === 'completed') {
            this._setStepStatus(stepKey, 'ok');
            return;
        }
        if (phase === 'error') {
            this._setStepStatus(stepKey, 'error');
        }
    }

    _setActiveStep(stepKey) {
        if (!this.root) return;
        const rows = this.root.querySelectorAll('.update-progress__step');
        rows.forEach((row) => {
            const hint = row.querySelector('.update-progress__step-hint');
            const isActive = row.dataset.step === stepKey;
            if (isActive) {
                row.dataset.status = 'active';
                if (hint) hint.textContent = 'running…';
            } else if (row.dataset.status === 'active') {
                row.dataset.status = 'pending';
                if (hint) hint.textContent = '';
            }
        });
        this._updateMeterProgress();
    }

    _setStepStatus(stepKey, status) {
        const row = this.root?.querySelector(`[data-step="${stepKey}"]`);
        if (!row) return;
        row.dataset.status = status;
        const hint = row.querySelector('.update-progress__step-hint');
        if (hint) hint.textContent = '';
        this._updateMeterProgress();
    }

    _updateMeterProgress() {
        const fill = this.root?.querySelector('[data-update-meter-fill]');
        const meter = this.root?.querySelector('.update-progress__meter');
        if (!fill || !meter) return;
        const total = this._stepDefs.length;
        const done = this.root.querySelectorAll(
            '.update-progress__step[data-status="ok"], .update-progress__step[data-status="error"]',
        ).length;
        const active = this.root.querySelector('.update-progress__step[data-status="active"]');
        const pct = total
            ? Math.min(100, Math.round(((done + (active ? 0.35 : 0)) / total) * 100))
            : 0;
        fill.style.width = `${pct}%`;
        fill.classList.toggle('update-progress__meter-fill--indeterminate', pct === 0 && !!active);
        meter.setAttribute('aria-valuenow', String(pct));
    }

    setElapsedSeconds(seconds) {
        const el = this.root?.querySelector('[data-update-elapsed]');
        if (!el) return;
        const rounded = Math.max(0, Math.floor(seconds));
        el.textContent = `Elapsed: ${rounded}s`;
    }

    complete(result) {
        if (!this.root || !result) return;
        const logByStep = new Map((result.log || []).map((entry) => [entry.step, entry]));
        let sawError = false;
        for (const def of this._stepDefs) {
            const row = this.root.querySelector(`[data-step="${def.key}"]`);
            const entry = logByStep.get(def.key);
            if (!row) continue;
            const hint = row.querySelector('.update-progress__step-hint');
            if (hint) hint.remove();
            if (!entry) {
                row.dataset.status = sawError ? 'skipped' : 'pending';
                continue;
            }
            if (entry.returncode === 0) {
                row.dataset.status = 'ok';
            } else {
                row.dataset.status = 'error';
                sawError = true;
            }
        }
        this._stopElapsedClock();
        this.root.dataset.state = result.success ? 'done' : 'failed';
        const hint = this.root.querySelector('.update-progress__hint');
        if (hint) {
            hint.textContent = result.success
                ? 'Steps finished on the device. Waiting for the dashboard to come back if the service restarted.'
                : `Stopped at "${result.failed_step || 'unknown step'}". See the log below for command output.`;
        }
    }

    async waitForServiceRecovery({ timeoutMs = 90000, intervalMs = 2000 } = {}) {
        if (!this.root) return false;
        this.root.dataset.state = 'reconnecting';
        const hint = this.root.querySelector('.update-progress__hint');
        if (hint) {
            hint.textContent = 'Meshpoint is restarting. Reconnecting to the dashboard…';
        }
        const deadline = Date.now() + timeoutMs;
        while (Date.now() < deadline) {
            try {
                const response = await fetch('/api/device/status', {
                    credentials: 'same-origin',
                    cache: 'no-store',
                });
                if (response.ok) {
                    this.root.dataset.state = 'online';
                    if (hint) {
                        hint.textContent = 'Dashboard is back online. Reloading to pick up the new version.';
                    }
                    return true;
                }
            } catch (_e) { /* service restart drops the connection */ }
            await new Promise((resolve) => setTimeout(resolve, intervalMs));
        }
        if (hint) {
            hint.textContent = 'Still waiting for the dashboard. If this lasts more than a minute, open the page again or check `journalctl -u meshpoint` over SSH.';
        }
        return false;
    }

    hide() {
        this._stopElapsedClock();
        if (!this.root) return;
        this.root.hidden = true;
        this.root.innerHTML = '';
        this.root.removeAttribute('data-state');
    }

    _startElapsedClock() {
        this._stopElapsedClock();
        this._elapsedTimer = window.setInterval(() => {
            const seconds = (Date.now() - this._startedAt) / 1000;
            this.setElapsedSeconds(seconds);
        }, 500);
    }

    _stopElapsedClock() {
        if (this._elapsedTimer) {
            window.clearInterval(this._elapsedTimer);
            this._elapsedTimer = null;
        }
    }

    _escape(value) {
        return String(value || '').replace(/[&<>"']/g, (c) => (
            { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
        ));
    }
}

window.UpdateProgressView = UpdateProgressView;
window.UPDATE_APPLY_STEP_DEFS = APPLY_STEP_DEFS;
