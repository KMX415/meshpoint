/**
 * RSSI sparkline for node cards.
 *
 * Paints a tiny canvas line chart from 15-minute signal buckets.
 * Gaps longer than one bucket use a dashed connector. Health helpers
 * classify a rolling 1-hour average against configurable thresholds.
 */
class SignalSparkline {
    static DEFAULT_THRESHOLDS = {
        green_rssi_floor: -100,
        yellow_rssi_floor: -115,
        min_packets_per_hour: 5,
    };

    constructor(canvasEl) {
        this._canvas = canvasEl;
        this._ctx = canvasEl.getContext('2d');
        this._buckets = [];
        this._floor = -130;
        this._ceiling = -70;
        this._gapMs = 15 * 60 * 1000;
        this._resize();
        window.addEventListener('resize', () => {
            this._resize();
            this._render();
        });
    }

    static classifyHealth(buckets, thresholds) {
        const t = { ...SignalSparkline.DEFAULT_THRESHOLDS, ...(thresholds || {}) };
        const hourAgo = Date.now() - 3_600_000;
        let packetCount = 0;
        let weighted = 0;

        for (const b of buckets || []) {
            const ts = Date.parse(b.bucket);
            if (Number.isNaN(ts) || ts < hourAgo) continue;
            const count = b.packet_count || 0;
            if (b.rssi_avg == null || count <= 0) continue;
            packetCount += count;
            weighted += b.rssi_avg * count;
        }

        if (packetCount < t.min_packets_per_hour) {
            return { level: null, avgRssi: null, packetCount };
        }

        const avgRssi = weighted / packetCount;
        let level = 'red';
        if (avgRssi >= t.green_rssi_floor) level = 'green';
        else if (avgRssi >= t.yellow_rssi_floor) level = 'yellow';

        return { level, avgRssi, packetCount };
    }

    setBuckets(buckets, opts = {}) {
        this._buckets = Array.isArray(buckets) ? buckets.slice() : [];
        if (opts.bucketMinutes) {
            this._gapMs = opts.bucketMinutes * 60 * 1000;
        }
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

    _bucketMs(bucket) {
        const ts = Date.parse(bucket.bucket);
        return Number.isNaN(ts) ? null : ts;
    }

    _render() {
        const ctx = this._ctx;
        const rect = this._canvas.getBoundingClientRect();
        const w = rect.width;
        const h = rect.height;
        ctx.clearRect(0, 0, w, h);

        const valid = (this._buckets || []).filter(
            (b) => b.rssi_avg != null && (b.packet_count || 0) > 0,
        );
        if (valid.length < 1) return;

        const floor = this._floor;
        const top = this._ceiling;
        const range = top - floor;
        if (range <= 0) return;

        const times = valid.map((b) => this._bucketMs(b)).filter((t) => t != null);
        if (!times.length) return;
        const minT = Math.min(...times);
        const maxT = Math.max(...times);
        const span = Math.max(maxT - minT, this._gapMs);

        const toPoint = (bucket) => {
            const t = this._bucketMs(bucket);
            const clamped = Math.max(floor, Math.min(top, bucket.rssi_avg));
            const yFraction = 1 - (clamped - floor) / range;
            const x = span > 0 ? ((t - minT) / span) * w : w * 0.5;
            return { x, y: yFraction * h, rssi: bucket.rssi_avg };
        };

        const points = valid.map(toPoint);
        const strokeFor = (rssi) => {
            if (rssi >= -95) return '#22c55e';
            if (rssi >= -110) return '#f59e0b';
            return '#ef4444';
        };

        const drawSegment = (from, to, dashed) => {
            ctx.save();
            ctx.strokeStyle = strokeFor(to.rssi);
            ctx.lineWidth = dashed ? 1.25 : 1.75;
            if (dashed) ctx.setLineDash([3, 3]);
            ctx.beginPath();
            ctx.moveTo(from.x, from.y);
            ctx.lineTo(to.x, to.y);
            ctx.stroke();
            ctx.restore();
        };

        for (let i = 1; i < points.length; i++) {
            const prev = valid[i - 1];
            const curr = valid[i];
            const prevMs = this._bucketMs(prev);
            const currMs = this._bucketMs(curr);
            const gap = currMs != null && prevMs != null ? currMs - prevMs : 0;
            drawSegment(points[i - 1], points[i], gap > this._gapMs * 1.5);
        }

        const last = points[points.length - 1];
        ctx.fillStyle = strokeFor(last.rssi);
        ctx.beginPath();
        ctx.arc(last.x, last.y, 2, 0, Math.PI * 2);
        ctx.fill();
    }
}

window.SignalSparkline = SignalSparkline;
