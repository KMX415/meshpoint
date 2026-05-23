/**
 * Renderer for the structured update log returned by ``/api/update/apply``.
 *
 * Single responsibility: take the ``log`` array from the server
 * (one entry per step with stdout/stderr/returncode) and render it
 * as a collapsible, color-coded list. No fetching, no state -- the
 * controller passes the array in once per render.
 */

class UpdateLogView {
    constructor(rootEl) {
        this.root = rootEl;
    }

    render(result) {
        if (!result) {
            this.root.innerHTML = '';
            return;
        }
        const status = result.success ? 'success' : 'error';
        const summary = result.success
            ? `Update applied to ${this._escape(result.target_branch)} in ${this._formatDuration(result.duration_seconds)}.`
            : `Update failed at "${this._escape(result.failed_step || 'unknown step')}".`;
        const previousSha = result.pre_update_sha
            ? `<span class="update-log__sha" title="Pre-update SHA">rollback to ${this._escape(result.pre_update_sha.slice(0, 8))}</span>`
            : '';

        const items = (result.log || []).map((entry) => this._renderEntry(entry)).join('');
        this.root.innerHTML = `
            <div class="update-log__summary" data-status="${status}">
                <span class="update-log__status">${status}</span>
                <p>${summary}</p>
                ${previousSha}
            </div>
            <ol class="update-log__steps">${items}</ol>
        `;
    }

    _renderEntry(entry) {
        const ok = entry.returncode === 0;
        const stdout = entry.stdout ? this._escape(entry.stdout) : '';
        const stderr = entry.stderr ? this._escape(entry.stderr) : '';
        return `
            <li class="update-log__step" data-status="${ok ? 'ok' : 'error'}">
                <details>
                    <summary>
                        <span class="update-log__step-label">${this._escape(entry.step)}</span>
                        <code class="update-log__step-cmd">${this._escape(entry.command)}</code>
                        <span class="update-log__step-rc">rc=${entry.returncode}</span>
                    </summary>
                    ${stdout ? `<pre class="update-log__stream">${stdout}</pre>` : ''}
                    ${stderr ? `<pre class="update-log__stream update-log__stream--err">${stderr}</pre>` : ''}
                </details>
            </li>
        `;
    }

    _formatDuration(seconds) {
        if (!seconds) return '0s';
        if (seconds < 60) return `${seconds.toFixed(1)}s`;
        const mins = Math.floor(seconds / 60);
        const secs = Math.round(seconds % 60);
        return `${mins}m ${secs}s`;
    }

    _escape(value) {
        return String(value || '').replace(/[&<>"']/g, (c) => (
            { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
        ));
    }
}

window.UpdateLogView = UpdateLogView;
