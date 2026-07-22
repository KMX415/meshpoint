/**
 * Renders incoming commit subjects when the install is behind origin.
 *
 * Credit: javastraat/meshpoint ``4ed91d5``.
 */

class UpdateIncomingView {
    constructor(rootEl) {
        this.root = rootEl;
    }

    clear() {
        if (!this.root) return;
        this.root.textContent = '';
        this.root.hidden = true;
    }

    render(status) {
        if (!this.root) return;
        const commits = (status && status.incoming_commits) || [];
        const behind = status && status.commits_behind;
        this.root.textContent = '';
        if (!behind || !commits.length) {
            this.root.hidden = true;
            return;
        }
        commits.forEach((c) => {
            const li = document.createElement('li');
            const sha = document.createElement('code');
            sha.textContent = c.sha || '';
            li.appendChild(sha);
            li.appendChild(document.createTextNode(` ${c.subject || ''}`));
            this.root.appendChild(li);
        });
        if (behind > commits.length) {
            const li = document.createElement('li');
            li.className = 'update-incoming__more';
            li.textContent = `… and ${behind - commits.length} more`;
            this.root.appendChild(li);
        }
        this.root.hidden = false;
    }
}

window.UpdateIncomingView = UpdateIncomingView;
