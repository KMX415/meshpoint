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

const UPDATE_CHANNEL_STORAGE_KEY = 'meshpoint_update_channel_id';
const UPDATE_CUSTOM_BRANCH_STORAGE_KEY = 'meshpoint_update_custom_branch';
/** Retired picker ids remapped when the dashboard reloads after a release. */
const UPDATE_CHANNEL_ALIASES = { 'rc-074': 'rc-075', 'rc-075': 'rc-076' };

class UpdatePanelController {
    constructor(rootEl) {
        this.root = rootEl;
        this.channelSelect = rootEl.querySelector('[data-update-channel]');
        this.customRow = rootEl.querySelector('[data-update-custom-row]');
        this.customInput = rootEl.querySelector('[data-update-custom-branch]');
        this.checkBtn = rootEl.querySelector('[data-update-check]');
        this.applyBtn = rootEl.querySelector('[data-update-apply]');
        this.rollbackBtn = rootEl.querySelector('[data-update-rollback]');
        this.rollbackHintEl = rootEl.querySelector('[data-update-rollback-hint]');
        this.syncHintEl = rootEl.querySelector('[data-update-sync-hint]');
        this.statusEl = rootEl.querySelector('[data-update-status]');
        this.descriptionEl = rootEl.querySelector('[data-update-description]');
        this.localVersionEl = rootEl.querySelector('[data-update-local-version]');
        this.localBranchEl = rootEl.querySelector('[data-update-local-branch]');
        this.remoteVersionEl = rootEl.querySelector('[data-update-remote-version]');
        this.remoteBranchEl = rootEl.querySelector('[data-update-remote-branch]');
        this.logView = new window.UpdateLogView(
            rootEl.querySelector('[data-update-log]')
        );
        this.progressView = new window.UpdateProgressView(
            rootEl.querySelector('[data-update-progress]')
        );
        this.releaseNotesView = new window.ReleaseNotesView(
            rootEl.querySelector('[data-update-release-notes]')
        );
        this._channels = [];
        this._installStatus = null;
        this._lastResult = null;
        this._releaseNotesToken = 0;
    }

    bind() {
        this.channelSelect?.addEventListener('change', () => this._onChannelChanged());
        this.checkBtn?.addEventListener('click', () => this._checkForUpdates());
        this.applyBtn?.addEventListener('click', () => this._apply());
        this.rollbackBtn?.addEventListener('click', () => this._rollback());
    }

    async refresh() {
        await this._loadChannels();
        await this._loadInstallStatus();
        this._syncChannelPickerToInstall();
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

    async _loadInstallStatus() {
        try {
            const response = await fetch('/api/update/install_status', {
                credentials: 'same-origin',
            });
            if (!response.ok) return;
            this._installStatus = await response.json();
            this._renderVersionCards(this._installStatus);
            if (!this._installStatus.checked_at) {
                this._renderSyncHint(null);
            }
        } catch (_e) { /* install status is best-effort */ }
        this._syncRollbackButton();
    }

    async _checkForUpdates() {
        const channel = this._currentChannel();
        if (!channel) return;
        const customBranch = channel.tier === 'custom'
            ? (this.customInput?.value || '').trim()
            : undefined;
        if (channel.tier === 'custom' && !customBranch) {
            this._setStatus('error', 'Enter a custom branch name first.');
            return;
        }
        this._setStatus('pending', 'Fetching from GitHub…');
        if (this.checkBtn) this.checkBtn.disabled = true;
        try {
            const response = await fetch('/api/update/check', {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    channel_id: channel.id,
                    custom_branch: customBranch,
                }),
            });
            if (!response.ok) {
                this._setStatus('error', `Check failed (HTTP ${response.status}).`);
                this._renderSyncHint({ sync_error: 'request failed' });
                return;
            }
            this._installStatus = await response.json();
            this._renderVersionCards(this._installStatus);
            this._renderSyncHint(this._installStatus);
            const behind = this._installStatus.commits_behind;
            if (this._installStatus.sync_error) {
                this._setStatus('error', 'Could not reach GitHub.');
            } else if (behind != null && behind > 0) {
                this._setStatus(
                    'success',
                    `${behind} commit${behind === 1 ? '' : 's'} behind — use Apply when ready.`,
                );
            } else {
                this._setStatus('success', 'Up to date with the selected channel.');
            }
        } catch (_e) {
            this._setStatus('error', 'Network error while checking for updates.');
            this._renderSyncHint({ sync_error: 'network error' });
        } finally {
            if (this.checkBtn) this.checkBtn.disabled = false;
            this._syncRollbackButton();
        }
    }

    _renderVersionCards(status) {
        if (!status) return;
        if (this.localVersionEl) {
            this.localVersionEl.textContent = status.local_version || '--';
        }
        if (this.remoteVersionEl) {
            this.remoteVersionEl.textContent = status.remote_version || 'unknown';
        }
        if (this.localBranchEl) {
            const branch = status.install_branch || '';
            const sha = status.install_sha_short || '';
            const parts = [];
            if (branch) parts.push(branch);
            if (sha) parts.push(`@ ${sha}`);
            this.localBranchEl.textContent = parts.join(' ');
        }
        if (this.remoteBranchEl) {
            const branch = status.compare_branch || status.remote_branch || status.install_branch || '';
            const remoteSha = status.remote_sha_short || '';
            let text = branch ? `origin/${branch}` : '';
            if (remoteSha) text = text ? `${text} @ ${remoteSha}` : `@ ${remoteSha}`;
            this.remoteBranchEl.textContent = text;
        }
    }

    _renderSyncHint(status) {
        if (!this.syncHintEl) return;
        if (!status) {
            this.syncHintEl.dataset.kind = '';
            this.syncHintEl.textContent =
                'Select a channel, then check how far behind GitHub you are.';
            return;
        }
        if (status.sync_error) {
            this.syncHintEl.dataset.kind = 'error';
            this.syncHintEl.textContent = this._withLastChecked(
                `Could not fetch origin: ${status.sync_error}`,
                status,
            );
            return;
        }
        const branch = status.compare_branch || status.remote_branch || '';
        const behind = status.commits_behind;
        const ahead = status.commits_ahead;
        if (behind == null) {
            this.syncHintEl.dataset.kind = '';
            this.syncHintEl.textContent = 'Could not compare with GitHub.';
            return;
        }
        if (behind === 0 && (!ahead || ahead === 0)) {
            this.syncHintEl.dataset.kind = 'ok';
            this.syncHintEl.textContent = this._withLastChecked(
                branch
                    ? `Up to date with origin/${branch}.`
                    : 'Up to date with GitHub.',
                status,
            );
            return;
        }
        const parts = [];
        if (behind > 0) {
            parts.push(
                `${behind} commit${behind === 1 ? '' : 's'} behind origin/${branch}`,
            );
        }
        if (ahead > 0) {
            parts.push(
                `${ahead} commit${ahead === 1 ? '' : 's'} ahead of origin/${branch}`,
            );
        }
        this.syncHintEl.dataset.kind = behind > 0 ? 'behind' : '';
        this.syncHintEl.textContent = this._withLastChecked(
            parts.join(' · '),
            status,
        );
    }

    _withLastChecked(message, status) {
        const stamp = this._formatLastChecked(status?.checked_at);
        if (!stamp) return message;
        return `${message} Last checked ${stamp}.`;
    }

    _formatLastChecked(iso) {
        if (!iso) return '';
        const ms = Date.parse(iso);
        if (Number.isNaN(ms)) return '';
        const sec = Math.max(0, Math.floor((Date.now() - ms) / 1000));
        if (sec < 45) return 'just now';
        if (sec < 3600) {
            const m = Math.floor(sec / 60);
            return `${m} minute${m === 1 ? '' : 's'} ago`;
        }
        if (sec < 86400) {
            const h = Math.floor(sec / 3600);
            return `${h} hour${h === 1 ? '' : 's'} ago`;
        }
        return new Date(ms).toLocaleString();
    }

    _renderChannelOptions() {
        if (!this.channelSelect) return;
        this.channelSelect.innerHTML = this._channels
            .map((c) => `<option value="${this._escape(c.id)}">${this._escape(c.label)}</option>`)
            .join('');
    }

    _syncChannelPickerToInstall() {
        if (!this.channelSelect || !this._channels.length) return;
        const status = this._installStatus || {};
        let channelId = status.active_channel_id
            || sessionStorage.getItem(UPDATE_CHANNEL_STORAGE_KEY);
        channelId = this._normalizeChannelId(channelId);
        if (!channelId && status.install_branch) {
            const byBranch = this._channels.find(
                (c) => c.branch === status.install_branch,
            );
            if (byBranch) channelId = byBranch.id;
        }
        if (
            !channelId
            && status.install_branch === 'main'
            && this._versionAtLeast(status.local_version, [0, 7, 4])
        ) {
            const rc = this._channels.find((c) => c.tier === 'rc');
            if (rc) channelId = rc.id;
        }
        if (channelId && !this._channels.some((c) => c.id === channelId)) {
            channelId = null;
        }
        if (channelId) {
            this.channelSelect.value = channelId;
        }
        const channel = this._currentChannel();
        if (channel?.tier === 'custom') {
            const branch = status.install_branch
                || sessionStorage.getItem(UPDATE_CUSTOM_BRANCH_STORAGE_KEY)
                || '';
            if (this.customInput && branch) {
                this.customInput.value = branch;
            }
        }
        this._onChannelChanged();
    }

    _rememberChannelForReload(channel, customBranch) {
        sessionStorage.setItem(UPDATE_CHANNEL_STORAGE_KEY, channel.id);
        if (channel.tier === 'custom' && customBranch) {
            sessionStorage.setItem(UPDATE_CUSTOM_BRANCH_STORAGE_KEY, customBranch);
        } else {
            sessionStorage.removeItem(UPDATE_CUSTOM_BRANCH_STORAGE_KEY);
        }
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
        if (!this._installStatus?.checked_at
            || this._installStatus?.compare_branch !== this._compareBranchForChannel(channel)) {
            this._renderSyncHint(null);
        }
        this._loadReleaseNotes(channel);
    }

    _compareBranchForChannel(channel) {
        if (!channel) return '';
        if (channel.tier === 'custom') {
            return (this.customInput?.value || '').trim();
        }
        return channel.branch || '';
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
        this._rememberChannelForReload(channel, customBranch);
        const branch = channel.tier === 'custom' ? customBranch : (channel.branch || '');
        this.progressView?.start({
            mode: 'apply',
            channelLabel: channel.label,
            branch,
        });
        this._setStatus('pending', 'Applying update on the Meshpoint…');
        this.applyBtn.disabled = true;
        this.rollbackBtn.disabled = true;
        try {
            const body = await window.UpdateStreamClient.postNdjson(
                '/api/update/apply/stream',
                { channel_id: channel.id, custom_branch: customBranch },
                (event) => this.progressView?.onStreamEvent(event),
            );
            if (!body) {
                this.progressView?.complete({
                    success: false,
                    failed_step: 'stream',
                    log: [],
                });
                this._setStatus('error', 'Update finished without a result payload.');
                return;
            }
            await this._finishUpdateResult(body, {
                successMessage: `Applied to ${body.target_branch}.`,
                failureMessage: (b) => `Failed at ${b.failed_step}.`,
            });
        } catch (err) {
            await this._handleUpdateStreamError(err);
        } finally {
            this.applyBtn.disabled = false;
            this._syncRollbackButton();
        }
    }

    async _rollback() {
        const sha = this._rollbackSha();
        if (!sha) return;
        const confirmed = window.confirm(
            `Roll back to ${sha.slice(0, 8)}? The service will restart.`
        );
        if (!confirmed) return;
        this.progressView?.start({ mode: 'rollback', channelLabel: `commit ${sha.slice(0, 8)}` });
        this._setStatus('pending', 'Rolling back on the Meshpoint…');
        this.rollbackBtn.disabled = true;
        this.applyBtn.disabled = true;
        try {
            const body = await window.UpdateStreamClient.postNdjson(
                '/api/update/rollback/stream',
                { sha },
                (event) => this.progressView?.onStreamEvent(event),
            );
            if (!body) {
                this.progressView?.complete({
                    success: false,
                    failed_step: 'stream',
                    log: [],
                });
                this._setStatus('error', 'Rollback finished without a result payload.');
                return;
            }
            await this._finishUpdateResult(body, {
                successMessage: `Rolled back to ${sha.slice(0, 8)}.`,
                failureMessage: () => 'Rollback failed.',
            });
        } catch (err) {
            await this._handleUpdateStreamError(err);
        } finally {
            this.applyBtn.disabled = false;
            this._syncRollbackButton();
        }
    }

    async _finishUpdateResult(body, { successMessage, failureMessage }) {
        this._lastResult = body;
        this.progressView?.complete(body);
        this.logView.render(body);
        if (body.success) {
            this._setStatus('success', successMessage);
            const restarted = (body.log || []).some(
                (entry) => entry.step === 'upgrade' && entry.returncode === 0,
            );
            if (restarted) {
                await this._loadInstallStatus();
                const online = await this.progressView?.waitForServiceRecovery();
                if (online) {
                    window.setTimeout(() => window.location.reload(), 800);
                }
            } else {
                await this.refresh();
            }
            this._syncRollbackButton();
        } else {
            const msg = typeof failureMessage === 'function'
                ? failureMessage(body)
                : failureMessage;
            this._setStatus('error', msg);
        }
    }

    async _handleUpdateStreamError(err) {
        if (err && err.status) {
            this.progressView?.complete({
                success: false,
                failed_step: 'request',
                log: [],
            });
            this._setStatus('error', `Update request failed (HTTP ${err.status}).`);
            return;
        }
        const recovered = await this.progressView?.waitForServiceRecovery({
            timeoutMs: 45000,
        });
        if (recovered) {
            // Apply may have succeeded; rollback is written before git fetch.
            await this._loadInstallStatus();
            this._syncRollbackButton();
            window.setTimeout(() => window.location.reload(), 800);
            return;
        }
        this.progressView?.complete({
            success: false,
            failed_step: 'network',
            log: [],
        });
        this._setStatus('error', 'Connection lost during update. Check SSH or try again.');
    }

    _normalizeChannelId(channelId) {
        if (!channelId) return channelId;
        return UPDATE_CHANNEL_ALIASES[channelId] || channelId;
    }

    _versionAtLeast(localVersion, parts) {
        if (!localVersion) return false;
        const nums = String(localVersion).split('.').map((n) => parseInt(n, 10));
        for (let i = 0; i < parts.length; i += 1) {
            const have = nums[i] || 0;
            const need = parts[i] || 0;
            if (have > need) return true;
            if (have < need) return false;
        }
        return true;
    }

    _currentChannel() {
        const id = this._normalizeChannelId(this.channelSelect?.value);
        return this._channels.find((c) => c.id === id) || null;
    }

    /** SHA captured before the last successful dashboard apply (in-memory or persisted). */
    _rollbackSha() {
        const fromResult = this._lastResult?.pre_update_sha;
        if (fromResult) return fromResult;
        const fromInstall = this._installStatus?.rollback_pre_sha;
        if (fromInstall) return fromInstall;
        return null;
    }

    _syncRollbackButton() {
        const sha = this._rollbackSha();
        if (this.rollbackBtn) {
            this.rollbackBtn.disabled = !sha;
            if (sha) {
                this.rollbackBtn.title =
                    `Restore commit ${sha.slice(0, 8)} from before the last apply`;
            } else {
                this.rollbackBtn.title =
                    'Enabled after a successful Apply from this page';
            }
        }
        if (this.rollbackHintEl) {
            this.rollbackHintEl.textContent = sha
                ? `Rollback point: ${sha.slice(0, 8)} (from before the last dashboard apply).`
                : 'Rollback unlocks after Apply update runs once from this page '
                    + '(even when already up to date). Git pull alone does not count.';
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

window.UpdatePanelController = UpdatePanelController;
