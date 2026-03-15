/**
 * Simple node list for the local Mesh Point dashboard.
 * Shows nodes with name, protocol badge, RSSI, and time ago.
 */
class SimpleNodeList {
    constructor(containerId) {
        this._container = document.getElementById(containerId);
        this._nodes = [];
        this._searchQuery = '';
        this._initSearch();
    }

    get nodeCount() { return this._nodes.length; }

    _initSearch() {
        const input = document.getElementById('node-search');
        if (!input) return;
        let timer;
        input.addEventListener('input', () => {
            clearTimeout(timer);
            timer = setTimeout(() => {
                this._searchQuery = input.value.trim().toLowerCase();
                this._render();
            }, 200);
        });
    }

    loadNodes(nodes) {
        this._nodes = nodes.map(n => ({
            ...n,
            rssi: n.rssi ?? n.latest_rssi ?? null,
            snr: n.snr ?? n.latest_snr ?? null,
        }));
        this._nodes.sort((a, b) => {
            const aTime = a.last_heard || a.last_seen || '';
            const bTime = b.last_heard || b.last_seen || '';
            return bTime.localeCompare(aTime);
        });
        this._render();
    }

    updateFromPacket(packet) {
        if (!packet.source_id) return;
        const sig = packet.signal || {};
        const pktRssi = sig.rssi != null ? sig.rssi : packet.rssi;
        const pktSnr = sig.snr != null ? sig.snr : packet.snr;

        const existing = this._nodes.find(n => n.node_id === packet.source_id);
        if (existing) {
            existing.last_heard = new Date().toISOString();
            if (pktRssi != null) existing.rssi = pktRssi;
            if (pktSnr != null) existing.snr = pktSnr;
            if (packet.packet_type === 'nodeinfo' && packet.decoded_payload) {
                const p = packet.decoded_payload;
                if (p.long_name) existing.long_name = p.long_name;
                if (p.short_name) existing.short_name = p.short_name;
            }
        } else {
            this._nodes.push({
                node_id: packet.source_id,
                protocol: packet.protocol || 'meshtastic',
                rssi: pktRssi,
                snr: pktSnr,
                last_heard: new Date().toISOString(),
            });
        }
        this._nodes.sort((a, b) => {
            const aTime = a.last_heard || a.last_seen || '';
            const bTime = b.last_heard || b.last_seen || '';
            return bTime.localeCompare(aTime);
        });
        this._render();
    }

    _render() {
        let filtered = this._nodes;
        if (this._searchQuery) {
            filtered = filtered.filter(n => {
                const name = (n.long_name || n.name || '').toLowerCase();
                const id = (n.node_id || '').toLowerCase();
                return name.includes(this._searchQuery) || id.includes(this._searchQuery);
            });
        }

        if (filtered.length === 0) {
            this._container.innerHTML = '<div style="padding:1rem;text-align:center;color:var(--text-muted);font-size:0.8rem;">No nodes found</div>';
            return;
        }

        this._container.innerHTML = filtered.map(n => {
            const name = this._esc(n.display_name || n.long_name || n.name || n.node_id || '--');
            const proto = n.protocol || 'meshtastic';
            const rssi = n.rssi != null ? `${Number(n.rssi).toFixed(0)} dBm` : '';
            const heard = n.last_heard || n.last_seen;
            const ago = heard ? this._timeAgo(heard) : '';
            const metaParts = [rssi, ago].filter(Boolean).join(' · ');

            return `<div class="node-item">
                <div class="node-item__top">
                    <span class="node-item__name">${name}</span>
                    <span class="node-item__ago">${ago || '--'}</span>
                </div>
                <div class="node-item__bottom">
                    <span class="node-item__proto node-item__proto--${proto}">${proto}</span>
                    <span class="node-item__rssi">${rssi || '--'}</span>
                </div>
            </div>`;
        }).join('');
    }

    _timeAgo(isoStr) {
        const diff = Date.now() - new Date(isoStr).getTime();
        const mins = Math.floor(diff / 60000);
        if (mins < 1) return 'now';
        if (mins < 60) return `${mins}m`;
        const hours = Math.floor(mins / 60);
        if (hours < 24) return `${hours}h`;
        return `${Math.floor(hours / 24)}d`;
    }

    _esc(str) {
        const el = document.createElement('span');
        el.textContent = str;
        return el.innerHTML;
    }
}
