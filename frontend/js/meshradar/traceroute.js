export class TraceRoutePanel {
  constructor(container) {
    this.container = container;
    this._routes = [];
    this._nodeMap = {};
  }

  setNodeMap(nodeMap) {
    this._nodeMap = nodeMap || {};
    this._rerender();
  }

  loadHistory(packets) {
    this._routes = (packets || []).filter((p) => p.portnum === "TRACEROUTE_APP").slice(0, 30);
    this._rerender();
  }

  addPacket(pkt) {
    if (pkt.portnum !== "TRACEROUTE_APP") return;
    this._routes.unshift(pkt);
    if (this._routes.length > 30) this._routes.pop();
    this._rerender();
  }

  _rerender() {
    this.container.innerHTML = this._routes.map((p) => {
      const time = new Date(p.timestamp).toLocaleTimeString([], { hour12: false });
      const from = this._nodeMap[p.from_id]?.short_name || p.from_id;
      const to = this._nodeMap[p.to_id]?.short_name || p.to_id;
      return `<div class="ms-trace-row">
        <div class="ms-trace-row__meta"><span>${time}</span><span>${Math.round(p.rssi || -120)} dBm</span></div>
        <div class="ms-trace-row__path">${from} to ${to}</div>
      </div>`;
    }).join("");
  }
}
