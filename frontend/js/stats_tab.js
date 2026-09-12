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

// HW_NAMES lives in meshtastic_hw_names.js (shared with node cards/drawer).
// Credit: javastraat/meshpoint 39910a0

class StatsTab {
    constructor(containerId) {
        this._container = document.getElementById(containerId);
        this._charts = new window.StatsChartHost();
        this._refreshInterval = null;
        this._rendered = false;
        this._statusStrip = null;
        this._fetchedAt = null;
        this._rangeData = null;
        if (window.MeshpointDisplayUnits) {
            window.MeshpointDisplayUnits.onChange(() => {
                if (this._rendered && this._rangeData) {
                    this._updateRange(...this._rangeData);
                }
            });
        }
    }

    async refresh() {
        try {
            const res = await fetch('/api/stats/summary');
            const data = await res.json();
            if (!this._rendered) {
                this._buildLayout();
                this._rendered = true;
            }
            this._fetchedAt = Date.now();
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
                            <span id="ss-direct-unit" class="stats-range-card__unit"></span>
                        </div>
                        <div id="ss-direct-detail" class="stats-range-card__detail"></div>
                        <div class="stats-range-bar"><div id="ss-direct-bar" class="stats-range-bar__fill"></div></div>
                    </div>
                    <div class="stats-range-card">
                        <div class="stats-range-card__header">Farthest Node Via Mesh</div>
                        <div class="stats-range-card__desc">Relayed through other nodes across the mesh</div>
                        <div class="stats-range-card__value">
                            <span id="ss-mesh-mi" class="stats-range-card__miles">--</span>
                            <span id="ss-mesh-unit" class="stats-range-card__unit"></span>
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

            <div id="stats-status-strip-host"></div>

        </div>`;

        const host = document.getElementById('stats-status-strip-host');
        if (host && window.StatusStrip) {
            this._statusStrip = new window.StatusStrip(host, 'TRAFFIC');
            this._statusStrip.mount();
        }
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
        // Prefer lifetime SQLite distributions. live.* is the heartbeat
        // window and resets every ~5 min; empty {} is truthy so it used
        // to block the traffic fallback and leave Protocol Split / Packet
        // Types empty (or showing only a handful of recent packets).
        const protocols = window.nonemptyStatsMap(traffic.protocol_distribution)
            || window.nonemptyStatsMap(live.protocols)
            || {};
        const packetTypes = window.nonemptyStatsMap(traffic.type_distribution)
            || window.nonemptyStatsMap(live.packet_types)
            || {};
        this._updateProtocol(protocols);
        this._updateTypes(packetTypes);
        this._updateRssiHist(data.rssi_distribution || {});
        this._updateQuality(signal);
        this._updateDirectRelayed(directRelayed, traffic);
        this._updateActiveNodes(network);
        this._updateRoles(network.roles || {});
        this._updateHwModels(network.hw_models || {});
        this._updateProtoBars(protocols);
        this._updateTimeline(data.traffic_timeline || {});
        this._updateRelay(data.relay || {});
        this._updateRejectReasons(data.relay || {});
        this._updateStatusStrip(traffic, network, device, data.relay || {});
    }

    _updateStatusStrip(traffic, network, device, relay) {
        if (!this._statusStrip) return;
        const total = traffic.total_packets || 0;
        const nodes = network.total_nodes || 0;
        const region = device.region || 'region n/a';
        const relayed = relay.relayed ?? relay.relayed_count ?? 0;
        const rejected = relay.rejected ?? relay.rejected_count ?? 0;
        const relayLine = relay.enabled
            ? `relay ${relayed} ok / ${rejected} blocked`
            : 'relay off';
        this._statusStrip.update(
            [
                'concentrator',
                `${total.toLocaleString()} pkts`,
                `${nodes} nodes`,
                region,
                relayLine,
            ],
            this._fetchedAt,
        );
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
        this._rangeData = [live, farthestMesh];
        const fd = live.farthest_direct;
        this._setRangeDistance('ss-direct', fd?.miles);
        this._setRangeDistance('ss-mesh', farthestMesh?.miles);
        if (fd && fd.miles > 0) {
            const detail = [];
            if (fd.rssi) detail.push(`${fd.rssi} dBm`);
            if (fd.node_id) detail.push(fd.node_id);
            this._setText('ss-direct-detail', detail.join('  ·  '));
            const bar = document.getElementById('ss-direct-bar');
            if (bar) bar.style.width = `${Math.min(100, (fd.miles / 200) * 100)}%`;
        }

        if (farthestMesh && farthestMesh.miles > 0) {
            this._setText('ss-mesh-detail', farthestMesh.node_name || farthestMesh.node_id || '');
            const bar = document.getElementById('ss-mesh-bar');
            if (bar) bar.style.width = `${Math.min(100, (farthestMesh.miles / 300) * 100)}%`;
        }
    }

    _setRangeDistance(prefix, miles) {
        const distance = Number(miles);
        const units = window.MeshpointDisplayUnits;
        const valid = miles != null && Number.isFinite(distance) && distance > 0;
        const formatted = valid
            ? (units ? units.formatDistanceKm(distance / 0.621371) : `${distance.toFixed(1)} mi`)
            : `-- ${units?.getPrefs().distance === 'metric' ? 'km' : 'mi'}`;
        const split = formatted.lastIndexOf(' ');
        this._setText(`${prefix}-mi`, formatted.slice(0, split));
        this._setText(`${prefix}-unit`, formatted.slice(split + 1));
    }

    _updateProtocol(protocols) {
        const labels = Object.keys(protocols);
        const values = Object.values(protocols);
        const total = values.reduce((a, b) => a + b, 0);
        this._charts.renderDoughnut('sc-protocol', labels, values, window.STATS_CHART_COLORS, total);
    }

    _updateTypes(types) {
        const sorted = Object.entries(types).sort((a, b) => b[1] - a[1]);
        const labels = sorted.map(e => e[0]);
        const values = sorted.map(e => e[1]);
        this._charts.renderHorizontalBar('sc-types', labels, values);
    }

    _updateRssiHist(dist) {
        const buckets = dist.buckets || [];
        const counts = dist.counts || [];
        this._charts.renderChart('sc-rssi', 'bar', {
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
        this._charts.renderChart('sc-quality', 'doughnut', {
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
        this._charts.renderDoughnut('sc-direct-relayed',
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
        this._charts.renderDoughnut('sc-active-nodes',
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
        this._charts.renderDoughnut('sc-roles', labels, values, window.STATS_CHART_COLORS, total);
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
        this._charts.renderDoughnut('sc-hw', labels, values, window.STATS_CHART_COLORS, total);
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
        this._charts.renderChart('sc-timeline', 'bar', {
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
        this._charts.renderDoughnut('sc-relay',
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
        this._charts.renderHorizontalBar('sc-reject', labels, values, '#ef4444');
    }

}

window.statsTab = new StatsTab('stats-panel');
