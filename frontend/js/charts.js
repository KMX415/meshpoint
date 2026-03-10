class DashboardCharts {
    constructor() {
        this.trafficChart = null;
        this.rssiChart = null;
        this._initCharts();
    }

    _initCharts() {
        Chart.defaults.color = '#94a3b8';
        Chart.defaults.borderColor = '#2a3a4e';
        Chart.defaults.font.family = "'JetBrains Mono', monospace";
        Chart.defaults.font.size = 11;

        this.trafficChart = new Chart(
            document.getElementById('chart-traffic'),
            {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [{
                        label: 'Packets',
                        data: [],
                        borderColor: '#06b6d4',
                        backgroundColor: 'rgba(6, 182, 212, 0.1)',
                        fill: true,
                        tension: 0.3,
                        pointRadius: 2,
                    }],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false },
                        title: {
                            display: true,
                            text: 'Packet Traffic (Last Hour)',
                            color: '#94a3b8',
                        },
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                            grid: { color: '#1a2332' },
                        },
                        x: {
                            grid: { display: false },
                        },
                    },
                },
            }
        );

        this.rssiChart = new Chart(
            document.getElementById('chart-rssi'),
            {
                type: 'bar',
                data: {
                    labels: [],
                    datasets: [{
                        label: 'Packets',
                        data: [],
                        backgroundColor: 'rgba(59, 130, 246, 0.6)',
                        borderColor: '#3b82f6',
                        borderWidth: 1,
                    }],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false },
                        title: {
                            display: true,
                            text: 'RSSI Distribution (dBm)',
                            color: '#94a3b8',
                        },
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                            grid: { color: '#1a2332' },
                        },
                        x: {
                            grid: { display: false },
                        },
                    },
                },
            }
        );
    }

    async updateTraffic() {
        try {
            const res = await fetch('/api/analytics/traffic/timeline?minutes=60&bucket_minutes=5');
            const data = await res.json();
            this.trafficChart.data.labels = data.labels;
            this.trafficChart.data.datasets[0].data = data.counts;
            this.trafficChart.update('none');
        } catch (e) {
            console.error('Failed to update traffic chart:', e);
        }
    }

    async updateRSSI() {
        try {
            const res = await fetch('/api/analytics/signal/rssi');
            const data = await res.json();
            this.rssiChart.data.labels = data.buckets;
            this.rssiChart.data.datasets[0].data = data.counts;
            this.rssiChart.update('none');
        } catch (e) {
            console.error('Failed to update RSSI chart:', e);
        }
    }

    async updateAll() {
        await Promise.all([this.updateTraffic(), this.updateRSSI()]);
    }
}

window.DashboardCharts = DashboardCharts;
