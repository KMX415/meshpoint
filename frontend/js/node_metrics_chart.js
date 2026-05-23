/**
 * Node drawer time-series chart (Chart.js).
 * Meshtastic-style device metrics: battery, voltage, util, temperature, RSSI.
 */
class NodeMetricsChart {
    constructor(canvas) {
        this._canvas = canvas;
        this._chart = null;
        this._timeSpanMs = 0;
    }

    destroy() {
        if (this._chart) {
            this._chart.destroy();
            this._chart = null;
        }
    }

    /**
     * @param {{ telemetry: object[], signal: object[] }} history
     */
    render(history) {
        this.destroy();
        if (!window.Chart || !this._canvas) return false;

        const datasets = this._buildDatasets(history || {});
        if (datasets.length === 0) return false;

        const bounds = this._timeBounds(datasets);
        this._timeSpanMs = bounds.max - bounds.min;

        this._chart = new Chart(this._canvas, {
            type: 'line',
            data: { datasets },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'nearest', axis: 'x', intersect: false },
                plugins: {
                    legend: {
                        display: true,
                        position: 'bottom',
                        onClick: (evt, item, legend) => {
                            const chart = legend.chart;
                            const idx = item.datasetIndex;
                            chart.setDatasetVisibility(
                                idx,
                                !chart.isDatasetVisible(idx),
                            );
                            chart.update();
                            this._syncAxes(chart);
                        },
                        labels: {
                            boxWidth: 10,
                            font: { size: 10 },
                            color: '#94a3b8',
                            generateLabels: (chart) => {
                                const defaults = Chart.defaults.plugins.legend.labels
                                    .generateLabels(chart);
                                return defaults.map((item) => {
                                    const hidden = !chart.isDatasetVisible(item.datasetIndex);
                                    return {
                                        ...item,
                                        textDecoration: hidden ? 'line-through' : '',
                                        fontColor: hidden ? '#475569' : '#94a3b8',
                                    };
                                });
                            },
                        },
                    },
                    tooltip: {
                        filter: (item) => item.chart.isDatasetVisible(item.datasetIndex),
                        callbacks: {
                            title: (items) => {
                                if (!items.length) return '';
                                const x = items[0].parsed.x;
                                return new Date(x).toLocaleString([], {
                                    month: 'short',
                                    day: 'numeric',
                                    hour: '2-digit',
                                    minute: '2-digit',
                                });
                            },
                            label: (ctx) => this._tooltipLabel(ctx),
                        },
                    },
                },
                scales: this._buildScales(datasets, bounds),
            },
        });
        this._syncAxes(this._chart);
        return true;
    }

    _buildScales(datasets, bounds) {
        const hasAxis = (id) => datasets.some(
            (d) => d.yAxisID === id && !d.hidden,
        );
        return {
            x: {
                type: 'linear',
                min: bounds.min,
                max: bounds.max,
                ticks: {
                    maxTicksLimit: 6,
                    color: '#64748b',
                    font: { size: 9 },
                    callback: (v) => this._formatAxisTime(v),
                },
                grid: { color: 'rgba(51, 65, 85, 0.35)' },
            },
            y: {
                display: hasAxis('y'),
                position: 'left',
                min: 0,
                max: 100,
                title: {
                    display: hasAxis('y'),
                    text: '%',
                    color: '#22c55e',
                    font: { size: 9 },
                },
                ticks: { color: '#64748b', font: { size: 9 } },
                grid: { color: 'rgba(51, 65, 85, 0.25)' },
            },
            y1: {
                display: hasAxis('y1'),
                position: 'right',
                min: 0,
                max: 5.5,
                title: {
                    display: hasAxis('y1'),
                    text: 'V',
                    color: '#eab308',
                    font: { size: 9 },
                },
                ticks: { color: '#64748b', font: { size: 9 } },
                grid: { drawOnChartArea: false },
            },
            y2: {
                display: hasAxis('y2'),
                position: 'right',
                min: -120,
                max: -40,
                title: {
                    display: hasAxis('y2'),
                    text: 'dBm',
                    color: '#06b6d4',
                    font: { size: 9 },
                },
                ticks: { color: '#64748b', font: { size: 9 } },
                grid: { drawOnChartArea: false },
            },
            y3: {
                display: hasAxis('y3'),
                position: 'right',
                title: {
                    display: hasAxis('y3'),
                    text: '°C',
                    color: '#f97316',
                    font: { size: 9 },
                },
                ticks: { color: '#64748b', font: { size: 9 } },
                grid: { drawOnChartArea: false },
            },
        };
    }

    _syncAxes(chart) {
        if (!chart) return;
        const ids = ['y', 'y1', 'y2', 'y3'];
        for (const id of ids) {
            const scale = chart.scales[id];
            if (!scale) continue;
            const inUse = chart.data.datasets.some(
                (ds, i) => ds.yAxisID === id && chart.isDatasetVisible(i),
            );
            scale.options.display = inUse;
        }
        chart.update('none');
    }

    _timeBounds(datasets) {
        let min = Infinity;
        let max = -Infinity;
        for (const ds of datasets) {
            for (const pt of ds.data) {
                if (pt.x < min) min = pt.x;
                if (pt.x > max) max = pt.x;
            }
        }
        if (!Number.isFinite(min)) {
            const now = Date.now();
            return { min: now - 3600000, max: now };
        }
        const pad = Math.max((max - min) * 0.02, 60000);
        return { min: min - pad, max: max + pad };
    }

    _buildDatasets(history) {
        const out = [];
        const telem = history.telemetry || [];
        const signal = this._downsampleSignal(history.signal || [], 350);

        this._addSeries(out, 'Battery', '#22c55e', 'y', telem, (t) => {
            const v = t.battery_level;
            return v != null && v > 0 ? v : null;
        }, false);
        this._addSeries(out, 'Voltage', '#eab308', 'y1', telem, (t) => t.voltage, false);
        this._addSeries(out, 'ChUtil', '#a855f7', 'y', telem, (t) => t.channel_utilization, false);
        this._addSeries(out, 'AirUtil', '#3b82f6', 'y', telem, (t) => t.air_util_tx, false);
        this._addSeries(out, 'Temp', '#f97316', 'y3', telem, (t) => {
            if (t.temperature == null) return null;
            const c = Number(t.temperature);
            if (Number.isNaN(c) || c === 0 || c < -60 || c > 85) return null;
            return c;
        }, false);
        // RSSI is dense: hidden by default; click legend to show.
        this._addSeries(out, 'RSSI', '#06b6d4', 'y2', signal, (s) => s.rssi, true);

        return out.filter((d) => d.data.length >= 2);
    }

    _downsampleSignal(rows, maxPoints) {
        if (rows.length <= maxPoints) return rows;
        const step = Math.ceil(rows.length / maxPoints);
        const out = [];
        for (let i = 0; i < rows.length; i += step) {
            out.push(rows[i]);
        }
        if (out[out.length - 1] !== rows[rows.length - 1]) {
            out.push(rows[rows.length - 1]);
        }
        return out;
    }

    _addSeries(list, label, color, yAxisID, rows, pick, hiddenDefault) {
        const data = [];
        for (const row of rows) {
            const y = pick(row);
            if (y == null || Number.isNaN(Number(y))) continue;
            const x = this._parseTimestamp(row.timestamp);
            if (Number.isNaN(x)) continue;
            data.push({ x, y: Number(y) });
        }
        if (data.length === 0) return;
        data.sort((a, b) => a.x - b.x);
        list.push({
            label,
            data,
            yAxisID,
            hidden: hiddenDefault,
            borderColor: color,
            backgroundColor: color + (label === 'RSSI' ? '18' : '22'),
            borderWidth: label === 'RSSI' ? 1 : 1.5,
            pointRadius: 0,
            pointHitRadius: 8,
            tension: label === 'RSSI' ? 0 : 0.25,
            fill: label === 'Battery' || label === 'Voltage',
            spanGaps: true,
        });
    }

    _parseTimestamp(ts) {
        if (!ts) return NaN;
        const s = String(ts).trim();
        const iso = s.includes('T') ? s : s.replace(' ', 'T');
        return new Date(iso).getTime();
    }

    _formatAxisTime(ms) {
        const d = new Date(ms);
        if (this._timeSpanMs > 6 * 3600000) {
            return d.toLocaleString([], {
                month: 'short',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit',
            });
        }
        return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }

    _tooltipLabel(ctx) {
        const label = ctx.dataset.label || '';
        const value = ctx.parsed.y;
        if (label === 'Temp' && window.MeshpointDisplayUnits) {
            const formatted = window.MeshpointDisplayUnits.formatTemperature(value);
            return formatted ? `${label}: ${formatted}` : `${label}: ${value.toFixed(1)}`;
        }
        if (label === 'RSSI') return `${label}: ${value.toFixed(1)} dBm`;
        if (label === 'Voltage') return `${label}: ${value.toFixed(2)} V`;
        if (label === 'Battery') return `${label}: ${value.toFixed(0)}%`;
        if (label === 'ChUtil' || label === 'AirUtil') {
            return `${label}: ${value.toFixed(1)}%`;
        }
        return `${label}: ${value}`;
    }
}

window.NodeMetricsChart = NodeMetricsChart;
