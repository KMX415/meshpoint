export class Topology {
  constructor(canvas, { onNodeSelect = null } = {}) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.onNodeSelect = onNodeSelect;
    this.nodes = [];
    this.positions = {};
    this.selectedId = null;
    this.scale = 1;
    this.offsetX = 0;
    this.offsetY = 0;
    this._resize();
    window.addEventListener("resize", () => this._resize());
    this.canvas.addEventListener("click", (e) => this._click(e));
    requestAnimationFrame(() => this._drawLoop());
  }

  setNodes(nodes) {
    this.nodes = nodes || [];
    const cx = this.w / 2;
    const cy = this.h / 2;
    this.nodes.forEach((n, i) => {
      if (!this.positions[n.id]) {
        const a = (i / Math.max(this.nodes.length, 1)) * Math.PI * 2;
        const r = 120 + ((n.hops_away || 1) * 45);
        this.positions[n.id] = { x: cx + Math.cos(a) * r, y: cy + Math.sin(a) * r };
      }
    });
  }

  selectNode(id) { this.selectedId = id; }
  zoom(factor) { this.scale = Math.max(0.2, Math.min(4, this.scale * factor)); }
  fitAll() { this.scale = 1; this.offsetX = 0; this.offsetY = 0; }

  _resize() {
    const rect = this.canvas.parentElement.getBoundingClientRect();
    this.w = rect.width;
    this.h = rect.height;
    this.canvas.width = this.w;
    this.canvas.height = this.h;
  }

  _drawLoop() {
    this.ctx.clearRect(0, 0, this.w, this.h);
    this.ctx.save();
    this.ctx.translate(this.offsetX, this.offsetY);
    this.ctx.scale(this.scale, this.scale);
    for (const n of this.nodes) {
      const p = this.positions[n.id];
      if (!p) continue;
      this.ctx.beginPath();
      this.ctx.arc(p.x, p.y, n.id === this.selectedId ? 10 : 7, 0, Math.PI * 2);
      this.ctx.fillStyle = n.hops_away === 0 ? "#e8931a" : "#1cb89a";
      this.ctx.fill();
      this.ctx.fillStyle = "#b0c0d0";
      this.ctx.font = "10px monospace";
      this.ctx.textAlign = "center";
      this.ctx.fillText(n.short_name || n.long_name || n.id.slice(-4), p.x, p.y + 18);
    }
    this.ctx.restore();
    requestAnimationFrame(() => this._drawLoop());
  }

  _click(e) {
    const rect = this.canvas.getBoundingClientRect();
    const x = (e.clientX - rect.left - this.offsetX) / this.scale;
    const y = (e.clientY - rect.top - this.offsetY) / this.scale;
    for (const n of this.nodes) {
      const p = this.positions[n.id];
      if (!p) continue;
      const d2 = (x - p.x) ** 2 + (y - p.y) ** 2;
      if (d2 <= 12 ** 2) {
        this.selectedId = n.id;
        this.onNodeSelect?.(n);
        break;
      }
    }
  }
}
