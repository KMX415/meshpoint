import { CFG } from "./config.js";

async function apiFetch(path) {
  const res = await fetch(`${CFG.apiBase}${path}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

function toUnixSeconds(value) {
  if (!value) return Math.floor(Date.now() / 1000);
  if (typeof value === "number") return value > 1e12 ? Math.floor(value / 1000) : value;
  const d = Date.parse(value);
  return Number.isNaN(d) ? Math.floor(Date.now() / 1000) : Math.floor(d / 1000);
}

function normalizeRole(role) {
  if (!role) return "CLIENT";
  return String(role).toUpperCase();
}

function inferNodeSourceType(node) {
  const candidates = [
    node?.last_seen_via,
    node?.last_heard_via,
    node?.source,
    node?.source_type,
    node?.transport,
    node?.ingress,
    node?.rx_source,
    node?.latest_signal?.source,
    node?.latest_signal?.transport,
  ].filter(Boolean).map((v) => String(v).toLowerCase());
  const text = candidates.join(" ");
  if (text.includes("mqtt")) return "MQTT";
  if (text.includes("lora") || text.includes("rf") || text.includes("radio")) return "RF";
  return "UNKNOWN";
}

export async function getNodes() {
  const rows = await apiFetch("/nodes?enrich=true");
  return (rows || []).map((n) => {
    const sig = n.latest_signal || {};
    const tel = n.latest_telemetry || {};
    return {
      id: n.node_id || "",
      long_name: n.long_name || "",
      short_name: n.short_name || "",
      hw_model: n.hardware_model || "",
      role: normalizeRole(n.role),
      lat: n.latitude,
      lon: n.longitude,
      altitude: n.altitude,
      rssi: sig.rssi ?? n.rssi ?? -120,
      snr: sig.snr ?? n.snr ?? 0,
      battery_level: tel.battery_level ?? null,
      last_heard: toUnixSeconds(n.last_heard),
      hops_away: n.hops_away ?? 1,
      neighbors: n.neighbors || [],
      firmware: n.firmware_version || "",
      air_util_tx: tel.air_util_tx ?? null,
      channel_util: tel.channel_utilization ?? null,
      source_type: inferNodeSourceType(n),
    };
  });
}

function normalizePacket(p) {
  const sig = p.signal || {};
  const source = p.source_id || p.from_id || "";
  const dest = p.destination_id || p.to_id || "^all";
  const pktType = String(p.packet_type || p.portnum || "unknown").toLowerCase();
  const portnumMap = {
    text: "TEXT_MESSAGE_APP",
    position: "POSITION_APP",
    telemetry: "TELEMETRY_APP",
    nodeinfo: "NODEINFO_APP",
    traceroute: "TRACEROUTE_APP",
    routing: "ROUTING_APP",
    admin: "ADMIN_APP",
    encrypted: "UNKNOWN_APP",
  };
  const decoded = p.decoded_payload || p.decoded || {};
  return {
    id: p.packet_id || p.id || `${source}-${Date.now()}`,
    timestamp: p.timestamp ? Date.parse(p.timestamp) || Date.now() : Date.now(),
    from_id: source,
    to_id: dest,
    via_id: null,
    portnum: portnumMap[pktType] || String(p.portnum || "UNKNOWN_APP"),
    portnum_int: 0,
    decoded,
    rssi: sig.rssi ?? p.rssi ?? -120,
    snr: sig.snr ?? p.snr ?? 0,
    hop_limit: p.hop_limit ?? 0,
    hop_start: p.hop_start ?? 0,
    rx_time: toUnixSeconds(p.timestamp),
    channel: 0,
    encrypted: p.decrypted === false,
  };
}

export async function getPackets({ limit = 50 } = {}) {
  const rows = await apiFetch(`/packets?limit=${limit}`);
  const packets = (rows || []).map(normalizePacket);
  return { packets, total: packets.length, page: 1 };
}

export async function getTraffic() {
  const data = await apiFetch("/analytics/traffic");
  return {
    rate_per_min: data.packets_per_minute || 0,
    counts: data.counts || [],
    timestamps: data.timestamps || [],
  };
}

export async function getRssiDistribution() {
  const data = await apiFetch("/analytics/signal/rssi");
  return {
    distribution: data.distribution || data || {},
    mean: data.mean ?? null,
    min: data.min ?? null,
    max: data.max ?? null,
  };
}

export async function getDeviceStatus() {
  const [status, device] = await Promise.all([
    apiFetch("/device/status"),
    apiFetch("/device").catch(() => ({})),
  ]);
  const metrics = await apiFetch("/device/metrics").catch(() => ({}));
  return {
    cpu_percent: metrics.cpu_percent ?? 0,
    temp_c: metrics.cpu_temp_c ?? 0,
    uptime_seconds: status.uptime_seconds ?? 0,
    sources: ["concentrator", "meshcore_usb"],
    region: "US",
    frequency_mhz: 906.875,
    device_id: status.device_id ?? device.device_id ?? "",
    device_name: device.device_name ?? "Meshpoint",
    firmware_version: status.firmware_version ?? device.firmware_version ?? "",
  };
}

export async function getUpdateCheck() {
  return apiFetch("/device/update-check");
}

export { normalizePacket };
