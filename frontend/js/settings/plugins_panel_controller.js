/** Installed plugin state and restart-to-apply enablement. */
class PluginsPanelController {
    constructor(root) {
        this.root = root;
        this.catalog = new window.PluginCatalog(root.querySelector("#plugin-catalog"), () => this.refresh());
        this.list = root.querySelector('[data-plugin-list]');
        this.status = root.querySelector('[data-plugin-status]');
        root.querySelector('[data-plugin-refresh]').addEventListener('click', () => this.refresh());
    }

    async refresh() {
        this.status.textContent = 'Loading plugins...';
        try {
            const response = await fetch('/api/plugins', {credentials: 'same-origin'});
            if (!response.ok) throw new Error('Could not load plugins.');
            const {plugins} = await response.json();
            this.catalog.setInstalled(plugins);
            this.list.replaceChildren();
            for (const plugin of plugins) this.render(plugin);
            this.status.textContent = plugins.length ? '' : 'No optional plugins installed.';
            await this.catalog.refresh();
        } catch (error) { this.status.textContent = error.message; }
    }

    render(plugin) {
        const card = document.createElement('article');
        card.className = 'auth-card';
        card.dataset.pluginId = plugin.id;
        const title = document.createElement('h4');
        const module = window.MESHPOINT_MODULES.find(item => item.id === plugin.id);
        title.textContent = `${module?.name || plugin.id} · ${plugin.version}`;
        const description = document.createElement('p');
        description.className = 'auth-card__hint';
        description.textContent = plugin.description;
        const state = document.createElement('p');
        state.textContent = `${plugin.status}${plugin.restart_required ? ' (restart required)' : ''}`;
        const error = document.createElement('p');
        error.textContent = plugin.error || '';
        const toggle = document.createElement('label');
        toggle.className = 'store-toggle';
        const button = document.createElement('input');
        button.type = 'checkbox';
        button.checked = plugin.enabled;
        button.setAttribute('aria-label', `Enable ${module?.name || plugin.id}`);
        button.disabled = !plugin.enabled && (['incompatible', 'failed'].includes(plugin.status)
            || (plugin.dependency && !plugin.dependency.enabled));
        toggle.append(button, document.createTextNode('Enabled'));
        button.addEventListener('change', async () => {
            const enabled = button.checked;
            button.disabled = true;
            try {
                const response = await fetch(`/api/plugins/${encodeURIComponent(plugin.id)}`, {
                    method: 'PUT', credentials: 'same-origin',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({enabled}),
                });
                const result = await response.json();
                if (!response.ok) throw new Error(result.detail || 'Could not save plugin settings.');
                await this.refresh();
                this.status.textContent = 'Saved. Restart Meshpoint to apply.';
                if (result.also_disabled?.length) this.status.textContent += ` Also disabled: ${result.also_disabled.join(', ')}.`;
                this.list.querySelector(`[data-plugin-id="${plugin.id}"] input[type="checkbox"]`)?.focus();
            } catch (failure) {
                this.status.textContent = failure.message;
                button.checked = plugin.enabled;
                button.disabled = false;
            }
        });
        const source = document.createElement('p');
        source.textContent = plugin.source?.url
            ? `Updates & support: ${this.catalog.sourceName(plugin.source)} (${plugin.source.url})`
            : plugin.locked ? 'Bundled with Meshpoint' : 'Source not recorded';
        card.append(title, description, source, state, error, toggle);
        if (plugin.dependency) {
            const dependency = document.createElement('p');
            dependency.textContent = plugin.dependency.enabled ? `Requires ${plugin.dependency.id} (enabled).`
                : `Install and enable ${plugin.dependency.id} first.`;
            card.append(dependency);
        }
        if (plugin.python_setup && !plugin.python_ready) {
            const setup = document.createElement('button');
            setup.type = 'button'; setup.className = 'terminal-button'; setup.textContent = 'Install Reticulum dependencies';
            setup.addEventListener('click', async () => {
                setup.disabled = true;
                this.status.textContent = 'Downloading verified Reticulum libraries into their separate directory...';
                try {
                    const response = await fetch(`/api/plugins/${encodeURIComponent(plugin.id)}/dependencies`, {
                        method: 'POST', credentials: 'same-origin',
                    });
                    const result = await response.json();
                    if (!response.ok) throw new Error(result.detail || 'Dependency installation failed.');
                    await this.refresh();
                    this.status.textContent = 'Dependencies installed. Enable Reticulum and restart Meshpoint.';
                } catch (failure) { this.status.textContent = failure.message; setup.disabled = false; }
            });
            card.appendChild(setup);
        }
        if (plugin.dependencies) {
            const deps = document.createElement('p');
            deps.textContent = plugin.dependencies.missing_commands.length
                ? `Missing commands: ${plugin.dependencies.missing_commands.join(', ')}. ${plugin.dependencies.instructions}`
                : 'Dependency command check passed. Device access still needs validation.';
            card.appendChild(deps);
        }
        if (!plugin.locked) {
            const remove = document.createElement('button');
            remove.type = 'button'; remove.className = 'terminal-button'; remove.textContent = 'Uninstall';
            remove.disabled = plugin.enabled || plugin.restart_required;
            remove.addEventListener('click', async () => {
                if (!window.confirm(`Remove ${plugin.id}? Settings and captured data will be retained.`)) return;
                remove.disabled = true;
                try {
                    const response = await fetch(`/api/plugins/${encodeURIComponent(plugin.id)}`, {
                        method: 'DELETE', credentials: 'same-origin',
                    });
                    const result = await response.json();
                    if (!response.ok) throw new Error(result.detail || 'Could not uninstall plugin.');
                    await this.refresh();
                    this.status.textContent = result.cleanup_pending
                        ? 'Plugin removed. Some unused code files still need cleanup.'
                        : 'Plugin removed. Settings and data retained.';
                } catch (failure) { this.status.textContent = failure.message; remove.disabled = false; }
            });
            card.appendChild(remove);
        }
        this.list.appendChild(card);
    }
}
window.PluginsPanelController = PluginsPanelController;
