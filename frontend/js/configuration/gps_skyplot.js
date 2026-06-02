/**
 * Configuration -> GPS skyplot view.
 *
 * Pure SVG renderer for the 360-degree satellite bullseye. Owns no
 * state of its own beyond the rendered DOM: every call to render(sats)
 * rebuilds the satellite layer from scratch. Bullseye rings, cardinal
 * labels, and the slow radar-sweep animation are static and live in
 * the SVG markup so we don't repaint them every poll.
 *
 * Coordinate system:
 *   - input:  azimuth in degrees (0=N, 90=E, 180=S, 270=W),
 *             elevation in degrees (0=horizon, 90=zenith).
 *   - output: SVG x/y in a viewBox of -100..100 with (0,0) at center.
 *
 *   x = sin(az) * (90 - el)
 *   y = -cos(az) * (90 - el)
 *
 * The "(90 - el)" inversion places the zenith at center and the
 * horizon at the outer edge -- the standard GPS skyplot convention.
 *
 * No external libraries. Pure SVG and CSS animation. Design-system
 * tokens only (read from the page palette).
 */

(function () {
    'use strict';

    const VIEWBOX_RADIUS = 95;        // satellites can plot up to here (horizon)
    const RING_RADII = [30, 60, 90];  // 60deg, 30deg, 0deg elevation rings
    const SAT_DOT_MIN = 2.0;
    const SAT_DOT_MAX = 5.0;
    const SNR_MIN = 10;
    const SNR_MAX = 50;

    const CONSTELLATION_SHAPES = {
        GPS: 'circle',
        GLONASS: 'diamond',
        Galileo: 'hex',
        BeiDou: 'square',
        QZSS: 'triangle',
        SBAS: 'cross',
    };

    class GpsSkyplotView {
        constructor() {
            this._root = null;
            this._satLayer = null;
            this._tooltip = null;
        }

        mount(root) {
            this._root = root;
            this._root.classList.add('gps-skyplot');
            this._root.innerHTML = `
                <svg class="gps-skyplot__svg" viewBox="-100 -100 200 200"
                     role="img" aria-label="GPS satellite skyplot">
                    <defs>
                        <radialGradient id="gps-skyplot-bg" cx="50%" cy="50%" r="50%">
                            <stop offset="0%" stop-color="rgba(34, 211, 238, 0.06)"/>
                            <stop offset="100%" stop-color="rgba(11, 13, 18, 0)"/>
                        </radialGradient>
                        <linearGradient id="gps-skyplot-sweep" x1="0" y1="0" x2="1" y2="0">
                            <stop offset="0%" stop-color="rgba(34, 211, 238, 0)"/>
                            <stop offset="80%" stop-color="rgba(34, 211, 238, 0.15)"/>
                            <stop offset="100%" stop-color="rgba(34, 211, 238, 0.55)"/>
                        </linearGradient>
                    </defs>
                    <circle class="gps-skyplot__bg" cx="0" cy="0" r="92"
                            fill="url(#gps-skyplot-bg)"/>
                    <g class="gps-skyplot__rings">
                        ${RING_RADII.map((r, i) => `
                            <circle cx="0" cy="0" r="${r}"
                                    class="gps-skyplot__ring${i === RING_RADII.length - 1
                                        ? ' gps-skyplot__ring--horizon' : ''}"/>
                        `).join('')}
                        <line class="gps-skyplot__crosshair" x1="-90" y1="0" x2="90" y2="0"/>
                        <line class="gps-skyplot__crosshair" x1="0" y1="-90" x2="0" y2="90"/>
                        <circle class="gps-skyplot__zenith" cx="0" cy="0" r="1.5"/>
                    </g>
                    <g class="gps-skyplot__sweep" aria-hidden="true">
                        <path d="M 0 0 L 90 0 A 90 90 0 0 1 ${
                            (90 * Math.cos(Math.PI / 6)).toFixed(2)
                        } ${
                            (-90 * Math.sin(Math.PI / 6)).toFixed(2)
                        } Z" fill="url(#gps-skyplot-sweep)"/>
                    </g>
                    <g class="gps-skyplot__cardinals">
                        <text x="0" y="-94" text-anchor="middle"
                              dominant-baseline="middle">N</text>
                        <text x="94" y="0" text-anchor="middle"
                              dominant-baseline="middle">E</text>
                        <text x="0" y="94" text-anchor="middle"
                              dominant-baseline="middle">S</text>
                        <text x="-94" y="0" text-anchor="middle"
                              dominant-baseline="middle">W</text>
                    </g>
                    <g class="gps-skyplot__satellites" data-sat-layer></g>
                </svg>
                <div class="gps-skyplot__tooltip" data-sat-tooltip aria-hidden="true"></div>
            `;
            this._satLayer = this._root.querySelector('[data-sat-layer]');
            this._tooltip = this._root.querySelector('[data-sat-tooltip]');
        }

        render(satellites) {
            if (!this._satLayer) return;
            const list = Array.isArray(satellites) ? satellites : [];
            this._satLayer.innerHTML = list
                .filter((s) => this._isPlottable(s))
                .map((s) => this._renderSatellite(s))
                .join('');
            this._wireTooltipHandlers();
        }

        _isPlottable(sat) {
            return (
                Number.isFinite(sat.azimuth)
                && Number.isFinite(sat.elevation)
                && sat.elevation >= 0
                && sat.elevation <= 90
            );
        }

        _renderSatellite(sat) {
            const azRad = (sat.azimuth * Math.PI) / 180;
            const r = (90 - sat.elevation) * (VIEWBOX_RADIUS / 90);
            const x = (Math.sin(azRad) * r).toFixed(2);
            const y = (-Math.cos(azRad) * r).toFixed(2);

            const snr = Number.isFinite(sat.snr_dbhz) ? sat.snr_dbhz : 0;
            const radius = this._snrToRadius(snr);
            const cls = this._satClassNames(sat);
            const shape = CONSTELLATION_SHAPES[sat.gnss] || 'circle';
            const label = `PRN ${sat.prn} · ${sat.gnss || 'UNK'} · `
                + `Az ${this._fmt(sat.azimuth)}° El ${this._fmt(sat.elevation)}° · `
                + `SNR ${this._fmt(snr)} dBHz`;

            return `
                <g class="${cls}" data-sat-tip="${this._escape(label)}">
                    ${this._drawShape(shape, x, y, radius)}
                    <text x="${x}" y="${(Number(y) - radius - 1.2).toFixed(2)}"
                          class="gps-skyplot__sat-label"
                          text-anchor="middle">${sat.prn}</text>
                </g>
            `;
        }

        _drawShape(shape, x, y, r) {
            const cx = Number(x);
            const cy = Number(y);
            switch (shape) {
                case 'diamond':
                    return `<polygon points="${cx},${cy - r} ${cx + r},${cy} `
                        + `${cx},${cy + r} ${cx - r},${cy}" class="gps-skyplot__sat-shape"/>`;
                case 'square':
                    return `<rect x="${cx - r}" y="${cy - r}" width="${r * 2}" `
                        + `height="${r * 2}" class="gps-skyplot__sat-shape"/>`;
                case 'triangle':
                    return `<polygon points="${cx},${cy - r * 1.1} `
                        + `${cx + r},${cy + r * 0.6} ${cx - r},${cy + r * 0.6}" `
                        + 'class="gps-skyplot__sat-shape"/>';
                case 'hex': {
                    const pts = [];
                    for (let i = 0; i < 6; i += 1) {
                        const a = (Math.PI / 3) * i + Math.PI / 6;
                        pts.push(`${(cx + r * Math.cos(a)).toFixed(2)},${(cy + r * Math.sin(a)).toFixed(2)}`);
                    }
                    return `<polygon points="${pts.join(' ')}" class="gps-skyplot__sat-shape"/>`;
                }
                case 'cross':
                    return `<g class="gps-skyplot__sat-shape">`
                        + `<line x1="${cx - r}" y1="${cy}" x2="${cx + r}" y2="${cy}"/>`
                        + `<line x1="${cx}" y1="${cy - r}" x2="${cx}" y2="${cy + r}"/>`
                        + `</g>`;
                case 'circle':
                default:
                    return `<circle cx="${cx}" cy="${cy}" r="${r}" `
                        + 'class="gps-skyplot__sat-shape"/>';
            }
        }

        _snrToRadius(snr) {
            const clamped = Math.max(SNR_MIN, Math.min(SNR_MAX, snr));
            const t = (clamped - SNR_MIN) / (SNR_MAX - SNR_MIN);
            return SAT_DOT_MIN + t * (SAT_DOT_MAX - SAT_DOT_MIN);
        }

        _satClassNames(sat) {
            const classes = ['gps-skyplot__sat'];
            if (sat.used) {
                classes.push('gps-skyplot__sat--used');
            } else if (Number.isFinite(sat.snr_dbhz) && sat.snr_dbhz >= 20) {
                classes.push('gps-skyplot__sat--visible');
            } else {
                classes.push('gps-skyplot__sat--weak');
            }
            return classes.join(' ');
        }

        _wireTooltipHandlers() {
            if (!this._tooltip || !this._satLayer) return;
            const groups = this._satLayer.querySelectorAll('[data-sat-tip]');
            groups.forEach((g) => {
                g.addEventListener('mouseenter', (e) => this._showTooltip(e));
                g.addEventListener('mouseleave', () => this._hideTooltip());
            });
        }

        _showTooltip(event) {
            const target = event.currentTarget;
            const text = target.getAttribute('data-sat-tip');
            if (!text) return;
            this._tooltip.textContent = text;
            this._tooltip.dataset.visible = 'true';
            this._tooltip.setAttribute('aria-hidden', 'false');
        }

        _hideTooltip() {
            if (!this._tooltip) return;
            this._tooltip.dataset.visible = 'false';
            this._tooltip.setAttribute('aria-hidden', 'true');
        }

        _fmt(value) {
            return Number.isFinite(value) ? value.toFixed(1) : '?';
        }

        _escape(value) {
            return String(value)
                .replace(/&/g, '&amp;')
                .replace(/"/g, '&quot;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;');
        }
    }

    window.GpsSkyplotView = GpsSkyplotView;
}());
