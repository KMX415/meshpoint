/**
 * Settings → Updates panel controller.
 *
 * Single responsibility: pull the release-channel list from the
 * backend, render the picker, fire ``POST /api/update/apply`` when
 * the operator commits, and forward the structured result to
 * ``UpdateLogView`` for display. Rollback uses the pre-update SHA
 * captured by the apply call.
 *
 * The class is intentionally chatty in the UI: applying an update
 * is a destructive operation, so we surface every state transition
 * (loading channels, applying, success, failure) so the operator
 * always knows what just happened.
 */

class UpdatePanelController {
    constructor(rootEl) {
        this.root = rootEl;
        this.channelSelect = rootEl.querySelector('[data-update-channel]');
        this.customRow = rootEl.querySelector('[data-update-custom-row]');
        this.customInput = rootEl.querySelector('[data-update-custom-branch]');
        this.applyBtn = rootEl.querySelector('[data-update-apply]');
        this.rollbackBtn = rootEl.querySelector('[data-update-rollback]');
        this.statusEl = rootEl.querySelector('[data-update-status]');
        this.descriptionEl = rootEl.querySelector('[data-update-description]');
        this.localVersionEl = rootEl.querySelector('[data-update-local-version]');
        this.remoteVersionEl = rootEl.querySelector('[data-update-remote-version]');
        this.logView = new window.UpdateLogView(
            rootEl.querySelector('[data-update-log]')
        );
        this.releaseNotesView = new window.ReleaseNotesView(
            rootEl.querySelector('[data-update-release-notes]')
        );
        this._channels = [];
        this._lastResult = null;
        this._releaseNotesToken = 0;
    }

    bind() {
        this.channelSelect?.addEventListener('change', () => this._onChannelChanged());
        this.applyBtn?.addEventListener('click', () => this._apply());
        this.rollbackBtn?.addEventListener('click', () => this._rollback());
    }

    async refresh() {
        await Promise.all([
            this._loadChannels(),
            this._loadVersionStatus(),
        ]);
    }

    async _loadChannels() {
        try {
            const response = await fetch('/api/update/channels', {
                credentials: 'same-origin',
            });
            if (!response.ok) {
                this._setStatus('error', `Could not load channels (HTTP ${response.status}).`);
                return;
            }
            const body = await response.json();
            this._channels = body.channels || [];
            this._renderChannelOptions();
        } catch (_e) {
            this._setStatus('error', 'Network error loading channels.');
        }
    }

    async _loadVersionStatus() {
        try {
            const response = await fetch('/api/device/update-check', {
                credentials: 'same-origin',
            });
            if (!response.ok) return;
            const body = await response.json();
            if (this.localVersionEl) {
                this.localVersionEl.textContent = body.local_version || '--';
            }
            if (this.remoteVersionEl) {
                this.remoteVersionEl.textContent = body.remote_version || 'unknown';
            }
        } catch (_e) { /* badge handles its own error path */ }
    }

    _renderChannelOptions() {
        if (!this.channelSelect) return;
        this.channelSelect.innerHTML = this._channels
            .map((c) => `<option value="${this._escape(c.id)}">${this._escape(c.label)}</option>`)
            .join('');
        this._onChannelChanged();
    }

    _onChannelChanged() {
        const channel = this._currentChannel();
        if (!channel) return;
        if (this.descriptionEl) {
            this.descriptionEl.textContent = channel.description || '';
            this.descriptionEl.dataset.tier = channel.tier;
        }
        if (this.customRow) {
            this.customRow.style.display = channel.tier === 'custom' ? '' : 'none';
        }
        this._loadReleaseNotes(channel);
    }

    async _loadReleaseNotes(channel) {
        if (!this.releaseNotesView) return;
        const token = ++this._releaseNotesToken;
        if (channel.tier === 'custom') {
            this.releaseNotesView.renderEmpty(channel.label);
            return;
        }
        try {
            const response = await fetch(
                `/api/update/release_notes?channel_id=${encodeURIComponent(channel.id)}`,
                { credentials: 'same-origin' },
            );
            if (token !== this._releaseNotesToken) return;
            if (!response.ok) {
                this.releaseNotesView.renderError(
                    `Could not load release notes (HTTP ${response.status}).`
                );
                return;
            }
            const body = await response.json();
            if (token !== this._releaseNotesToken) return;
            this.releaseNotesView.render(body);
        } catch (_e) {
            if (token === this._releaseNotesToken) {
                this.releaseNotesView.renderError('Network error loading release notes.');
            }
        }
    }

    async _apply() {
        const channel = this._currentChannel();
        if (!channel) return;
        const customBranch = channel.tier === 'custom'
            ? (this.customInput?.value || '').trim()
            : undefined;
        if (channel.tier === 'custom' && !customBranch) {
            this._setStatus('error', 'Custom channel requires a branch name.');
            return;
        }
        const confirmed = window.confirm(
            `Apply update from "${channel.label}"? `
            + 'The service will restart at the end of the chain.'
        );
        if (!confirmed) return;
        this._setStatus('pending', 'Applying update… this may take several minutes.');
        this.applyBtn.disabled = true;
        this.rollbackBtn.disabled = true;
        try {
            const response = await fetch('/api/update/apply', {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    channel_id: channel.id,
                    custom_branch: customBranch,
                }),
            });
            const body = await response.json().catch(() => ({}));
            if (!response.ok) {
                this._setStatus('error', `Apply failed (HTTP ${response.status}).`);
                return;
            }
            this._lastResult = body;
            this.logView.render(body);
            if (body.success) {
                this._setStatus('success', `Applied to ${body.target_branch}.`);
            } else {
                this._setStatus('error', `Failed at ${body.failed_step}.`);
            }
        } catch (_e) {
            this._setStatus('error', 'Network error during apply.');
        } finally {
            this.applyBtn.disabled = false;
            this.rollbackBtn.disabled = !(this._lastResult && this._lastResult.pre_update_sha);
        }
    }

    async _rollback() {
        if (!this._lastResult || !this._lastResult.pre_update_sha) return;
        const sha = this._lastResult.pre_update_sha;
        const confirmed = window.confirm(
            `Roll back to ${sha.slice(0, 8)}? The service will restart.`
        );
        if (!confirmed) return;
        this._setStatus('pending', 'Rolling back…');
        this.rollbackBtn.disabled = true;
        this.applyBtn.disabled = true;
        try {
            const response = await fetch('/api/update/rollback', {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ sha }),
            });
            const body = await response.json().catch(() => ({}));
            if (!response.ok) {
                this._setStatus('error', `Rollback failed (HTTP ${response.status}).`);
                return;
            }
            this.logView.render(body);
            this._setStatus(
                body.success ? 'success' : 'error',
                body.success ? `Rolled back to ${sha.slice(0, 8)}.` : 'Rollback failed.',
            );
        } catch (_e) {
            this._setStatus('error', 'Network error during rollback.');
        } finally {
            this.applyBtn.disabled = false;
        }
    }

    _currentChannel() {
        const id = this.channelSelect?.value;
        return this._channels.find((c) => c.id === id) || null;
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

window.UpdatePanelController = UpdatePanelController;
