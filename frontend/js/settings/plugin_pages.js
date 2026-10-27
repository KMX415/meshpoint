/** Load optional admin pages before the sidebar takes its DOM snapshot. */
window.loadPluginPages = async function loadPluginPages(identity) {
    if (identity?.role !== 'admin') return [];
    try {
        const response = await fetch('/api/plugin-ui', {credentials: 'same-origin'});
        if (!response.ok) return [];
        const {plugins} = await response.json();
        // Host libraries must load before the hooks that use them.
        plugins.sort((a, b) => Number(!a.sidebar) - Number(!b.sidebar));
        for (const plugin of plugins) {
            try {
                for (const path of plugin.styles) {
                    const link = document.createElement('link');
                    link.rel = 'stylesheet';
                    link.href = assetUrl(plugin.id, path);
                    document.head.appendChild(link);
                }
                for (const path of plugin.scripts) await loadScript(assetUrl(plugin.id, path));
                if (plugin.sidebar) window.MESHPOINT_SIDEBAR_PLUGINS.push({id: plugin.id, ...plugin.sidebar});
            } catch (error) {
                console.warn(`Plugin ${plugin.id} could not load its page.`, error);
            }
        }
        const pages = window.mountPluginSidebarPages();
        identity.available_sections = [...(identity.available_sections || []),
            ...pages.map(page => page.routeId.replaceAll('/', '.'))];
        return pages;
    } catch (error) {
        console.warn('Optional plugin pages unavailable.', error);
        return [];
    }

    function assetUrl(id, path) {
        return `/api/plugin-ui/${encodeURIComponent(id)}/${path.split('/').map(encodeURIComponent).join('/')}`;
    }

    function loadScript(url) {
        return new Promise((resolve, reject) => {
            const script = document.createElement('script');
            const timeout = setTimeout(() => {
                script.remove();
                reject(new Error('Plugin script timed out'));
            }, 10000);
            script.src = url;
            script.onload = () => { clearTimeout(timeout); resolve(); };
            script.onerror = () => { clearTimeout(timeout); reject(new Error('Plugin script failed')); };
            document.body.appendChild(script);
        });
    }
};
