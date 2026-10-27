/** Optional chips share the dashboard topbar and own their polling lifecycle. */
(() => {
    const entries = new Map();
    window.registerTopbarChip = ({id, make}) => {
        if (/^[a-z0-9][a-z0-9-]*$/.test(id) && typeof make === 'function') entries.set(id, make);
    };
    window.mountPluginTopbarChips = () => {
        const root = document.getElementById('topbar');
        if (!root) return;
        for (const [id, make] of entries) {
            const group = document.createElement('div');
            group.className = 'topbar__group';
            group.dataset.pluginChip = id;
            root.insertBefore(group, root.querySelector('.topbar__spacer'));
            try {
                const chip = make();
                chip.mount(group);
                chip.init?.();
                window.addEventListener('pagehide', () => chip.destroy?.(), {once:true});
            } catch (error) {
                group.remove();
                console.warn(`Optional topbar chip ${id} failed.`, error);
            }
        }
    };
})();
