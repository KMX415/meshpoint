export const PORTNUM_META = {
  TEXT_MESSAGE_APP: { label: "TEXT", cls: "ms-pkt-type--text" },
  POSITION_APP: { label: "POS", cls: "ms-pkt-type--pos" },
  TELEMETRY_APP: { label: "TELEM", cls: "ms-pkt-type--telem" },
  NODEINFO_APP: { label: "NODE", cls: "ms-pkt-type--node" },
  TRACEROUTE_APP: { label: "TRACE", cls: "ms-pkt-type--route" },
  ADMIN_APP: { label: "ADMIN", cls: "ms-pkt-type--admin" },
  UNKNOWN_APP: { label: "ENC", cls: "ms-pkt-type--enc" },
};

const ENCRYPTED_FILTER_VALUE = "__ENCRYPTED__";

export function getPortnumMeta(portnum) {
  return PORTNUM_META[portnum] || { label: "UNK", cls: "ms-pkt-type--enc" };
}

function formatTime(ts) {
  const d = new Date(ts);
  return [d.getHours(), d.getMinutes(), d.getSeconds()].map((n) => String(n).padStart(2, "0")).join(":");
}

function shortId(id) {
  if (!id || id === "^all") return id === "^all" ? "all" : "--";
  return id.replace("!", "").slice(-4).toUpperCase();
}

function formatDecoded(pkt) {
  if (!pkt.decoded) return pkt.encrypted ? "[encrypted]" : "";
  if (pkt.decoded.text) return pkt.decoded.text;
  if (pkt.decoded.long_name) return pkt.decoded.long_name;
  return JSON.stringify(pkt.decoded).slice(0, 80);
}

export class PacketFeed {
  constructor(container, { maxRows = 120, onPacketClick = null } = {}) {
    this.container = container;
    this.maxRows = maxRows;
    this.onPacketClick = onPacketClick;
    this._packets = [];
    this._filter = null;
    this._nodeFilter = null;
  }

  loadHistory(packets) {
    this._packets = [...packets].sort((a, b) => b.timestamp - a.timestamp);
    this._rerender();
  }

  addPacket(pkt) {
    this._packets.unshift(pkt);
    this._rerender();
  }

  setFilter(portnum) { this._filter = portnum || null; this._rerender(); }
  setNodeFilter(nodeId) { this._nodeFilter = nodeId || null; this._rerender(); }
  visibleCount() { return this._visiblePackets().length; }

  _visiblePackets() {
    return this._packets.filter((p) => {
      if (this._filter) {
        if (this._filter === ENCRYPTED_FILTER_VALUE) {
          if (!p.encrypted && p.portnum !== "UNKNOWN_APP") return false;
        } else if (p.portnum !== this._filter) return false;
      }
      if (this._nodeFilter && p.from_id !== this._nodeFilter && p.to_id !== this._nodeFilter) return false;
      return true;
    }).slice(0, this.maxRows);
  }

  _rerender() {
    const list = this._visiblePackets();
    this.container.innerHTML = "";
    for (const pkt of list) {
      const meta = getPortnumMeta(pkt.portnum);
      const el = document.createElement("div");
      el.className = "ms-pkt-row";
      el.innerHTML = `
        <span class="ms-pkt-time">${formatTime(pkt.timestamp)}</span>
        <span class="ms-pkt-from">${shortId(pkt.from_id)}</span>
        <span class="ms-pkt-via">${shortId(pkt.via_id)}</span>
        <span class="ms-pkt-body">
          <span class="ms-pkt-type ${meta.cls}">${meta.label}</span>
          <span class="ms-pkt-content">${formatDecoded(pkt)}</span>
        </span>
        <span class="ms-pkt-rssi">${Math.round(pkt.rssi || -120)}</span>
      `;
      el.addEventListener("click", () => this.onPacketClick?.(pkt));
      this.container.appendChild(el);
    }
  }
}
