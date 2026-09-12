/** Optional module storefront. Trusted catalogs remain the install authority. */
class PluginCatalog {
    constructor(root, installed) {
        this.root = root;
        this.installed = installed;
        this.status = root.querySelector('[data-source-status]');
        this.list = root.querySelector('[data-source-list]');
        this.catalog = root.querySelector('[data-source-catalog]');
        this.sourcesPanel = root.querySelector('[data-store-source-panel]');
        this.sourcesEnabled = false;
        this.permissionNote = document.createElement('p');
        this.permissionNote.className = 'store-note';
        this.permissionNote.setAttribute('role', 'status');
        this.sourcesPanel.before(this.permissionNote);
        this.setSourceAccess(false);
        this.installedPlugins = new Map();
        this.entries = [];
        this.category = 'All';
        this.query = '';
        root.querySelector('form').addEventListener('submit', event => this.add(event));
        root.querySelector('[data-store-search]').addEventListener('input', event => {
            this.query = event.target.value.toLowerCase().trim(); this.render();
        });
        root.querySelector('[data-store-sources]').addEventListener('click', () => this.showSources());
        const filters = root.querySelector('[data-store-filters]');
        for (const name of ['All', 'Networks', 'Radio', 'Aviation', 'Sensors', 'Paging', 'Themes', 'Installed']) {
            const button = this.button(name, () => { this.category = name; this.render(); });
            button.dataset.category = name; button.setAttribute('aria-pressed', String(name === 'All'));
            filters.append(button);
        }
        this.render();
    }

    async request(path, options = {}) {
        const response = await fetch(`/api/plugin-sources${path}`, {credentials:'same-origin', ...options});
        const data = await response.json();
        if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Request failed.');
        return data;
    }

    button(label, action) {
        const button = document.createElement('button');
        button.type = 'button'; button.className = 'terminal-button'; button.textContent = label;
        button.addEventListener('click', action);
        return button;
    }

    setInstalled(plugins) {
        this.installedPlugins = new Map(plugins.map(plugin => [plugin.id, plugin]));
        this.render();
    }

    showSources() {
        this.sourcesPanel.open = true;
        this.sourcesPanel.scrollIntoView({behavior:'smooth', block:'start'});
        if (this.sourcesEnabled) this.sourcesPanel.querySelector('input').focus({preventScroll:true});
    }

    setSourceAccess(enabled) {
        this.sourcesEnabled = enabled === true;
        this.permissionNote.textContent = this.sourcesEnabled ? ''
            : 'Downloads are locked on this device. Set plugin_sources_enabled: true in config/local.yaml and restart Meshpoint to add sources, install or update. Installed modules remain available.';
        this.permissionNote.hidden = this.sourcesEnabled;
        for (const control of this.root.querySelectorAll('form input, form button, [data-source-mutation]')) {
            control.disabled = !this.sourcesEnabled;
        }
    }

    async refresh() {
        this.setSourceAccess(false);
        this.render();
        this.status.textContent = 'Checking module sources...';
        try {
            const data = await this.request('');
            this.setSourceAccess(data.sources_enabled);
            this.list.replaceChildren();
            this.entries = [];
            for (const source of data.sources) {
                const row = document.createElement('div'); row.className = 'store-source';
                const label = document.createElement('span');
                label.textContent = `${source.url} · ${source.ref.slice(0, 8)}`;
                row.append(label, this.button('Reload catalog', () => this.browse(source)));
                const repin = this.button('Update source revision', async () => {
                    if (!this.sourcesEnabled) return;
                    if (!window.confirm(`Resolve ${source.requested_ref} again for ${source.url}? Installed apps will not change.`)) return;
                    try {
                        await this.request('', {method:'PUT', headers:{'Content-Type':'application/json'},
                            body:JSON.stringify({url:source.url, ref:source.requested_ref, trusted:true})});
                        await this.refresh();
                    } catch (error) { this.status.textContent = error.message; }
                });
                repin.dataset.sourceMutation = '';
                repin.disabled = !this.sourcesEnabled;
                row.append(repin);
                this.list.append(row);
            }
            const results = await Promise.allSettled(data.sources.map(source => this.loadSource(source)));
            const failures = results.filter(result => result.status === 'rejected').length;
            this.status.textContent = failures ? `Could not load ${failures} catalog(s). Check the sources below and retry.` : '';
            this.render();
        } catch (error) { this.status.textContent = error.message; this.render(); }
    }

    async loadSource(source) {
        const data = await this.request(`/catalog?url=${encodeURIComponent(source.url)}`);
        this.entries = this.entries.filter(entry => entry.source.url !== source.url);
        this.entries.push(...[...data.plugins, ...data.themes].map(entry => ({...entry, source})));
    }

    async browse(source) {
        this.status.textContent = 'Refreshing catalog...';
        try { await this.loadSource(source); this.status.textContent = ''; this.render(); }
        catch (error) { this.status.textContent = error.message; }
    }

    async add(event) {
        event.preventDefault();
        if (!this.sourcesEnabled) return;
        const form = event.currentTarget;
        const submit = form.querySelector('button');
        submit.disabled = true; this.status.textContent = 'Checking source...';
        try {
            await this.request('', {method:'POST', headers:{'Content-Type':'application/json'},
                body:JSON.stringify({url:form.elements.url.value, ref:form.elements.ref.value, trusted:form.elements.trusted.checked})});
            form.elements.trusted.checked = false;
            await this.refresh();
        } catch (error) { this.status.textContent = error.message; }
        finally { submit.disabled = !this.sourcesEnabled; }
    }

    modules() {
        const metadata = window.MESHPOINT_MODULES;
        const remote = this.entries.map(entry => ({
            ...metadata.find(item => item.id === entry.id && entry.kind === 'app'),
            ...entry,
            description: entry.kind === 'app' ? metadata.find(item => item.id === entry.id)?.description || entry.description : entry.description,
            name: entry.kind === 'theme' ? entry.id : metadata.find(item => item.id === entry.id)?.name || entry.id,
            category: entry.kind === 'theme' ? 'Themes' : metadata.find(item => item.id === entry.id)?.category || 'Other',
        }));
        const previews = metadata.filter(item => !remote.some(entry => entry.id === item.id && entry.kind === 'app'));
        const unknownInstalled = [...this.installedPlugins.values()]
            .filter(item => ![...remote, ...previews].some(entry => entry.id === item.id && entry.kind === 'app'))
            .map(item => ({...item, name:item.id, kind:'app', category:'Other'}));
        return [...remote, ...previews, ...unknownInstalled].map(entry => ({
            ...entry,
            installed: entry.kind === 'app' ? this.installedPlugins.has(entry.id) : entry.installed,
            runtime: entry.kind === 'app' ? this.installedPlugins.get(entry.id) : null,
        }));
    }

    render() {
        const entries = this.modules();
        const visible = entries.filter(entry => (
            (this.category === 'All' || (this.category === 'Installed' ? entry.installed : entry.category === this.category))
            && [entry.name, entry.id, entry.description, entry.hardware, entry.category].join(' ').toLowerCase().includes(this.query)
        ));
        this.catalog.replaceChildren(...visible.map(entry => this.card(entry)));
        this.root.querySelector('[data-store-count]').textContent = `${visible.length} module${visible.length === 1 ? '' : 's'}`;
        this.root.querySelector('[data-store-empty]').hidden = visible.length > 0;
        this.root.querySelector('[data-store-note]').textContent = this.entries.length
            ? 'Install only what you need. Hardware requirements and source details are shown on each card.'
            : 'Explore the collection. Add a trusted release source to install modules not already on this device.';
        for (const button of this.root.querySelectorAll('[data-category]')) {
            button.setAttribute('aria-pressed', String(button.dataset.category === this.category));
        }
    }

    card(entry) {
        const card = document.createElement('article'); card.className = 'store-card';
        card.dataset.category = entry.category;
        const top = document.createElement('div'); top.className = 'store-card__top';
        const icon = document.createElement('span'); icon.className = 'store-icon';
        icon.innerHTML = window.meshpointModuleIcon(entry.icon);
        const badge = document.createElement('span'); badge.className = 'store-badge';
        badge.textContent = entry.installed ? (entry.runtime?.enabled ? 'Enabled' : 'Installed')
            : entry.source ? (entry.compatible ? 'Available' : 'Incompatible') : 'Catalog preview';
        badge.dataset.state = entry.installed ? 'installed' : 'available';
        top.append(icon, badge);
        const category = document.createElement('p'); category.className = 'store-card__category'; category.textContent = entry.category;
        const title = document.createElement('h4'); title.textContent = entry.name;
        const description = document.createElement('p'); description.className = 'store-card__description'; description.textContent = entry.description;
        const details = document.createElement('details'); details.className = 'store-card__details';
        const summary = document.createElement('summary'); summary.textContent = 'Requirements & source';
        const hardware = document.createElement('p'); hardware.textContent = entry.hardware || 'See the module documentation for setup requirements.';
        const source = document.createElement('p'); source.textContent = entry.source
            ? `${entry.source.url} · ${entry.source.ref.slice(0, 8)} · v${entry.version}`
            : 'Preview from this development build. No download source selected.';
        const author = document.createElement('p'); author.textContent = `By ${entry.author || (entry.id === 'p25' ? 'Meshpoint contributors' : null) || (window.MESHPOINT_MODULES.some(item => item.id === entry.id && entry.kind === 'app') ? 'Einstein PD2EMC' : 'Author not specified')}`;
        details.append(summary, hardware, source, author);
        const actions = document.createElement('div'); actions.className = 'store-card__actions';
        if (entry.installed && entry.kind === 'app') {
            actions.append(this.button('Manage', () => {
                const target = document.getElementById('settings-plugins-panel').querySelector('[data-store-installed]');
                target.scrollIntoView({behavior:'smooth', block:'start'});
                const control = [...target.querySelectorAll('[data-plugin-id]')].find(item => item.dataset.pluginId === entry.id)?.querySelector('button');
                control?.focus({preventScroll:true});
            }));
        }
        if (entry.source) {
            const updating = entry.installed && entry.kind === 'app';
            const button = this.button(updating ? 'Update' : entry.installed ? 'Installed' : 'Install', () => this.install(entry, button, updating));
            button.disabled = !this.sourcesEnabled || !entry.compatible || (entry.installed && !updating);
            button.classList.add('store-install'); actions.append(button);
        } else if (!entry.installed) {
            actions.append(this.button('Choose source', () => this.showSources()));
        }
        card.append(top, category, title, description, details, actions);
        return card;
    }

    async install(entry, button, updating) {
        if (!this.sourcesEnabled) return;
        if (updating && !window.confirm(`Update ${entry.id} from ${entry.source.ref.slice(0, 8)}? Disable it and restart Meshpoint first.`)) return;
        button.disabled = true; this.status.textContent = `Downloading ${entry.name}...`;
        try {
            await this.request(updating ? '/update' : '/install', {method:'POST', headers:{'Content-Type':'application/json'},
                body:JSON.stringify({source:entry.source.url, id:entry.id})});
            await this.installed();
            this.status.textContent = entry.kind === 'theme' ? 'Theme installed. Reload the dashboard to use it.' : 'Installed and disabled. Review setup requirements below, then enable when ready.';
        } catch (error) { this.status.textContent = error.message; button.disabled = !this.sourcesEnabled; }
    }
}
window.PluginCatalog = PluginCatalog;
