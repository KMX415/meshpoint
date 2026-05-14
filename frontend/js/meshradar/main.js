import { CFG } from "./config.js";
import {
  getNodes,
  getPackets,
  getTraffic,
  getRssiDistribution,
  getDeviceStatus,
  getUpdateCheck,
} from "./api.js";
import { meshWS, WS_STATE } from "./ws.js";
import { Topology } from "./topology.js";
import { PacketFeed } from "./packets.js";
import { SignalPanel } from "./signal.js";
import { TraceRoutePanel } from "./traceroute.js";
import { initSystemShell } from "./system_shell.js";

let nodes = [];
let nodeMap = {};
let selectedId = null;
let pktTotal = 0;
let nodeSourceFilter = "ALL";

const topo = new Topology(document.getElementById("topoCanvas"), { onNodeSelect });
const feed = new PacketFeed(document.getElementById("pkt-feed-container"), { maxRows: CFG.packetFeedMax, onPacketClick });
const signal = new SignalPanel(document.getElementById("signal-container"));
const traces = new TraceRoutePanel(document.getElementById("trace-container"));
const packetTypeFilterEl = document.getElementById("pkt-portnum-filter");
const packetCountShowTotalEl = document.getElementById("pkt-count-show-total");
const nodeSourceFilterEl = document.getElementById("node-source-filter");

function getFilteredNodes() {
  if (nodeSourceFilter === "ALL") return nodes;
  return nodes.filter((n) => (n.source_type || "UNKNOWN") === nodeSourceFilter);
}

function sourcePillClass(sourceType) {
  if (sourceType === "RF") return "ms-node-source-pill--rf";
  if (sourceType === "MQTT") return "ms-node-source-pill--mqtt";
  return "ms-node-source-pill--unknown";
}

function updatePacketCountBadge() {
  const badge = document.getElementById("pkt-count-badge");
  if (!badge) return;
  const selectedType = packetTypeFilterEl?.value;
  const showTotal = Boolean(packetCountShowTotalEl?.checked);
  if (selectedType && showTotal) {
    badge.textContent = `${feed.visibleCount()}/${pktTotal}`;
    return;
  }
  badge.textContent = selectedType ? String(feed.visibleCount()) : String(pktTotal);
}

if (packetTypeFilterEl) {
  packetTypeFilterEl.addEventListener("change", () => {
    feed.setFilter(packetTypeFilterEl.value || null);
    updatePacketCountBadge();
  });
}

if (packetCountShowTotalEl) {
  packetCountShowTotalEl.addEventListener("change", () => updatePacketCountBadge());
}

if (nodeSourceFilterEl) {
  nodeSourceFilterEl.addEventListener("change", () => {
    nodeSourceFilter = nodeSourceFilterEl.value || "ALL";
    const visibleNodes = getFilteredNodes();
    topo.setNodes(visibleNodes);
    if (selectedId && !visibleNodes.some((n) => n.id === selectedId)) {
      selectedId = null;
      const hint = document.getElementById("detail-hint");
      if (hint) hint.textContent = "Select a node";
      const dc = document.getElementById("detail-content");
      if (dc) dc.innerHTML = "<div class=\"ms-detail-empty\">Select a node to view details.</div>";
    }
    renderNodeList();
  });
}

function setView(name) {
  document.querySelectorAll(".tab-content").forEach((p) => {
    const on = p.id === `tab-${name}`;
    p.classList.toggle("tab-content--active", on);
  });
  document.querySelectorAll(".tab-bar__btn").forEach((t) => {
    const on = t.dataset.view === name;
    t.classList.toggle("tab-bar__btn--active", on);
    if (t.getAttribute("role") === "tab") t.setAttribute("aria-selected", on ? "true" : "false");
  });
  const stage = document.getElementById("ms-stage");
  if (stage) {
    const single = name === "messages" || name === "radio" || name === "terminal" || name === "system";
    stage.classList.toggle("ms-stage--single", single);
  }
  if (name === "messages" && window.messagingPanel) window.messagingPanel.onActivated();
  if (name === "radio" && window.radioSettings) window.radioSettings.onActivated();
  if (name === "terminal" && window.meshTerminal) window.meshTerminal.onActivated();
}

document.querySelectorAll(".tab-bar__btn").forEach((el) => {
  el.addEventListener("click", () => setView(el.dataset.view));
});

initSystemShell();

function ageStr(lastHeard) {
  const s = Math.max(0, Math.round(Date.now() / 1000 - lastHeard));
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  return `${Math.floor(s / 3600)}h`;
}

function renderNodeList() {
  const el = document.getElementById("node-list");
  const visibleNodes = getFilteredNodes();
  el.innerHTML = visibleNodes.map((n) => `
    <div class="ms-node-entry${n.id === selectedId ? " ms-node-entry--selected" : ""}" data-id="${n.id}">
      <div class="ms-node-entry__line">
        <span class="ms-node-callsign">${n.short_name || n.long_name || n.id}</span>
        <span class="ms-node-source-pill ${sourcePillClass(n.source_type)}">${n.source_type || "UNKNOWN"}</span>
      </div>
      <div class="ms-node-entry__line ms-node-entry__line--meta">
        <span class="ms-node-meta">${Math.round(n.rssi)} dBm</span>
        <span class="ms-node-meta">${ageStr(n.last_heard)} ago</span>
      </div>
    </div>
  `).join("");
  el.querySelectorAll(".ms-node-entry").forEach((entry) => entry.addEventListener("click", () => onNodeSelect(nodeMap[entry.dataset.id])));
}

function onNodeSelect(node) {
  if (!node) return;
  selectedId = node.id;
  topo.selectNode(node.id);
  renderNodeList();
  document.getElementById("detail-hint").textContent = node.short_name || node.long_name || node.id;
  document.getElementById("detail-content").innerHTML = `
    <div class="ms-detail-hero">
      <div class="ms-detail-hero__title">${node.long_name || node.short_name || node.id}</div>
      <div class="ms-detail-hero__meta">${node.hw_model || "unknown hw"} · ${node.role}</div>
    </div>
    <div class="ms-detail-body">
      <div class="ms-detail-row"><span class="ms-detail-row__key">Node ID</span><span class="ms-detail-row__val">${node.id}</span></div>
      <div class="ms-detail-row"><span class="ms-detail-row__key">RSSI</span><span class="ms-detail-row__val">${Math.round(node.rssi)} dBm</span></div>
      <div class="ms-detail-row"><span class="ms-detail-row__key">SNR</span><span class="ms-detail-row__val">${(node.snr || 0).toFixed(1)} dB</span></div>
      <div class="ms-detail-row"><span class="ms-detail-row__key">Seen via</span><span class="ms-detail-row__val">${node.source_type || "UNKNOWN"}</span></div>
      <div class="ms-detail-row"><span class="ms-detail-row__key">Last heard</span><span class="ms-detail-row__val">${ageStr(node.last_heard)} ago</span></div>
    </div>
  `;
}

function onPacketClick(pkt) {
  const node = nodeMap[pkt.from_id];
  if (node) onNodeSelect(node);
}

function syncTopSummaryBadges() {
  const nodes = document.getElementById("stat-nodes")?.textContent ?? "--";
  const pkts = document.getElementById("stat-pkts")?.textContent ?? "--";
  const nEl = document.getElementById("node-count-badge");
  const pEl = document.getElementById("packet-count-badge");
  if (nEl) nEl.textContent = `${nodes} nodes (24h)`;
  if (pEl) pEl.textContent = `${pkts} packets`;
}

function updateConnPill(state) {
  const pill = document.getElementById("conn-pill");
  if (!pill) return;
  const labels = {
    [WS_STATE.CONNECTED]: "LIVE",
    [WS_STATE.CONNECTING]: "CONNECTING",
    [WS_STATE.RECONNECTING]: "RECONNECTING",
    [WS_STATE.CLOSED]: "OFFLINE",
  };
  const mod = {
    [WS_STATE.CONNECTED]: "live",
    [WS_STATE.CONNECTING]: "warn",
    [WS_STATE.RECONNECTING]: "warn",
    [WS_STATE.CLOSED]: "err",
  };
  pill.textContent = labels[state] || String(state);
  pill.className = `top-bar__pill top-bar__pill--${mod[state] || "err"}`;

  const dot = document.getElementById("ws-status");
  const label = document.getElementById("ws-label");
  if (dot && label) {
    const connected = state === WS_STATE.CONNECTED;
    dot.className = connected ? "status-dot status-dot--connected" : "status-dot status-dot--disconnected";
    const wsLabels = {
      [WS_STATE.CONNECTED]: "Connected",
      [WS_STATE.CONNECTING]: "Connecting…",
      [WS_STATE.RECONNECTING]: "Reconnecting…",
      [WS_STATE.CLOSED]: "Offline",
    };
    label.textContent = wsLabels[state] || String(state);
  }
}

meshWS.on("state", updateConnPill);
meshWS.on("packet", (pkt) => {
  pktTotal += 1;
  document.getElementById("stat-pkts").textContent = String(pktTotal);
  syncTopSummaryBadges();
  feed.addPacket(pkt);
  updatePacketCountBadge();
});
meshWS.on("packet:TRACEROUTE_APP", (pkt) => {
  traces.addPacket(pkt);
  const c = document.getElementById("trace-count");
  c.textContent = String((parseInt(c.textContent, 10) || 0) + 1);
});

async function updateDevice() {
  const s = await getDeviceStatus();
  document.getElementById("dev-cpu").textContent = `${(s.cpu_percent || 0).toFixed(1)}%`;
  document.getElementById("dev-temp").textContent = `${(s.temp_c || 0).toFixed(1)}°C`;
  const h = Math.floor((s.uptime_seconds || 0) / 3600);
  const m = Math.floor(((s.uptime_seconds || 0) % 3600) / 60);
  document.getElementById("dev-uptime").textContent = `${h}h ${m}m`;
  document.getElementById("dev-sources").textContent = (s.sources || []).join("+");
  document.getElementById("top-freq").textContent = `${s.region || "US"} · ${s.frequency_mhz || "N/A"} MHz`;

  const nameEl = document.getElementById("device-name");
  if (nameEl) nameEl.textContent = s.device_name || "Meshpoint";

  const idEl = document.getElementById("device-id");
  if (idEl && s.device_id) {
    const full = s.device_id;
    const short = full.slice(0, 8);
    idEl.dataset.fullId = full;
    idEl.textContent = short;
    idEl.title = full;
  }

  const verEl = document.getElementById("version-badge");
  if (verEl) {
    verEl.textContent = s.firmware_version ? `v${s.firmware_version}` : "--";
  }
}

function wireHybridChromeOnce() {
  if (document.body.dataset.hybridChromeWired === "1") return;
  document.body.dataset.hybridChromeWired = "1";

  const idEl = document.getElementById("device-id");
  if (idEl) {
    idEl.addEventListener("click", () => {
      const full = idEl.dataset.fullId;
      if (!full || !navigator.clipboard?.writeText) return;
      const short = full.slice(0, 8);
      navigator.clipboard.writeText(full).then(() => {
        idEl.textContent = "copied!";
        setTimeout(() => { idEl.textContent = short; }, 1500);
      }).catch(() => {});
    });
  }

  document.getElementById("signout-btn")?.addEventListener("click", async () => {
    try {
      const r = await fetch(`${CFG.apiBase}/auth/logout`, { method: "POST", credentials: "same-origin" });
      if (r.ok) window.location.reload();
    } catch {
      /* no auth route in this build */
    }
  });
}

async function refreshUpdateBadge() {
  const badge = document.getElementById("update-badge");
  if (!badge) return;
  try {
    const data = await getUpdateCheck();
    if (data.update_available) {
      badge.classList.remove("hidden");
      badge.title = `Update available (local: ${data.local_version}, remote: ${data.remote_version})`;
    } else {
      badge.classList.add("hidden");
    }
  } catch {
    badge.classList.add("hidden");
  }
}

async function boot() {
  meshWS.connect();
  try {
    nodes = await getNodes();
    nodeMap = Object.fromEntries(nodes.map((n) => [n.id, n]));
    topo.setNodes(getFilteredNodes());
    traces.setNodeMap(nodeMap);
    signal.setNodes(nodes);
    renderNodeList();
    document.getElementById("topo-count").textContent = `${nodes.length} nodes`;
    document.getElementById("stat-nodes").textContent = String(nodes.filter((n) => (Date.now() / 1000 - n.last_heard) < 86400).length);
  } catch (e) { console.error(e); }

  try {
    const { packets, total } = await getPackets({ limit: 60 });
    feed.loadHistory(packets);
    pktTotal = total;
    document.getElementById("stat-pkts").textContent = String(total);
    updatePacketCountBadge();
    const tracePackets = packets.filter((p) => p.portnum === "TRACEROUTE_APP");
    traces.loadHistory(tracePackets);
    document.getElementById("trace-count").textContent = String(tracePackets.length);
  } catch (e) { console.error(e); }

  try {
    const [rssi, traffic] = await Promise.all([getRssiDistribution(), getTraffic()]);
    signal.setRssiDistribution(rssi);
    signal.setTraffic(traffic);
    document.getElementById("stat-rate").textContent = `${(traffic.rate_per_min || 0).toFixed(1)}`;
  } catch (e) { console.error(e); }

  try { await updateDevice(); } catch (e) { console.error(e); }

  wireHybridChromeOnce();
  syncTopSummaryBadges();
  try { await refreshUpdateBadge(); } catch (e) { console.error(e); }
}

setInterval(async () => {
  try {
    nodes = await getNodes();
    nodeMap = Object.fromEntries(nodes.map((n) => [n.id, n]));
    topo.setNodes(getFilteredNodes());
    signal.setNodes(nodes);
    traces.setNodeMap(nodeMap);
    renderNodeList();
    const sn = document.getElementById("stat-nodes");
    if (sn) sn.textContent = String(nodes.filter((n) => (Date.now() / 1000 - n.last_heard) < 86400).length);
    const tc = document.getElementById("topo-count");
    if (tc) tc.textContent = `${nodes.length} nodes`;
    syncTopSummaryBadges();
  } catch {}
}, CFG.poll.nodes);

setInterval(async () => {
  try {
    const t = await getTraffic();
    signal.pushTrafficPoint(t.rate_per_min || 0);
    document.getElementById("stat-rate").textContent = `${(t.rate_per_min || 0).toFixed(1)}`;
  } catch {}
}, CFG.poll.traffic);

setInterval(async () => { try { await updateDevice(); } catch {} }, CFG.poll.deviceStatus);

setInterval(() => { refreshUpdateBadge().catch(() => {}); }, 300_000);

boot();
