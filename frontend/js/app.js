/**
 * Single-page controller for the local Mesh Point dashboard.
 * Wires up map, node list, packet feed, stat cards, and WebSocket.
 */
document.addEventListener('DOMContentLoaded', async () => {
    const nodeMap = new NodeMap('map');
    const nodeList = new SimpleNodeList('node-list');
    const packetFeed = new SimplePacketFeed('packet-tbody');

    await _loadInitial(nodeMap, nodeList, packetFeed);
    await _updateStats();
    _checkForUpdate();

    window.concentratorWS.on('packet', (packet) => {
        packetFeed.addPacket(packet);
        nodeMap.updateFromPacket(packet);
        nodeList.updateFromPacket(packet);
        _incrementPacketCount();
    });

    window.concentratorWS.connect();

    setInterval(() => {
        _refreshData(nodeMap, nodeList);
        _updateStats();
    }, 15_000);

    setInterval(_checkForUpdate, 300_000);
});

async function _loadInitial(nodeMap, nodeList, packetFeed) {
    try {
        const [deviceRes, nodesRes, packetsRes] = await Promise.all([
            fetch('/api/device'),
            fetch('/api/nodes'),
            fetch('/api/packets?limit=50'),
        ]);
        const device = await deviceRes.json();
        const nodesData = await nodesRes.json();
        const packetsData = await packetsRes.json();

        _setText('device-name', device.device_name || 'Mesh Point');

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
        const res = await fetch('/api/nodes');
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

function _setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}
