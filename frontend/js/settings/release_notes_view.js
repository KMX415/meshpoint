/**
 * Renders the structured release-notes payload returned by
 * ``GET /api/update/release_notes``.
 *
 * Single responsibility: layout. The class doesn't fetch, doesn't
 * pick channels, and doesn't know anything about apply / rollback
 * lifecycle. It takes a parsed body and writes it into the host
 * element. ``UpdatePanelController`` owns the fetch lifecycle and
 * decides when to render.
 *
 * Render states surfaced via ``data-state`` so CSS can swap the
 * styling without us re-touching the DOM:
 *   - ready   -- a section with bullets is rendered
 *   - empty   -- channel returned no preview (custom channel)
 *   - error   -- network or HTTP failure
 *   - hidden  -- nothing rendered yet (default)
 */

class ReleaseNotesView {
    constructor(rootEl) {
        this.root = rootEl;
    }

    clear() {
        if (!this.root) return;
        this.root.removeAttribute('data-state');
        this.root.innerHTML = '';
    }

    renderEmpty(channelLabel) {
        if (!this.root) return;
        this.root.dataset.state = 'empty';
        const message = channelLabel
            ? `No release-notes preview for "${this._escape(channelLabel)}". Custom branches surface only the commit log.`
            : 'No preview available for this channel.';
        this.root.innerHTML = `<p class="update-release-notes__empty">${message}</p>`;
    }

    renderError(reason) {
        if (!this.root) return;
        this.root.dataset.state = 'error';
        const text = reason || 'Could not load release notes.';
        this.root.innerHTML = `<p class="update-release-notes__error">${this._escape(text)}</p>`;
    }

    render(body) {
        if (!this.root) return;
        if (!body || !body.preview_section) {
            this.renderEmpty(body && body.channel_label);
            return;
        }
        const section = body.preview_section;
        const eyebrow = section.is_unreleased
            ? "What's coming"
            : "What's new";
        const title = section.header || section.version || 'Release notes';
        const date = section.date ? this._escape(section.date) : '';
        const bullets = this._renderBullets(section.bullets || []);
        const installed = body.current_installed_version
            ? `<p class="update-release-notes__date">Installed: v${this._escape(body.current_installed_version)}</p>`
            : '';
        this.root.dataset.state = 'ready';
        this.root.innerHTML = `
            <header class="update-release-notes__head">
                <p class="update-release-notes__eyebrow">${this._escape(eyebrow)}</p>
                <h3 class="update-release-notes__title">${this._escape(title)}</h3>
                ${date ? `<p class="update-release-notes__date">${date}</p>` : ''}
                ${installed}
            </header>
            <ul class="update-release-notes__list">
                ${bullets || '<li class="update-release-notes__empty">No bullets in this section.</li>'}
            </ul>
        `;
    }

    _renderBullets(bullets) {
        const parts = [];
        let lastCategory = null;
        for (const bullet of bullets) {
            const category = (bullet.category || '').trim();
            if (category && category !== lastCategory) {
                parts.push(
                    `<li class="update-release-notes__category">${this._escape(category)}</li>`
                );
                lastCategory = category;
            }
            parts.push(this._renderBullet(bullet));
        }
        return parts.join('');
    }

    _renderBullet(bullet) {
        const headline = this._escape(bullet.headline || '').trim();
        const detail = this._escape(bullet.detail || '').trim();
        if (!headline && !detail) return '';
        const detailHtml = detail
            ? `<span class="update-release-notes__bullet-detail">${detail}</span>`
            : '';
        return `<li class="update-release-notes__bullet">
            <span class="update-release-notes__bullet-headline">${headline}.</span>
            ${detailHtml}
        </li>`;
    }

    _escape(value) {
        return String(value == null ? '' : value).replace(
            /[&<>"']/g,
            (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])
        );
    }
}

window.ReleaseNotesView = ReleaseNotesView;
