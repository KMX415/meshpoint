/* Admin-only opt-in control for anonymous aggregate summaries. */
class PublicViewForm {
    constructor(root) {
        this.root = root;
        this.form = root.querySelector('form');
        this.enabled = root.querySelector('[data-public-enabled]');
        this.pages = [...root.querySelectorAll('[data-public-page]')];
        this.button = root.querySelector('button[type="submit"]');
        this.status = root.querySelector('[role="status"]');
        this.loaded = false;
    }

    bind() {
        this.form.addEventListener('submit', event => this.save(event));
    }

    setValues(settings) {
        this.enabled.checked = !!settings.public_view_enabled;
        for (const page of this.pages) {
            page.checked = (settings.public_view_pages || []).includes(page.value);
            page.disabled = false;
        }
        this.enabled.disabled = false;
        this.button.disabled = false;
        this.loaded = true;
    }

    async save(event) {
        event.preventDefault();
        if (!this.loaded || this.button.disabled) return;
        const enabled = this.enabled.checked;
        const pages = this.pages.filter(page => page.checked).map(page => page.value);
        if (enabled && !pages.length) {
            this.status.textContent = 'Choose at least one page to enable public viewing.';
            return;
        }
        this.button.disabled = true;
        this.status.textContent = 'Saving…';
        try {
            const response = await fetch('/api/config/public_view', {
                method:'PUT', credentials:'same-origin',
                headers:{'Content-Type':'application/json'}, body:JSON.stringify({enabled,pages}),
            });
            if (!response.ok) throw new Error(`Save failed (HTTP ${response.status}).`);
            const saved = await response.json();
            this.setValues({public_view_enabled:saved.enabled, public_view_pages:saved.pages});
            this.status.textContent = saved.enabled
                ? 'Public view enabled. Open the dashboard in a signed-out browser to check it.'
                : 'Public view disabled. Dashboard visitors must sign in.';
        } catch (error) {
            this.status.textContent = error.message || 'Save failed. Please try again.';
        } finally {
            this.button.disabled = false;
        }
    }
}
window.PublicViewForm = PublicViewForm;
