document.addEventListener('DOMContentLoaded', async () => {
    const nodeMap = new NodeMap('map');
    const charts = new DashboardCharts();
    const nodeList = new NodeList('node-list');
    const packetFeed = new PacketFeed('packet-tbody', 200);

    await Promise.all([
        nodeMap.loadNodes(),
        charts.updateAll(),
        nodeList.loadNodes(),
        packetFeed.loadRecent(),
        updateStats(),
    ]);

    nodeMap.invalidateSize();

    window.concentratorWS.on('packet', (packet) => {
        packetFeed.addPacket(packet);
        nodeList.updateFromPacket(packet);
    });

    window.concentratorWS.on('connected', () => {
        console.log('WebSocket connected');
    });

    window.concentratorWS.connect();

    setInterval(async () => {
        await charts.updateAll();
        await nodeMap.loadNodes();
        await nodeList.loadNodes();
        await updateStats();
    }, 15000);
});

async function updateStats() {
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

        setText('stat-nodes-val', nodeCount.count);
        setText('stat-packets-val', traffic.total_packets);
        setText('stat-rate-val', traffic.packets_per_minute);
        setText('stat-rssi-val', signal.avg_rssi != null ? `${signal.avg_rssi} dBm` : '--');

        const relay = device.relay || {};
        setText('stat-relay-val', relay.relayed ?? 0);
        const evaluated = (relay.relayed ?? 0) + (relay.rejected ?? 0);
        setText('stat-relay-sub', evaluated > 0
            ? `${evaluated} evaluated`
            : relay.enabled ? 'listening...' : 'relay off');

        setText('stat-uptime-val', formatUptime(device.uptime_seconds || 0));

        setText('node-count-badge', `${nodeCount.count} nodes`);
        setText('packet-count-badge', `${traffic.total_packets} packets`);
        setText('version-badge', device.firmware_version ? `v${device.firmware_version}` : '--');

        if (metricsRes.ok) {
            const metrics = await metricsRes.json();
            setText('stat-cpu-val', `${metrics.cpu_percent}%`);
            setText('stat-ram-val', `${metrics.memory_percent}%`);
            setText('stat-ram-sub', `${metrics.memory_used_mb} / ${metrics.memory_total_mb} MB`);
            setText('stat-disk-val', `${metrics.disk_percent}%`);
            setText('stat-disk-sub', `${metrics.disk_used_gb} / ${metrics.disk_total_gb} GB`);
            setText('stat-temp-val', metrics.cpu_temp_c != null ? `${metrics.cpu_temp_c}°C` : 'N/A');
        }
    } catch (e) {
        console.error('Failed to update stats:', e);
    }
}

function formatUptime(totalSeconds) {
    const days = Math.floor(totalSeconds / 86400);
    const hours = Math.floor((totalSeconds % 86400) / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    if (days > 0) return `${days}d ${hours}h`;
    if (hours > 0) return `${hours}h ${minutes}m`;
    return `${minutes}m`;
}

function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}
