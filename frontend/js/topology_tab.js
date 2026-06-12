/**
 * Topology tab: D3 force-directed graph from NEIGHBORINFO, ROUTING, and TRACEROUTE.
 */
class TopologyTab {
    constructor(containerId) {
        this._container = document.getElementById(containerId);
        this._hours = 24;
        this._rendered = false;
        this._simulation = null;
        this._graph = { nodes: [], edges: [], routes: [] };
        this._selectedNode = null;
    }

    async refresh() {
        if (!this._container || typeof d3 === 'undefined') return;

        try {
            const res = await fetch(`/api/analytics/topology?hours=${this._hours}`);
            if (!res.ok) return;
            this._graph = await res.json();
            if (!this._rendered) {
                this._buildLayout();
                this._rendered = true;
            }
            this._renderGraph();
        } catch (e) {
            console.error('Topology refresh failed:', e);
        }
    }

    _buildLayout() {
        this._container.innerHTML = `
            <div class="topology-panel">
                <header class="topology-panel__header">
                    <div>
                        <h2 class="topology-panel__title">Mesh topology</h2>
                        <p class="topology-panel__desc">
                            Force-directed graph from NEIGHBORINFO, traceroute replies, and routing paths.
                            Click a node to highlight traced routes.
                        </p>
                    </div>
                    <div class="topology-panel__controls">
                        <button type="button" class="topology-btn" data-hours="1">1h</button>
                        <button type="button" class="topology-btn" data-hours="6">6h</button>
                        <button type="button" class="topology-btn topology-btn--active" data-hours="24">24h</button>
                    </div>
                </header>
                <div class="topology-panel__meta">
                    <span id="topo-node-count">0 nodes</span>
                    <span id="topo-edge-count">0 links</span>
                </div>
                <div class="topology-panel__canvas-wrap">
                    <svg id="topo-svg" class="topology-svg" aria-label="Mesh topology graph"></svg>
                    <div id="topo-empty" class="topology-empty" hidden>No topology data in this window yet.</div>
                </div>
                <div id="topo-legend" class="topology-legend">
                    <span><i class="topology-swatch topology-swatch--mt"></i> Meshtastic</span>
                    <span><i class="topology-swatch topology-swatch--mc"></i> MeshCore</span>
                    <span><i class="topology-swatch topology-swatch--ni"></i> Neighbor link</span>
                    <span><i class="topology-swatch topology-swatch--tr"></i> Traced link</span>
                    <span><i class="topology-swatch topology-swatch--weak"></i> Weak (&lt; -110 dBm)</span>
                </div>
            </div>
        `;

        this._svg = d3.select('#topo-svg');
        this._emptyEl = document.getElementById('topo-empty');
        this._container.querySelectorAll('[data-hours]').forEach((btn) => {
            btn.addEventListener('click', () => {
                this._hours = Number(btn.dataset.hours);
                this._container.querySelectorAll('[data-hours]').forEach((b) => {
                    b.classList.toggle('topology-btn--active', b === btn);
                });
                this.refresh();
            });
        });

        window.addEventListener('resize', () => {
            if (this._rendered) this._renderGraph();
        });
    }

    _cssToken(name, fallback) {
        return getComputedStyle(document.documentElement)
            .getPropertyValue(name).trim() || fallback;
    }

    _ensureGraphNodes(nodes, edges) {
        const byId = new Map(nodes.map((n) => [n.id, n]));
        for (const edge of edges) {
            for (const id of [edge.source, edge.target]) {
                if (!id || byId.has(id)) continue;
                const stub = {
                    id,
                    label: `!${String(id).slice(-4)}`,
                    protocol: 'meshtastic',
                    packet_count: 0,
                    latest_rssi: null,
                };
                nodes.push(stub);
                byId.set(id, stub);
            }
        }
        return nodes;
    }

    _renderGraph() {
        const wrap = this._container.querySelector('.topology-panel__canvas-wrap');
        const width = wrap.clientWidth || 800;
        const height = Math.max(420, Math.min(560, width * 0.55));

        const accentCyan = this._cssToken('--accent-cyan', '#06b6d4');
        const accentPurple = this._cssToken('--accent-purple', '#a855f7');
        const accentAmber = this._cssToken('--accent-amber', '#f59e0b');
        const accentGreen = this._cssToken('--accent-green', '#00e5a0');
        const textMuted = this._cssToken('--text-muted', '#64748b');
        const textPrimary = this._cssToken('--text-primary', '#e2e8f0');

        let nodes = (this._graph.nodes || []).map((n) => ({ ...n }));
        const edges = (this._graph.edges || []).map((e) => ({ ...e }));
        nodes = this._ensureGraphNodes(nodes, edges);

        const sources = (this._graph.edge_sources || []).join(', ') || 'none';
        const generated = this._graph.generated_at
            ? new Date(this._graph.generated_at).toLocaleTimeString()
            : 'now';
        document.getElementById('topo-node-count').textContent =
            `${nodes.length} node${nodes.length === 1 ? '' : 's'}`;
        document.getElementById('topo-edge-count').textContent =
            `${edges.length} link${edges.length === 1 ? '' : 's'} · ${sources} · ${generated}`;

        if (!nodes.length && !edges.length) {
            this._svg.selectAll('*').remove();
            this._emptyEl.hidden = false;
            const st = this._graph.stats || {};
            const ni = st.neighborinfo_packets ?? 0;
            const tr = st.traceroute_packets ?? 0;
            const rt = st.routing_packets ?? 0;
            this._emptyEl.textContent =
                `No links in the last ${this._hours}h. Packets seen: `
                + `${ni} neighborinfo, ${tr} traceroute, ${rt} routing. `
                + 'Run a traceroute from the Meshtastic app or wait for the next neighbor broadcast.';
            return;
        }
        this._emptyEl.hidden = true;

        const svg = this._svg
            .attr('viewBox', `0 0 ${width} ${height}`)
            .attr('width', '100%')
            .attr('height', height);

        svg.selectAll('*').remove();

        const maxPackets = Math.max(1, ...nodes.map((n) => n.packet_count || 0));
        const radius = (count) => 6 + (count / maxPackets) * 14;

        const routeEdgeKeys = this._routeEdgeKeys(this._selectedNode);

        const link = svg.append('g')
            .attr('stroke-opacity', 0.75)
            .selectAll('line')
            .data(edges)
            .join('line')
            .attr('stroke', (d) => {
                if (routeEdgeKeys.has(this._edgeKey(d))) return accentGreen;
                if (d.weak) return textMuted;
                if (d.edge_type === 'neighborinfo') return accentCyan;
                return accentAmber;
            })
            .attr('stroke-width', (d) => (routeEdgeKeys.has(this._edgeKey(d)) ? 2.5 : d.weak ? 1 : 1.75))
            .attr('stroke-dasharray', (d) => {
                if (d.weak) return '4 3';
                if (d.edge_type && d.edge_type !== 'neighborinfo') return '6 4';
                return null;
            });

        const node = svg.append('g')
            .selectAll('circle')
            .data(nodes)
            .join('circle')
            .attr('r', (d) => radius(d.packet_count || 0))
            .attr('fill', (d) => (d.protocol === 'meshcore' ? accentPurple : accentCyan))
            .attr('stroke', (d) => (d.id === this._selectedNode ? textPrimary : 'rgba(15,23,42,0.8)'))
            .attr('stroke-width', (d) => (d.id === this._selectedNode ? 2 : 1))
            .style('cursor', 'pointer')
            .call(this._drag(svg));

        node.append('title').text((d) => {
            const rssi = d.latest_rssi != null ? `${d.latest_rssi} dBm` : 'n/a';
            return `${d.label} (!${d.id})\n${d.packet_count || 0} pkts · ${rssi}`;
        });

        node.on('click', (_, d) => {
            this._selectedNode = this._selectedNode === d.id ? null : d.id;
            this._renderGraph();
        });

        if (this._simulation) this._simulation.stop();
        this._simulation = d3.forceSimulation(nodes)
            .force('link', d3.forceLink(edges).id((d) => d.id).distance(90).strength(0.5))
            .force('charge', d3.forceManyBody().strength(-180))
            .force('center', d3.forceCenter(width / 2, height / 2))
            .force('collide', d3.forceCollide().radius((d) => radius(d.packet_count || 0) + 4))
            .on('tick', () => {
                link
                    .attr('x1', (d) => d.source.x)
                    .attr('y1', (d) => d.source.y)
                    .attr('x2', (d) => d.target.x)
                    .attr('y2', (d) => d.target.y);
                node
                    .attr('cx', (d) => d.x)
                    .attr('cy', (d) => d.y);
            });
    }

    _edgeKey(edge) {
        const a = typeof edge.source === 'object' ? edge.source.id : edge.source;
        const b = typeof edge.target === 'object' ? edge.target.id : edge.target;
        return `${Math.min(a, b)}_${Math.max(a, b)}`;
    }

    _routeEdgeKeys(nodeId) {
        const keys = new Set();
        if (!nodeId) return keys;
        for (const route of this._graph.routes || []) {
            if (!route.route || !route.route.includes(nodeId)) continue;
            for (let i = 0; i < route.route.length - 1; i++) {
                const a = route.route[i];
                const b = route.route[i + 1];
                keys.add(`${Math.min(a, b)}_${Math.max(a, b)}`);
            }
        }
        return keys;
    }

    _drag(svg) {
        const self = this;
        function dragstarted(event, d) {
            if (!event.active && self._simulation) self._simulation.alphaTarget(0.3).restart();
            d.fx = d.x;
            d.fy = d.y;
        }
        function dragged(event, d) {
            d.fx = event.x;
            d.fy = event.y;
        }
        function dragended(event, d) {
            if (!event.active && self._simulation) self._simulation.alphaTarget(0);
            d.fx = null;
            d.fy = null;
        }
        return d3.drag().on('start', dragstarted).on('drag', dragged).on('end', dragended);
    }
}

window.topologyTab = new TopologyTab('topology-panel');
