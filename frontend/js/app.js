/**
 * Single-page controller for the local Mesh Point dashboard.
 * Wires up map, node list, packet feed, stat cards, and WebSocket.
 */
document.addEventListener('DOMContentLoaded', async () => {
    const nodeMap = new NodeMap('map');
    const packetFeed = new SimplePacketFeed('packet-tbody');

    const nodeDrawer = new NodeDrawer('node-drawer', {
        onSendMessage: (node) => _openMessagingForNode(node),
        onViewOnMap: (node) => {
            if (node.latitude && node.longitude) {
                nodeMap.centerOn(node.latitude, node.longitude);
            }
        },
    });

    const nodeCards = new NodeCards('node-list', (node) => nodeDrawer.open(node));

    const backdrop = document.getElementById('node-backdrop');
    if (backdrop) {
        backdrop.addEventListener('click', () => {
            nodeDrawer.close();
            backdrop.classList.remove('nd-backdrop--visible');
        });
    }

    const origOpen = nodeDrawer.open.bind(nodeDrawer);
    nodeDrawer.open = async (node) => {
        if (backdrop) backdrop.classList.add('nd-backdrop--visible');
        await origOpen(node);
    };
    const origClose = nodeDrawer.close.bind(nodeDrawer);
    nodeDrawer.close = () => {
        if (backdrop) backdrop.classList.remove('nd-backdrop--visible');
        origClose();
    };

    await _loadInitial(nodeMap, nodeCards, packetFeed);
    await _updateStats();
    _checkForUpdate();

    window.spectrumTab = new SpectrumTab('spectrum-panel');

    window.concentratorWS.on('packet', (packet) => {
        packetFeed.addPacket(packet);
        nodeMap.updateFromPacket(packet);
        nodeCards.updateFromPacket(packet);
        _incrementPacketCount();
    });

    window.concentratorWS.on('spectral_row', (data) => {
        if (window.spectrumTab) window.spectrumTab.onRow(data);
    });

    _setupTabs();

    window.concentratorWS.connect();

    setInterval(() => {
        _refreshData(nodeMap, nodeCards);
        _updateStats();
    }, 15_000);

    setInterval(_checkForUpdate, 300_000);
});

function _openMessagingForNode(node) {
    const msgTab = document.querySelector('[data-tab="messages"]');
    if (msgTab) msgTab.click();

    setTimeout(() => {
        if (window.messagingPanel) {
            window.messagingPanel.openConversation({
                node_id: node.node_id,
                node_name: node.display_name || node.long_name || node.node_id,
                protocol: node.protocol || 'meshtastic',
                is_broadcast: false,
            });
        }
    }, 100);
}

async function _loadInitial(nodeMap, nodeList, packetFeed) {
    try {
        const [deviceRes, nodesRes, packetsRes] = await Promise.all([
            fetch('/api/device'),
            fetch('/api/nodes?enrich=true'),
            fetch('/api/packets?limit=50'),
        ]);
        const device = await deviceRes.json();
        const nodesData = await nodesRes.json();
        const packetsData = await packetsRes.json();

        _setText('device-name', device.device_name || 'Mesh Point');
        if (device.device_id) {
            const short = device.device_id.slice(0, 8);
            const idEl = document.getElementById('device-id');
            if (idEl) {
                idEl.textContent = short;
                idEl.title = device.device_id;
                idEl.addEventListener('click', () => {
                    navigator.clipboard.writeText(device.device_id).then(() => {
                        idEl.textContent = 'copied!';
                        setTimeout(() => { idEl.textContent = short; }, 1500);
                    });
                });
            }
        }

        const nodes = nodesData.nodes || nodesData || [];
        nodeMap.loadNodes(nodes, device);
        nodeList.loadNodes(nodes);

        const packets = packetsData.packets || packetsData || [];
        const sorted = packets.sort((a, b) => {
            const aTime = a.rx_time || new Date(a.timestamp || 0).getTime() / 1000;
            const bTime = b.rx_time || new Date(b.timestamp || 0).getTime() / 1000;
            return aTime - bTime;
        });
        sorted.forEach(pkt => packetFeed.addPacket(pkt));
        _totalPackets = sorted.length;
    } catch (e) {
        console.error('Initial load failed:', e);
    }
}

async function _refreshData(nodeMap, nodeList) {
    try {
        const res = await fetch('/api/nodes?enrich=true');
        const data = await res.json();
        const nodes = data.nodes || data || [];
        nodeMap.loadNodes(nodes);
        nodeList.loadNodes(nodes);
    } catch (e) {
        console.error('Refresh failed:', e);
    }
}

async function _updateStats() {
    try {
        const [trafficRes, signalRes, nodeRes, deviceRes, metricsRes] = await Promise.all([
            fetch('/api/analytics/traffic'),
            fetch('/api/analytics/signal/summary'),
            fetch('/api/nodes/count'),
            fetch('/api/device/status'),
            fetch('/api/device/metrics'),
        ]);

        const traffic = await trafficRes.json();
        const signal = await signalRes.json();
        const nodeCount = await nodeRes.json();
        const device = await deviceRes.json();

        _setText('stat-nodes-val', `${nodeCount.active} / ${nodeCount.count}`);
        _setText('stat-packets-val', traffic.total_packets);
        _setText('stat-rate-val', traffic.packets_per_minute);
        _setText('stat-rssi-val', signal.avg_rssi != null ? `${signal.avg_rssi} dBm` : '--');

        const relay = device.relay || {};
        _setText('stat-relay-val', relay.relayed ?? 0);
        const evaluated = (relay.relayed ?? 0) + (relay.rejected ?? 0);
        _setText('stat-relay-sub', evaluated > 0
            ? `${evaluated} evaluated`
            : relay.enabled ? 'listening...' : 'relay off');

        _setText('stat-uptime-val', _formatUptime(device.uptime_seconds || 0));

        _setText('node-count-badge', `${nodeCount.active} / ${nodeCount.count} nodes`);
        _setText('packet-count-badge', `${traffic.total_packets} packets`);
        _setText('version-badge', device.firmware_version ? `v${device.firmware_version}` : '--');

        if (metricsRes.ok) {
            const metrics = await metricsRes.json();
            _setText('stat-cpu-val', `${metrics.cpu_percent}%`);
            _setText('stat-ram-val', `${metrics.memory_percent}%`);
            _setText('stat-ram-sub', `${metrics.memory_used_mb} / ${metrics.memory_total_mb} MB`);
            _setText('stat-disk-val', `${metrics.disk_percent}%`);
            _setText('stat-disk-sub', `${metrics.disk_used_gb} / ${metrics.disk_total_gb} GB`);
            _setText('stat-temp-val', metrics.cpu_temp_c != null ? `${metrics.cpu_temp_c}°C` : 'N/A');
        }
    } catch (e) {
        console.error('Failed to update stats:', e);
    }
}

let _totalPackets = 0;

function _incrementPacketCount() {
    _totalPackets++;
}

function _formatUptime(totalSeconds) {
    const days = Math.floor(totalSeconds / 86400);
    const hours = Math.floor((totalSeconds % 86400) / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    if (days > 0) return `${days}d ${hours}h`;
    if (hours > 0) return `${hours}h ${minutes}m`;
    return `${minutes}m`;
}

async function _checkForUpdate() {
    try {
        const res = await fetch('/api/device/update-check');
        const data = await res.json();
        const badge = document.getElementById('update-badge');
        if (!badge) return;
        if (data.update_available) {
            badge.classList.remove('hidden');
            badge.title = `Update available (local: ${data.local_version}, remote: ${data.remote_version})`;
        } else {
            badge.classList.add('hidden');
        }
    } catch (_) {}
}

function _setupTabs() {
    document.querySelectorAll('.tab-bar__btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const tabId = btn.dataset.tab;
            document.querySelectorAll('.tab-bar__btn').forEach(b => b.classList.remove('tab-bar__btn--active'));
            btn.classList.add('tab-bar__btn--active');

            document.querySelectorAll('.tab-content').forEach(tc => tc.classList.remove('tab-content--active'));
            const target = document.getElementById(`tab-${tabId}`);
            if (target) target.classList.add('tab-content--active');

            if (tabId === 'messages' && window.messagingPanel) {
                window.messagingPanel.onActivated();
                window.messagingPanel.resetUnreadBadge();
            }
            if (tabId === 'radio' && window.radioSettings) {
                window.radioSettings.onActivated();
            }
            if (tabId === 'stats' && window.statsTab) {
                window.statsTab.refresh();
            }
            if (tabId === 'spectrum' && window.spectrumTab) {
                window.spectrumTab.onActivated();
            }
        });
    });
}

function _setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}
