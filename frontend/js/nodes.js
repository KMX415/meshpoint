class NodeList {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.nodes = [];
    }

    async loadNodes() {
        try {
            const res = await fetch('/api/nodes?limit=100');
            this.nodes = await res.json();
            this.render();
        } catch (e) {
            console.error('Failed to load nodes:', e);
        }
    }

    render() {
        this.container.textContent = '';
        this.nodes.forEach(node => {
            this.container.appendChild(this._createCard(node));
        });
    }

    _createCard(node) {
        const card = document.createElement('div');
        card.className = 'node-card';
        card.dataset.nodeId = node.node_id;

        const nameRow = document.createElement('div');
        nameRow.className = 'node-card__name';
        nameRow.appendChild(document.createTextNode(node.display_name || ''));
        const protocolSpan = document.createElement('span');
        protocolSpan.className = `node-card__protocol node-card__protocol--${this._safeClass(node.protocol)}`;
        protocolSpan.textContent = node.protocol;
        nameRow.appendChild(protocolSpan);

        const metaRow = document.createElement('div');
        metaRow.className = 'node-card__meta';
        const signalInfo = node.latest_signal ? `${node.latest_signal.rssi} dBm` : '--';
        const lastHeard = this._timeAgo(node.last_heard);
        const fields = [
            ['ID:', node.node_id],
            ['Pkts:', node.packet_count],
            ['RSSI:', signalInfo],
            ['Seen:', lastHeard],
        ];
        fields.forEach(([label, value]) => {
            const span = document.createElement('span');
            const labelEl = document.createElement('span');
            labelEl.className = 'label';
            labelEl.textContent = label;
            span.appendChild(labelEl);
            span.appendChild(document.createTextNode(' ' + value));
            metaRow.appendChild(span);
        });

        card.appendChild(nameRow);
        card.appendChild(metaRow);
        return card;
    }

    updateFromPacket(packet) {
        const badge = document.getElementById('node-count-badge');
        if (badge) {
            const uniqueNodes = new Set(this.nodes.map(n => n.node_id));
            uniqueNodes.add(packet.source_id);
            badge.textContent = `${uniqueNodes.size} nodes`;
        }
    }

    _timeAgo(isoString) {
        const diff = (Date.now() - new Date(isoString).getTime()) / 1000;
        if (diff < 60) return `${Math.floor(diff)}s ago`;
        if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
        if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
        return `${Math.floor(diff / 86400)}d ago`;
    }

    _safeClass(str) {
        return (str || '').replace(/[^a-zA-Z0-9_-]/g, '');
    }
}

window.NodeList = NodeList;
