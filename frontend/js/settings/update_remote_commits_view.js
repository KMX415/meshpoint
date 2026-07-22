/**
 * Renders the latest commits on origin/<branch> for the Updates card.
 *
 * Credit: javastraat/meshpoint ``98577f3``.
 */

class UpdateRemoteCommitsView {
    constructor(rootEl, listEl) {
        this.root = rootEl;
        this.list = listEl;
    }

    clear() {
        if (this.list) this.list.textContent = '';
        if (this.root) this.root.hidden = true;
    }

    render(status) {
        if (!this.root || !this.list) return;
        const commits = (status && status.remote_commits) || [];
        this.list.textContent = '';
        if (!commits.length) {
            this.root.hidden = true;
            return;
        }
        commits.slice(0, 5).forEach((c) => {
            const li = document.createElement('li');
            li.className = 'update-history__row';

            const when = document.createElement('span');
            when.className = 'update-history__when';
            when.textContent = this._formatCommitTime(c.committed_at);
            li.appendChild(when);

            const what = document.createElement('span');
            what.className = 'update-history__what';
            const sha = document.createElement('code');
            sha.textContent = c.sha || '';
            what.appendChild(sha);
            what.appendChild(document.createTextNode(` ${c.subject || ''}`));
            li.appendChild(what);

            this.list.appendChild(li);
        });
        this.root.hidden = false;
    }

    _formatCommitTime(iso) {
        if (!iso) return '--';
        const d = new Date(iso);
        if (Number.isNaN(d.getTime())) return '--';
        try {
            return d.toLocaleString(undefined, {
                month: 'short',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit',
            });
        } catch (_e) {
            return d.toISOString().slice(0, 16).replace('T', ' ');
        }
    }
}

window.UpdateRemoteCommitsView = UpdateRemoteCommitsView;
