/* Anonymous summaries use only the explicit public API, never dashboard /ws. */
(() => {
    const pages = {
        dashboard: ['Dashboard', 'Nodes heard by this Meshpoint.', [
            ['total_nodes', 'Known nodes'], ['active_24h', 'Active in the last 24 hours'],
        ]],
        stats: ['Stats', 'Stored packet totals and signal averages from recent reception.', [
            ['total_packets', 'Stored packets'], ['packets_last_hour', 'Packets in the last hour'],
            ['packets_per_minute', 'Packets / minute (hour average)'],
            ['avg_rssi', 'Average RSSI', ' dBm'], ['avg_snr', 'Average SNR', ' dB'],
        ]],
        radio: ['Radio', 'Configured receive parameters. Changes require administrator access.', [
            ['region', 'Region'], ['frequency_mhz', 'Frequency', ' MHz'],
            ['bandwidth_khz', 'Bandwidth', ' kHz'], ['spreading_factor', 'Spreading factor'],
        ]],
    };
    let busy = false;
    const metrics = document.getElementById('public-metrics');
    const status = document.getElementById('public-status');
    async function get(path) {
        const response = await fetch(`/api/public/view${path}`, {cache:'no-store'});
        if (!response.ok) throw new Error(response.status === 404
            ? 'Public viewing is unavailable. Sign in to continue.' : 'Unable to refresh. Retrying shortly.');
        return response.json();
    }
    async function refresh() {
        if (busy) return;
        busy = true;
        const requestedHash = location.hash;
        try {
            const index = await get('');
            const allowed = index.pages.filter(page => Object.hasOwn(pages, page));
            const requested = requestedHash.replace(/^#\/?/, '');
            const page = allowed.includes(requested) ? requested : allowed[0];
            if (!page) throw new Error('No public pages are available.');
            const data = await get(`/${page}`);
            if (requestedHash !== location.hash) return;
            document.getElementById('public-nav').replaceChildren(...allowed.map(key => {
                const link = document.createElement('a');
                link.href = `#/${key}`;
                link.textContent = pages[key][0];
                if (key === page) link.setAttribute('aria-current', 'page');
                return link;
            }));
            document.getElementById('page-title').textContent = pages[page][0];
            document.getElementById('page-description').textContent = pages[page][1];
            metrics.replaceChildren(...pages[page][2].map(([key, label, unit = '']) => {
                const card = document.createElement('dl');
                card.className = 'metric';
                const title = document.createElement('dt');
                title.textContent = label;
                const value = document.createElement('dd');
                value.textContent = data[key] == null ? 'Unavailable' : `${data[key]}${unit}`;
                card.append(title, value);
                return card;
            }));
            status.textContent = `Updated ${new Date().toLocaleTimeString()}`;
        } catch (error) {
            metrics.replaceChildren();
            document.getElementById('public-nav').replaceChildren();
            document.getElementById('page-title').textContent = 'Public view';
            document.getElementById('page-description').textContent = '';
            status.textContent = error.message;
        } finally {
            busy = false;
            if (requestedHash !== location.hash) refresh();
        }
    }
    addEventListener('hashchange', refresh);
    document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
    setInterval(() => { if (!document.hidden) refresh(); }, 15000);
    refresh();
})();
