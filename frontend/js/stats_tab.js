/**
 * Stats tab: comprehensive local stats dashboard matching the cloud Meshradar
 * per-Meshpoint stats page. Sections: hero, protocols, signal intelligence,
 * range, reception, network, protocol detail, relay.
 */

const ROLE_NAMES = {
    0: 'Client', 1: 'Client Mute', 2: 'Router', 3: 'Router Client',
    4: 'Repeater', 5: 'Tracker', 6: 'Sensor', 7: 'TAK', 8: 'Client Hidden',
    9: 'Lost & Found', 10: 'TAK Tracker',
};

const HW_NAMES = {
    0: 'UNSET',
    1: 'TLORA V2', 2: 'TLORA V1', 3: 'TLORA V2 1.6', 4: 'TBEAM',
    5: 'HELTEC V2.0', 6: 'TBEAM V0.7', 7: 'T-ECHO', 8: 'TLORA V1.1.3',
    9: 'RAK4631', 10: 'HELTEC V2.1', 11: 'HELTEC V1', 12: 'LILYGO TBEAM S3',
    13: 'RAK11200', 14: 'NANO G1', 15: 'TLORA V2.1 1.8', 16: 'TLORA T3 S3',
    17: 'NANO G1 EXPLORER', 18: 'NANO G2 ULTRA', 19: 'LORA TYPE',
    20: 'WIPHONE', 21: 'WIO WM1110', 22: 'RAK2560', 23: 'HELTEC HRU 3601',
    24: 'HELTEC WIRELESS BRIDGE', 25: 'STATION G1', 26: 'RAK11310',
    27: 'SENSELORA RP2040', 28: 'SENSELORA S3', 29: 'CANARYONE',
    30: 'RP2040 LORA', 31: 'STATION G2', 32: 'LORA RELAY V1',
    33: 'T-ECHO PLUS', 34: 'PPR', 35: 'GENIEBLOCKS', 36: 'NRF52 UNKNOWN',
    37: 'PORTDUINO', 38: 'ANDROID SIM', 39: 'DIY V1', 40: 'NRF52840 PCA10059',
    41: 'DR DEV', 42: 'M5STACK', 43: 'HELTEC V3', 44: 'HELTEC WSL V3',
    45: 'BETAFPV 2400 TX', 46: 'BETAFPV 900 NANO TX', 47: 'RPI PICO',
    48: 'HELTEC WIRELESS TRACKER', 49: 'HELTEC WIRELESS PAPER',
    50: 'T-DECK', 51: 'T-WATCH S3', 52: 'PICOMPUTER S3', 53: 'HELTEC HT62',
    54: 'EBYTE ESP32 S3', 55: 'ESP32 S3 PICO', 56: 'CHATTER 2',
    57: 'HELTEC WIRELESS PAPER V1.0', 58: 'HELTEC WIRELESS TRACKER V1.0',
    59: 'UNPHONE', 60: 'TD LORAC', 61: 'CDEBYTE EORA S3', 62: 'TWC MESH V4',
    63: 'NRF52 PROMICRO DIY', 64: 'RADIOMASTER 900 BANDIT NANO',
    65: 'HELTEC CAPSULE SENSOR V3', 66: 'HELTEC VISION MASTER T190',
    67: 'HELTEC VISION MASTER E213', 68: 'HELTEC VISION MASTER E290',
    69: 'HELTEC MESH NODE T114', 70: 'SENSECAP INDICATOR',
    71: 'TRACKER T1000-E', 72: 'RAK3172', 73: 'WIO E5',
    74: 'RADIOMASTER 900 BANDIT', 75: 'ME25LS01 4Y10TD',
    76: 'RP2040 FEATHER RFM95', 77: 'M5STACK COREBASIC', 78: 'M5STACK CORE2',
    79: 'RPI PICO2', 80: 'M5STACK CORES3', 81: 'SEEED XIAO S3', 82: 'MS24SF1',
    83: 'TLORA C6', 84: 'WISMESH TAP', 85: 'ROUTASTIC', 86: 'MESH-TAB',
    87: 'MESHLINK', 88: 'XIAO NRF52 KIT', 89: 'THINKNODE M1',
    90: 'THINKNODE M2', 91: 'T-ETH-ELITE', 92: 'HELTEC SENSOR HUB',
    93: 'MUZI BASE', 94: 'HELTEC MESH POCKET', 95: 'SEEED SOLAR NODE',
    96: 'NOMADSTAR METEOR PRO', 97: 'CROWPANEL', 98: 'LINK 32',
    99: 'SEEED WIO TRACKER L1', 100: 'SEEED WIO TRACKER L1 EINK',
    101: 'MUZI R1 NEO', 102: 'T-DECK PRO', 103: 'T-LORA PAGER',
    104: 'M5STACK RESERVED', 105: 'WISMESH TAG', 106: 'RAK3312',
    107: 'THINKNODE M5', 108: 'HELTEC MESH SOLAR', 109: 'T-ECHO LITE',
    110: 'HELTEC V4', 111: 'M5STACK C6L', 112: 'M5STACK CARDPUTER ADV',
    113: 'HELTEC WIRELESS TRACKER V2', 114: 'T-WATCH ULTRA',
    115: 'THINKNODE M3', 116: 'WISMESH TAP V2', 117: 'RAK3401',
    118: 'RAK6421', 119: 'THINKNODE M4', 120: 'THINKNODE M6',
    121: 'MESHSTICK 1262', 122: 'TBEAM 1 WATT', 123: 'T5 S3 EPAPER PRO',
    124: 'TBEAM BPF', 125: 'MINI EPAPER S3', 126: 'TDISPLAY S3 PRO',
    127: 'HELTEC MESH NODE T096', 128: 'TRACKER T1000-E PRO',
    129: 'THINKNODE M7',
    255: 'PRIVATE HW',
};

const CHART_COLORS = [
    '#06b6d4', '#a855f7', '#f59e0b', '#3b82f6', '#10b981',
    '#ef4444', '#ec4899', '#8b5cf6', '#14b8a6', '#f97316',
    '#eab308', '#6366f1', '#84cc16', '#e11d48',
];

class StatsTab {
    constructor(containerId) {
        this._container = document.getElementById(containerId);
        this._charts = {};
        this._refreshInterval = null;
        this._rendered = false;
    }

    async refresh() {
        try {
            const res = await fetch('/api/stats/summary');
            const data = await res.json();
            if (!this._rendered) {
                this._buildLayout();
                this._rendered = true;
            }
            this._update(data);
        } catch (e) {
            console.error('Stats refresh failed:', e);
        }

        if (!this._refreshInterval) {
            this._refreshInterval = setInterval(() => {
                const section = document.querySelector('[data-section="stats"]');
                if (section && section.classList.contains('section--active')) {
                    this.refresh();
                } else {
                    clearInterval(this._refreshInterval);
                    this._refreshInterval = null;
                }
            }, 15000);
        }
    }

    _buildLayout() {
        this._container.innerHTML = `
        <div class="stats-panel">

            <div class="stats-hero">
                <div>
                    <span id="ss-total" class="stats-hero__number">0</span>
                    <span class="stats-hero__label">packets captured</span>
                </div>
            </div>

            <div class="stats-strip">
                <div class="stats-strip__card">
                    <span id="ss-nodes" class="stats-strip__value">0</span>
                    <span class="stats-strip__label">Nodes Added</span>
                </div>
                <div class="stats-strip__card">
                    <span id="ss-days" class="stats-strip__value">0</span>
                    <span class="stats-strip__label">Days Online</span>
                </div>
                <div class="stats-strip__card">
                    <span id="ss-region" class="stats-strip__value">--</span>
                    <span class="stats-strip__label">Region</span>
                </div>
                <div class="stats-strip__card">
                    <span id="ss-firmware" class="stats-strip__value">--</span>
                    <span class="stats-strip__label">Firmware</span>
                </div>
            </div>

            <section class="stats-section">
                <h2 class="stats-section__title">Protocols</h2>
                <div class="stats-row">
                    <div class="stats-card">
                        <div class="stats-card__label">Protocol Split</div>
                        <div class="stats-card__desc">Meshtastic vs Meshcore packet share</div>
                        <canvas id="sc-protocol"></canvas>
                    </div>
                    <div class="stats-card">
                        <div class="stats-card__label">Packet Types</div>
                        <div class="stats-card__desc">Breakdown by decoded message type</div>
                        <canvas id="sc-types"></canvas>
                    </div>
                </div>
            </section>

            <section class="stats-section">
                <h2 class="stats-section__title">Signal Intelligence</h2>
                <div class="stats-signal-nums">
                    <div class="stats-signal-num">
                        <div class="stats-signal-num__label">Best RSSI</div>
                        <div id="ss-best-rssi" class="stats-signal-num__value">--</div>
                    </div>
                    <div class="stats-signal-num">
                        <div class="stats-signal-num__label">Avg RSSI</div>
                        <div id="ss-avg-rssi" class="stats-signal-num__value">--</div>
                    </div>
                    <div class="stats-signal-num">
                        <div class="stats-signal-num__label">Best SNR</div>
                        <div id="ss-best-snr" class="stats-signal-num__value">--</div>
                    </div>
                    <div class="stats-signal-num">
                        <div class="stats-signal-num__label">Avg SNR</div>
                        <div id="ss-avg-snr" class="stats-signal-num__value">--</div>
                    </div>
                </div>
                <div class="stats-row">
                    <div class="stats-card">
                        <div class="stats-card__label">RSSI Distribution</div>
                        <div class="stats-card__desc">Packet count by signal strength bucket (dBm)</div>
                        <canvas id="sc-rssi"></canvas>
                    </div>
                    <div class="stats-card">
                        <div class="stats-card__label">Avg Signal Quality</div>
                        <div class="stats-card__desc">Average RSSI mapped to 0-100 scale</div>
                        <canvas id="sc-quality"></canvas>
                    </div>
                </div>
            </section>

            <section class="stats-section">
                <h2 class="stats-section__title">Range</h2>
                <div class="stats-range-grid">
                    <div class="stats-range-card">
                        <div class="stats-range-card__header">Farthest Direct Signal</div>
                        <div class="stats-range-card__desc">Received directly by this Meshpoint (0 hops)</div>
                        <div class="stats-range-card__value">
                            <span id="ss-direct-mi" class="stats-range-card__miles">--</span>
                            <span class="stats-range-card__unit">mi</span>
                        </div>
                        <div id="ss-direct-detail" class="stats-range-card__detail"></div>
                        <div class="stats-range-bar"><div id="ss-direct-bar" class="stats-range-bar__fill"></div></div>
                    </div>
                    <div class="stats-range-card">
                        <div class="stats-range-card__header">Farthest Node Via Mesh</div>
                        <div class="stats-range-card__desc">Relayed through other nodes across the mesh</div>
                        <div class="stats-range-card__value">
                            <span id="ss-mesh-mi" class="stats-range-card__miles">--</span>
                            <span class="stats-range-card__unit">mi</span>
                        </div>
                        <div id="ss-mesh-detail" class="stats-range-card__detail"></div>
                        <div class="stats-range-bar"><div id="ss-mesh-bar" class="stats-range-bar__fill stats-range-bar__fill--mesh"></div></div>
                    </div>
                </div>
            </section>

            <section class="stats-section">
                <h2 class="stats-section__title">Reception</h2>
                <div class="stats-row">
                    <div class="stats-card">
                        <div class="stats-card__label">Direct vs Relayed</div>
                        <div class="stats-card__desc">Packets received directly (0 hops) vs relayed through other nodes</div>
                        <canvas id="sc-direct-relayed"></canvas>
                    </div>
                    <div class="stats-card">
                        <div class="stats-card__label">Active Nodes (24h)</div>
                        <div class="stats-card__desc">Nodes seen in the last 24 hours out of all nodes ever captured</div>
                        <canvas id="sc-active-nodes"></canvas>
                    </div>
                </div>
            </section>

            <section class="stats-section" id="ss-network-section" style="display:none">
                <h2 class="stats-section__title">Network</h2>
                <div class="stats-row">
                    <div class="stats-card" id="ss-roles-card" style="display:none">
                        <div class="stats-card__label">Device Roles</div>
                        <div class="stats-card__desc">Distribution of node roles seen on the mesh</div>
                        <canvas id="sc-roles"></canvas>
                    </div>
                    <div class="stats-card" id="ss-hw-card" style="display:none">
                        <div class="stats-card__label">Hardware Models</div>
                        <div class="stats-card__desc">Hardware types reported by nodes via NodeInfo</div>
                        <canvas id="sc-hw"></canvas>
                    </div>
                </div>
            </section>

            <section class="stats-section">
                <h2 class="stats-section__title">Protocol Detail</h2>
                <div id="ss-proto-bars" class="stats-proto-bars"></div>
            </section>

            <section class="stats-section">
                <h2 class="stats-section__title">Relay</h2>
                <div class="stats-row">
                    <div class="stats-card">
                        <div class="stats-card__label">Relay Breakdown</div>
                        <div class="stats-card__desc">Packets relayed vs rejected by the smart relay engine</div>
                        <canvas id="sc-relay"></canvas>
                    </div>
                    <div class="stats-card">
                        <div class="stats-card__label">Rejection Reasons</div>
                        <div class="stats-card__desc">Why packets were not relayed</div>
                        <canvas id="sc-reject"></canvas>
                    </div>
                </div>
            </section>

            <section class="stats-section">
                <h2 class="stats-section__title">Traffic</h2>
                <div class="stats-row">
                    <div class="stats-card stats-card--full">
                        <div class="stats-card__label">Traffic (60 min)</div>
                        <div class="stats-card__desc">Packets per 5-minute bucket over the last hour</div>
                        <canvas id="sc-timeline"></canvas>
                    </div>
                </div>
            </section>

        </div>`;
    }

    _update(data) {
        const live = data.live || {};
        const traffic = data.traffic || {};
        const signal = data.signal || {};
        const network = data.network || {};
        const device = data.device || {};
        const directRelayed = data.direct_relayed || {};

        this._setText('ss-total', (traffic.total_packets || 0).toLocaleString());
        this._setText('ss-nodes', network.total_nodes || 0);
        this._setText('ss-days', this._calcDays(data.first_packet_time, device.days_online));
        this._setText('ss-region', device.region || '--');
        this._setText('ss-firmware', device.firmware || '--');

        this._setText('ss-best-rssi', signal.best_rssi != null ? `${signal.best_rssi} dBm` : '--');
        this._setText('ss-avg-rssi', signal.avg_rssi != null ? `${signal.avg_rssi} dBm` : '--');
        this._setText('ss-best-snr', signal.best_snr != null ? `${signal.best_snr} dB` : '--');
        this._setText('ss-avg-snr', signal.avg_snr != null ? `${signal.avg_snr} dB` : '--');

        this._updateRange(live, data.farthest_mesh);
        this._updateProtocol(live.protocols || traffic.protocol_distribution || {});
        this._updateTypes(live.packet_types || traffic.type_distribution || {});
        this._updateRssiHist(data.rssi_distribution || {});
        this._updateQuality(signal);
        this._updateDirectRelayed(directRelayed, traffic);
        this._updateActiveNodes(network);
        this._updateRoles(network.roles || {});
        this._updateHwModels(network.hw_models || {});
        this._updateProtoBars(live.protocols || traffic.protocol_distribution || {});
        this._updateTimeline(data.traffic_timeline || {});
        this._updateRelay(data.relay || {});
        this._updateRejectReasons(data.relay || {});
    }

    _setText(id, value) {
        const el = document.getElementById(id);
        if (el) el.textContent = value;
    }

    _calcDays(firstPacketTime, fallback) {
        if (firstPacketTime) {
            const first = new Date(firstPacketTime);
            const now = new Date();
            return Math.max(1, Math.floor((now - first) / 86400000));
        }
        return fallback || 0;
    }

    _updateRange(live, farthestMesh) {
        const fd = live.farthest_direct;
        if (fd && fd.miles > 0) {
            this._setText('ss-direct-mi', fd.miles.toFixed(1));
            const detail = [];
            if (fd.rssi) detail.push(`${fd.rssi} dBm`);
            if (fd.node_id) detail.push(fd.node_id);
            this._setText('ss-direct-detail', detail.join('  ·  '));
            const bar = document.getElementById('ss-direct-bar');
            if (bar) bar.style.width = `${Math.min(100, (fd.miles / 200) * 100)}%`;
        }

        if (farthestMesh && farthestMesh.miles > 0) {
            this._setText('ss-mesh-mi', farthestMesh.miles.toFixed(1));
            this._setText('ss-mesh-detail', farthestMesh.node_name || farthestMesh.node_id || '');
            const bar = document.getElementById('ss-mesh-bar');
            if (bar) bar.style.width = `${Math.min(100, (farthestMesh.miles / 300) * 100)}%`;
        }
    }

    _updateProtocol(protocols) {
        const labels = Object.keys(protocols);
        const values = Object.values(protocols);
        const total = values.reduce((a, b) => a + b, 0);
        this._renderDoughnut('sc-protocol', labels, values, CHART_COLORS, total);
    }

    _updateTypes(types) {
        const sorted = Object.entries(types).sort((a, b) => b[1] - a[1]);
        const labels = sorted.map(e => e[0]);
        const values = sorted.map(e => e[1]);
        this._renderHorizontalBar('sc-types', labels, values);
    }

    _updateRssiHist(dist) {
        const buckets = dist.buckets || [];
        const counts = dist.counts || [];
        this._renderChart('sc-rssi', 'bar', {
            labels: buckets,
            datasets: [{
                data: counts,
                backgroundColor: 'rgba(6, 182, 212, 0.6)',
                borderColor: '#06b6d4',
                borderWidth: 1,
            }],
        }, { plugins: { legend: { display: false } } });
    }

    _updateQuality(signal) {
        const avgRssi = signal.avg_rssi;
        if (avgRssi == null) return;
        const quality = Math.max(0, Math.min(100, ((avgRssi + 130) / 90) * 100));
        const remaining = 100 - quality;
        const color = quality >= 70 ? '#22c55e' : quality >= 40 ? '#f59e0b' : '#ef4444';
        this._renderChart('sc-quality', 'doughnut', {
            labels: ['Signal', ''],
            datasets: [{
                data: [quality, remaining],
                backgroundColor: [color, 'rgba(30, 41, 59, 0.5)'],
                borderWidth: 0,
            }],
        }, {
            cutout: '75%',
            plugins: {
                legend: { display: false },
                tooltip: { enabled: false },
            },
        }, `${avgRssi} dBm`);
    }

    _updateDirectRelayed(dr, traffic) {
        const direct = dr.direct || 0;
        const relayed = dr.relayed || 0;
        const total = direct + relayed;
        this._renderDoughnut('sc-direct-relayed',
            ['Direct', 'Relayed'],
            [direct, relayed],
            ['#06b6d4', '#a855f7'],
            total > 0 ? total.toLocaleString() : '0',
        );
    }

    _updateActiveNodes(network) {
        const active = network.active_24h || 0;
        const total = network.total_nodes || 0;
        const inactive = Math.max(0, total - active);
        this._renderDoughnut('sc-active-nodes',
            [`${active} active`, `${inactive} inactive`],
            [active, inactive],
            ['#22c55e', 'rgba(30, 41, 59, 0.5)'],
            `${active} / ${total}`,
        );
    }

    _updateRoles(roles) {
        const card = document.getElementById('ss-roles-card');
        const entries = Object.entries(roles);
        if (entries.length === 0) {
            if (card) card.style.display = 'none';
            this._reconcileNetworkSection();
            return;
        }
        if (card) card.style.display = '';
        const labels = entries.map(([k]) => ROLE_NAMES[k] || k);
        const values = entries.map(([, v]) => v);
        const total = values.reduce((a, b) => a + b, 0);
        this._renderDoughnut('sc-roles', labels, values, CHART_COLORS, total);
        this._reconcileNetworkSection();
    }

    _updateHwModels(hw) {
        const card = document.getElementById('ss-hw-card');
        const entries = Object.entries(hw);
        if (entries.length === 0) {
            if (card) card.style.display = 'none';
            this._reconcileNetworkSection();
            return;
        }
        if (card) card.style.display = '';
        const labels = entries.map(([k]) => HW_NAMES[k] || k);
        const values = entries.map(([, v]) => v);
        const total = values.reduce((a, b) => a + b, 0);
        this._renderDoughnut('sc-hw', labels, values, CHART_COLORS, total);
        this._reconcileNetworkSection();
    }

    _reconcileNetworkSection() {
        const section = document.getElementById('ss-network-section');
        if (!section) return;
        const rolesVisible = document.getElementById('ss-roles-card')?.style.display !== 'none';
        const hwVisible = document.getElementById('ss-hw-card')?.style.display !== 'none';
        section.style.display = rolesVisible || hwVisible ? '' : 'none';
    }

    _updateProtoBars(protocols) {
        const container = document.getElementById('ss-proto-bars');
        if (!container) return;
        const entries = Object.entries(protocols).sort((a, b) => b[1] - a[1]);
        const maxVal = entries.length > 0 ? entries[0][1] : 1;
        container.innerHTML = entries.map(([name, count]) => {
            const pct = Math.max(1, (count / maxVal) * 100);
            return `<div class="stats-proto-row">
                <span class="stats-proto-name">${name}</span>
                <div class="stats-proto-track"><div class="stats-proto-fill" style="width:${pct}%"></div></div>
                <span class="stats-proto-count">${count.toLocaleString()}</span>
            </div>`;
        }).join('');
    }

    _updateTimeline(timeline) {
        const labels = timeline.labels || [];
        const counts = timeline.counts || [];
        this._renderChart('sc-timeline', 'bar', {
            labels,
            datasets: [{
                data: counts,
                backgroundColor: 'rgba(59, 130, 246, 0.6)',
                borderColor: '#3b82f6',
                borderWidth: 1,
            }],
        }, { plugins: { legend: { display: false } } });
    }

    _updateRelay(relay) {
        const relayed = relay.relayed || 0;
        const rejected = relay.rejected || 0;
        this._renderDoughnut('sc-relay',
            ['Relayed', 'Rejected'],
            [relayed, rejected],
            ['#22c55e', '#ef4444'],
        );
    }

    _updateRejectReasons(relay) {
        const reasons = relay.rejection_reasons || {};
        const labels = Object.keys(reasons);
        const values = Object.values(reasons);
        if (labels.length === 0) return;
        this._renderHorizontalBar('sc-reject', labels, values, '#ef4444');
    }

    _renderDoughnut(canvasId, labels, values, colors, centerText) {
        const centerPlugin = centerText != null ? {
            id: `center-${canvasId}`,
            afterDraw(chart) {
                const { ctx, chartArea } = chart;
                const cx = (chartArea.left + chartArea.right) / 2;
                const cy = (chartArea.top + chartArea.bottom) / 2;
                ctx.save();
                ctx.font = 'bold 16px "JetBrains Mono", monospace';
                ctx.fillStyle = '#f1f5f9';
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                ctx.fillText(String(centerText), cx, cy);
                ctx.restore();
            },
        } : null;

        const plugins = [centerPlugin].filter(Boolean);

        this._renderChart(canvasId, 'doughnut', {
            labels,
            datasets: [{
                data: values,
                backgroundColor: colors.slice(0, labels.length),
                borderWidth: 0,
            }],
        }, {
            cutout: '65%',
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        color: '#94a3b8',
                        font: { size: 11 },
                        padding: 8,
                        usePointStyle: true,
                        pointStyleWidth: 8,
                    },
                },
            },
        }, null, plugins);
    }

    _renderHorizontalBar(canvasId, labels, values, color) {
        const barColor = color || '#06b6d4';
        this._renderChart(canvasId, 'bar', {
            labels,
            datasets: [{
                data: values,
                backgroundColor: barColor + '99',
                borderColor: barColor,
                borderWidth: 1,
            }],
        }, {
            indexAxis: 'y',
            plugins: { legend: { display: false } },
            scales: {
                x: { ticks: { color: '#64748b' }, grid: { color: 'rgba(30,41,59,0.5)' } },
                y: { ticks: { color: '#94a3b8', font: { size: 11 } }, grid: { display: false } },
            },
        });
    }

    _renderChart(canvasId, type, data, extraOpts, centerLabel, extraPlugins) {
        const canvas = document.getElementById(canvasId);
        if (!canvas) return;

        if (this._charts[canvasId]) {
            const chart = this._charts[canvasId];
            chart.data = data;
            chart.update('none');
            return;
        }

        const baseOpts = {
            responsive: true,
            maintainAspectRatio: false,
            scales: type === 'bar' && !(extraOpts && extraOpts.indexAxis) ? {
                x: { ticks: { color: '#64748b', font: { size: 10 } }, grid: { color: 'rgba(30,41,59,0.5)' } },
                y: { ticks: { color: '#64748b' }, grid: { color: 'rgba(30,41,59,0.5)' } },
            } : undefined,
        };

        const opts = { ...baseOpts, ...(extraOpts || {}) };
        const plugins = extraPlugins || [];

        this._charts[canvasId] = new Chart(canvas, { type, data, options: opts, plugins });
    }
}

window.statsTab = new StatsTab('stats-panel');
