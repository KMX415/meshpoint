import { CFG } from "./config.js";
import { normalizePacket } from "./api.js";

export const WS_STATE = {
  CONNECTING: "connecting",
  CONNECTED: "connected",
  RECONNECTING: "reconnecting",
  CLOSED: "closed",
};

class MeshWS {
  constructor() {
    this._ws = null;
    this._listeners = new Map();
    this._retry = 0;
    this._closed = false;
  }

  on(event, fn) {
    if (!this._listeners.has(event)) this._listeners.set(event, new Set());
    this._listeners.get(event).add(fn);
    return () => this._listeners.get(event)?.delete(fn);
  }

  _emit(event, data) {
    const set = this._listeners.get(event);
    if (!set) return;
    for (const fn of set) {
      try { fn(data); } catch {}
    }
  }

  connect() {
    if (this._closed) return;
    this._emit("state", this._retry === 0 ? WS_STATE.CONNECTING : WS_STATE.RECONNECTING);
    this._ws = new WebSocket(CFG.wsUrl);
    this._ws.onopen = () => {
      this._retry = 0;
      this._emit("state", WS_STATE.CONNECTED);
    };
    this._ws.onclose = () => {
      this._emit("state", WS_STATE.RECONNECTING);
      setTimeout(() => {
        this._retry += 1;
        this.connect();
      }, Math.min(1000 * (2 ** this._retry), 30000));
    };
    this._ws.onmessage = (ev) => {
      let msg;
      try { msg = JSON.parse(ev.data); } catch { return; }
      if (msg?.type === "packet" && msg.data) {
        const pkt = normalizePacket(msg.data);
        this._emit("packet", pkt);
        this._emit(`packet:${pkt.portnum}`, pkt);
      }
    };
  }

  disconnect() {
    this._closed = true;
    this._emit("state", WS_STATE.CLOSED);
    this._ws?.close();
  }
}

export const meshWS = new MeshWS();
