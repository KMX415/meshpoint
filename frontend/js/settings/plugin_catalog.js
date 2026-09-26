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
        this.sourceChoices = new Map();
        this.sourceOrder = [];
        this.sourcePresets = {
            meshpoint: {label:'Meshpoint Official', url:'https://github.com/KMX415/meshpoint-plugins', ref:'main',
                description:'Official Meshpoint plugin repository, maintained through reviewed pull requests. This catalog targets the v0.8.0 release candidate; hardware validation varies by module.'},
            einstein: {label:'Einstein Experimental', url:'https://github.com/javastraat/meshpoint-plugins', ref:'main',
                description:'Experimental and additional plugins and themes maintained independently by Einstein PD2EMC. These are separate from the official Meshpoint catalog.'},
        };
        this.permission = root.querySelector('[data-source-enabled]');
        this.permission.addEventListener('change', () => this.setDownloads());
        this.preset = root.querySelector('[data-source-preset]');
        this.preset.addEventListener('change', () => this.selectPreset());
        this.selectPreset();
        this.permissionNote = document.createElement('aside');
        this.permissionNote.className = 'store-source-access';
        this.permissionNote.setAttribute('role', 'status');
        this.root.prepend(this.permissionNote);
        this.setSourceAccess(null);
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
        (this.sourcesEnabled ? this.preset : this.permission).focus({preventScroll:true});
    }

    selectPreset() {
        const preset = this.sourcePresets[this.preset.value];
        const form = this.root.querySelector('form');
        form.elements.url.value = preset?.url || '';
        form.elements.ref.value = preset?.ref || 'main';
        form.elements.url.readOnly = Boolean(preset);
        form.elements.trusted.checked = false;
        this.root.querySelector('[data-source-description]').textContent = preset?.description
            || 'Enter a GitHub repository that publishes a Meshpoint plugin catalog.';
    }

    sourceName(source) {
        if (source?.url === 'https://github.com/KMX415/meshpoint') return 'Meshpoint legacy catalog';
        return Object.values(this.sourcePresets).find(preset => preset.url === source?.url)?.label || source?.url || 'Source not recorded';
    }

    async setDownloads() {
        const enabled = this.permission.checked;
        this.permission.disabled = true;
        this.status.textContent = 'Saving download permission...';
        try {
            const result = await this.request('/settings', {method:'PUT', headers:{'Content-Type':'application/json'},
                body:JSON.stringify({enabled})});
            this.setSourceAccess(result.sources_enabled);
            this.render();
            this.status.textContent = enabled ? 'Downloads allowed. Choose a source below.' : 'Downloads disabled. Installed plugins are unchanged.';
        } catch (error) {
            this.setSourceAccess(this.sourceAccess);
            this.status.textContent = error.message;
        }
    }

    setSourceAccess(enabled) {
        this.sourcesEnabled = enabled === true;
        this.sourceAccess = enabled;
        this.permission.checked = this.sourcesEnabled;
        this.permission.disabled = typeof enabled !== 'boolean';
        const heading = document.createElement('h3');
        const explanation = document.createElement('p');
        heading.textContent = enabled === false ? 'Plugin downloads are locked' : enabled === null
            ? 'Checking download permission...' : 'Download permission could not be checked';
        explanation.textContent = enabled === false
            ? 'Turn on Allow plugin downloads in Plugin sources to add a catalog and install modules. You can still manage installed plugins.'
            : enabled === null ? 'Source controls will stay disabled until Meshpoint confirms access.'
                : 'Source controls are temporarily disabled. Refresh to retry before changing device settings.';
        this.permissionNote.replaceChildren(heading, explanation);
        if (enabled === false) this.permissionNote.append(this.button('Manage download permission', () => this.showSources()));
        this.permissionNote.hidden = this.sourcesEnabled;
        this.root.querySelector('[data-store-sources]').textContent = 'Manage sources';
        for (const control of this.root.querySelectorAll('form input, form select, form button, [data-source-mutation]')) {
            control.disabled = !this.sourcesEnabled;
        }
    }

    async refresh() {
        this.setSourceAccess(null);
        this.render();
        this.status.textContent = 'Checking module sources...';
        try {
            const data = await this.request('');
            this.sourceOrder = data.sources.map(source => source.url);
            this.setSourceAccess(data.sources_enabled);
            this.list.replaceChildren();
            if (!data.sources.length) {
                const empty = document.createElement('p');
                empty.className = 'store-note';
                empty.textContent = 'No plugin sources added yet. The module cards are previews until you add a catalog. Adding a source does not install or enable any plugins.';
                this.list.append(empty);
            }
            this.entries = [];
            for (const source of data.sources) {
                const row = document.createElement('div'); row.className = 'store-source';
                const label = document.createElement('span');
                label.textContent = `${this.sourceName(source)} · ${source.url} · ${source.ref.slice(0, 8)}`;
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
        } catch (error) { this.setSourceAccess('error'); this.status.textContent = error.message; this.render(); }
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
        const groups = new Map();
        for (const entry of remote) {
            const key = `${entry.kind}:${entry.id}`;
            if (!groups.has(key)) groups.set(key, []);
            groups.get(key).push(entry);
        }
        const selected = [...groups].map(([key, choices]) => {
            choices.sort((a, b) => this.sourceOrder.indexOf(a.source.url) - this.sourceOrder.indexOf(b.source.url));
            const original = this.installedPlugins.get(choices[0].id)?.source?.url;
            const requested = this.sourceChoices.get(key) || original;
            return {...(choices.find(entry => entry.source.url === requested) || choices[0]), choices};
        });
        return [...selected, ...previews, ...unknownInstalled].map(entry => ({
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
        const maintainer = document.createElement('p');
        maintainer.className = 'store-card__maintainer';
        maintainer.textContent = entry.source ? `Updates & support: ${this.sourceName(entry.source)}`
            : entry.runtime?.source ? `Installed from: ${this.sourceName(entry.runtime.source)}` : 'Choose a catalog for source and support details.';
        card.append(top, category, title, description, maintainer);
        if (entry.choices?.length > 1) {
            const label = document.createElement('label'); label.className = 'cfg-field store-card__source';
            const caption = document.createElement('span'); caption.textContent = 'Download source';
            const select = document.createElement('select'); select.className = 'cfg-field__input';
            for (const choice of entry.choices) {
                const option = document.createElement('option'); option.value = choice.source.url;
                option.textContent = `${this.sourceName(choice.source)} · v${choice.version}`;
                select.append(option);
            }
            select.value = entry.source.url;
            select.addEventListener('change', () => {
                this.sourceChoices.set(`${entry.kind}:${entry.id}`, select.value);
                this.render();
                this.catalog.querySelector(`[data-module-id="${entry.id}"][data-module-kind="${entry.kind}"] select`)?.focus();
            });
            label.append(caption, select); card.append(label);
        }
        card.dataset.moduleId = entry.id;
        card.dataset.moduleKind = entry.kind;
        const actions = document.createElement('div'); actions.className = 'store-card__actions';
        if (entry.installed && entry.kind === 'app') {
            actions.append(this.button('Manage', () => {
                const target = document.getElementById('settings-plugins-panel').querySelector('[data-store-installed]');
                target.scrollIntoView({behavior:'smooth', block:'start'});
                const control = [...target.querySelectorAll('[data-plugin-id]')].find(item => item.dataset.pluginId === entry.id)?.querySelector('input[type="checkbox"]');
                control?.focus({preventScroll:true});
            }));
        }
        if (entry.source) {
            const updating = entry.installed && entry.kind === 'app';
            const originalSource = entry.runtime?.source?.url;
            const canUpdate = !updating || (!entry.runtime.locked && originalSource === entry.source.url);
            const button = this.button(updating ? 'Update' : entry.installed ? 'Installed' : 'Install', () => this.install(entry, button, updating));
            button.disabled = !this.sourcesEnabled || !entry.compatible || (entry.installed && !updating) || !canUpdate;
            if (updating && !canUpdate) {
                const note = document.createElement('p'); note.className = 'store-note';
                note.textContent = entry.runtime.locked ? 'Bundled plugins update with Meshpoint.'
                    : `Installed from ${this.sourceName(entry.runtime.source)}. Updates keep that source. To change source, disable, restart and uninstall the plugin first.`;
                details.append(note);
            }
            button.classList.add('store-install'); actions.append(button);
        } else if (!entry.installed) {
            actions.append(this.button(this.sourceAccess === false ? 'Set up downloads' : 'Choose source', () => this.showSources()));
        }
        card.append(details, actions);
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
