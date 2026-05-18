/**
 * Noise-floor sparkline.
 *
 * Renders a tiny canvas line chart of the most recent noise-floor
 * samples. Three responsibilities:
 *   - Sizes the canvas to the host element with devicePixelRatio so
 *     the line stays crisp at any zoom or HiDPI display.
 *   - Maps sample dBm values into the canvas y-axis using the
 *     theoretical floor as the bottom anchor and -80 dBm as the top.
 *   - Colors the trace by margin above theoretical:
 *       within 5 dB  -> green  (clean channel)
 *       5-15 dB      -> amber  (some background traffic)
 *       >15 dB       -> red    (interference / congestion)
 *
 * Single responsibility: paint the canvas. Does no networking; the
 * orchestrator feeds it via setSamples().
 */
class NoiseFloorSparkline {
    constructor(canvasEl) {
        this._canvas = canvasEl;
        this._ctx = canvasEl.getContext('2d');
        this._samples = [];
        this._floor = null;
        this._ceiling = -80;
        this._resize();
        window.addEventListener('resize', () => {
            this._resize();
            this._render();
        });
    }

    setSamples(samples, theoreticalFloorDbm) {
        this._samples = Array.isArray(samples) ? samples : [];
        this._floor = theoreticalFloorDbm;
        this._render();
    }

    _resize() {
        const dpr = window.devicePixelRatio || 1;
        const rect = this._canvas.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) return;
        this._canvas.width = Math.floor(rect.width * dpr);
        this._canvas.height = Math.floor(rect.height * dpr);
        this._ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    _render() {
        const ctx = this._ctx;
        const rect = this._canvas.getBoundingClientRect();
        const w = rect.width;
        const h = rect.height;
        ctx.clearRect(0, 0, w, h);
        if (this._samples.length < 2) return;

        const floor = this._floor != null ? this._floor : -120;
        const top = this._ceiling;
        const range = top - floor;
        if (range <= 0) return;

        // Mid-line as a faint reference.
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.05)';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(0, h * 0.5);
        ctx.lineTo(w, h * 0.5);
        ctx.stroke();

        const stepX = w / (this._samples.length - 1);
        const points = this._samples.map((dbm, i) => {
            const clamped = Math.max(floor, Math.min(top, dbm));
            const yFraction = 1 - (clamped - floor) / range;
            return { x: i * stepX, y: yFraction * h };
        });

        const latest = this._samples[this._samples.length - 1];
        const margin = latest - floor;
        let stroke = '#00e5a0'; // green
        if (margin > 15) stroke = '#ef4444';
        else if (margin > 5) stroke = '#f59e0b';

        // Glow underlay.
        ctx.strokeStyle = stroke;
        ctx.lineWidth = 2;
        ctx.shadowColor = stroke;
        ctx.shadowBlur = 6;
        ctx.beginPath();
        ctx.moveTo(points[0].x, points[0].y);
        for (let i = 1; i < points.length; i++) {
            ctx.lineTo(points[i].x, points[i].y);
        }
        ctx.stroke();
        ctx.shadowBlur = 0;

        // Final-point dot.
        const last = points[points.length - 1];
        ctx.fillStyle = stroke;
        ctx.beginPath();
        ctx.arc(last.x, last.y, 1.8, 0, Math.PI * 2);
        ctx.fill();
    }
}

window.NoiseFloorSparkline = NoiseFloorSparkline;
