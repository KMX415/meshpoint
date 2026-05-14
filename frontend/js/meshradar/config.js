const host = location.hostname || "localhost";
const port = location.port || "8080";
const base = `${location.protocol}//${host}:${port}`;
const wsProto = location.protocol === "https:" ? "wss" : "ws";

export const CFG = {
  apiBase: `${base}/api`,
  wsUrl: `${wsProto}://${host}:${port}/ws`,
  poll: {
    nodes: 10000,
    deviceStatus: 15000,
    traffic: 5000,
  },
  packetFeedMax: 120,
};
