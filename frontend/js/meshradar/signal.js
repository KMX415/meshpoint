function cssColor(varName, fallback) {
  const raw = getComputedStyle(document.documentElement).getPropertyValue(varName).trim();
  return raw || fallback;
}

export class SignalPanel {
  constructor(container) {
    this.container = container;
    this._traffic = [];
    this._render();
  }

  _render() {
    const cyan = cssColor("--accent-cyan", "#06b6d4");
    const muted = cssColor("--text-muted", "#64748b");
    const barRgb = "rgba(6, 182, 212, 0.45)";
    this.container.innerHTML = `
      <div class="ms-signal-block">
        <div class="ms-signal-block__label">RSSI distribution</div>
        <div class="ms-signal-chart-wrap"><canvas id="mp-rssi-chart"></canvas></div>
      </div>
      <div class="ms-signal-block">
        <div class="ms-signal-block__label">Traffic rate</div>
        <div class="ms-signal-chart-wrap ms-signal-chart-wrap--traffic"><canvas id="mp-traffic-chart"></canvas></div>
      </div>
      <div id="mp-snr-bars" class="ms-signal-block"></div>
    `;
    this._rssiChart = new Chart(document.getElementById("mp-rssi-chart"), {
      type: "bar",
      data: {
        labels: [],
        datasets: [{
          data: [],
          backgroundColor: barRgb,
          borderColor: cyan,
          borderWidth: 1,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { ticks: { color: muted, font: { family: "JetBrains Mono", size: 10 } } },
          y: { ticks: { color: muted, font: { family: "JetBrains Mono", size: 10 } } },
        },
      },
    });
    this._trafficChart = new Chart(document.getElementById("mp-traffic-chart"), {
      type: "line",
      data: {
        labels: [],
        datasets: [{
          data: [],
          borderColor: cyan,
          backgroundColor: "rgba(6, 182, 212, 0.08)",
          fill: true,
          pointRadius: 0,
          tension: 0.35,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { ticks: { color: muted, font: { family: "JetBrains Mono", size: 9 } } },
          y: { ticks: { color: muted, font: { family: "JetBrains Mono", size: 10 } } },
        },
      },
    });
  }

  setRssiDistribution(data) {
    const entries = Object.entries(data.distribution || {}).map(([k, v]) => [Number(k), v]).sort((a, b) => a[0] - b[0]);
    this._rssiChart.data.labels = entries.map(([k]) => `${k}`);
    this._rssiChart.data.datasets[0].data = entries.map(([, v]) => v);
    this._rssiChart.update("none");
  }

  setTraffic(data) {
    this._traffic = [...(data.counts || [])].slice(-60);
    this._trafficChart.data.labels = this._traffic.map((_, i) => `-${this._traffic.length - 1 - i}m`);
    this._trafficChart.data.datasets[0].data = this._traffic;
    this._trafficChart.update("none");
  }

  pushTrafficPoint(value) {
    this._traffic.push(value);
    if (this._traffic.length > 60) this._traffic.shift();
    this._trafficChart.data.labels = this._traffic.map((_, i) => `-${this._traffic.length - 1 - i}m`);
    this._trafficChart.data.datasets[0].data = this._traffic;
    this._trafficChart.update("none");
  }

  setNodes(nodes) {
    const sorted = [...(nodes || [])].sort((a, b) => (b.snr || 0) - (a.snr || 0)).slice(0, 12);
    const el = document.getElementById("mp-snr-bars");
    if (!el) return;
    el.innerHTML = `
      <div class="ms-signal-block__label">SNR (top nodes)</div>
      ${sorted.map((n) => `
        <div class="ms-signal-node-row">
          <span>${n.short_name || n.long_name || n.id}</span>
          <span>${(n.snr || 0).toFixed(1)} dB</span>
        </div>
      `).join("")}
    `;
  }
}
