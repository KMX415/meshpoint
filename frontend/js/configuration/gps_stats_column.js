/**
 * Configuration -> GPS stats column.
 *
 * Right-side panel of the skyplot card. Renders fix mode lamp,
 * coordinates, satellite tally, DOP quality, device info, and last
 * fix timestamp. State-free: every render(status) call rebuilds
 * the values from the supplied GpsStatus snapshot.
 */

(function () {
    'use strict';

    class GpsStatsColumn {
        constructor() {
            this._root = null;
            this._lamp = null;
            this._fields = {};
        }

        mount(root) {
            this._root = root;
            this._root.classList.add('gps-stats');
            this._root.innerHTML = `
                <div class="gps-stats__lamp" data-lamp data-mode="0">
                    <span class="gps-stats__lamp-dot"></span>
                    <span class="gps-stats__lamp-label" data-mode-label>NO FIX</span>
                </div>
                <dl class="gps-stats__grid">
                    ${this._row('Latitude', 'lat')}
                    ${this._row('Longitude', 'lng')}
                    ${this._row('Altitude', 'alt')}
                </dl>
                <hr class="gps-stats__divider"/>
                <dl class="gps-stats__grid">
                    ${this._row('Sats used / view', 'sats')}
                    ${this._row('HDOP / PDOP', 'dop')}
                    ${this._row('Speed', 'speed')}
                </dl>
                <hr class="gps-stats__divider"/>
                <dl class="gps-stats__grid gps-stats__grid--meta">
                    ${this._row('Device', 'device')}
                    ${this._row('Source', 'source')}
                    ${this._row('Last fix', 'last')}
                </dl>
                <p class="gps-stats__error" data-error aria-live="polite"></p>
            `;
            this._lamp = this._root.querySelector('[data-lamp]');
            this._modeLabel = this._root.querySelector('[data-mode-label]');
            this._fields = {
                lat: this._root.querySelector('[data-field="lat"]'),
                lng: this._root.querySelector('[data-field="lng"]'),
                alt: this._root.querySelector('[data-field="alt"]'),
                sats: this._root.querySelector('[data-field="sats"]'),
                dop: this._root.querySelector('[data-field="dop"]'),
                speed: this._root.querySelector('[data-field="speed"]'),
                device: this._root.querySelector('[data-field="device"]'),
                source: this._root.querySelector('[data-field="source"]'),
                last: this._root.querySelector('[data-field="last"]'),
            };
            this._errorEl = this._root.querySelector('[data-error]');
        }

        render(status) {
            if (!status) {
                this._setLamp(0, 'NO DATA');
                Object.values(this._fields).forEach((f) => this._set(f, '—'));
                if (this._errorEl) this._errorEl.textContent = '';
                return;
            }

            const fix = status.fix;
            const mode = (fix && fix.mode) || 0;
            const modeLabel = (fix && fix.mode_label) || (status.available ? 'WAITING' : 'NO FIX');
            this._setLamp(mode, modeLabel);

            this._set(this._fields.lat, this._formatLat(fix && fix.latitude));
            this._set(this._fields.lng, this._formatLng(fix && fix.longitude));
            this._set(this._fields.alt, this._formatAlt(fix && fix.altitude_m));

            const sats = status.satellites;
            this._set(this._fields.sats, this._formatSats(sats));
            this._set(this._fields.dop, this._formatDop(fix));
            this._set(this._fields.speed, this._formatSpeed(fix));

            this._set(this._fields.device, this._formatDevice(status.device));
            this._set(this._fields.source, this._formatSource(status));
            this._set(this._fields.last, this._formatLastFix(status));

            if (this._errorEl) {
                this._errorEl.textContent = status.error || '';
            }
        }

        _row(label, key) {
            return `
                <div class="gps-stats__row">
                    <dt class="gps-stats__label">${label}</dt>
                    <dd class="gps-stats__value" data-field="${key}">—</dd>
                </div>
            `;
        }

        _set(el, text) {
            if (el) el.textContent = text;
        }

        _setLamp(mode, label) {
            if (!this._lamp) return;
            this._lamp.dataset.mode = String(mode);
            if (this._modeLabel) this._modeLabel.textContent = label;
        }

        _formatLat(value) {
            if (!Number.isFinite(value)) return '—';
            return `${value.toFixed(6)}°`;
        }

        _formatLng(value) {
            if (!Number.isFinite(value)) return '—';
            return `${value.toFixed(6)}°`;
        }

        _formatAlt(value) {
            if (!Number.isFinite(value)) return '—';
            return `${value.toFixed(1)} m`;
        }

        _formatSats(sats) {
            if (!sats) return '— / —';
            const used = Number.isFinite(sats.used) ? sats.used : '—';
            const view = Number.isFinite(sats.in_view) ? sats.in_view : '—';
            return `${used} / ${view}`;
        }

        _formatDop(fix) {
            if (!fix) return '— / —';
            const fmt = (v) => (Number.isFinite(v) ? v.toFixed(1) : '—');
            return `${fmt(fix.hdop)} / ${fmt(fix.pdop)}`;
        }

        _formatSpeed(fix) {
            if (!fix || !Number.isFinite(fix.speed_mps)) return '—';
            const mps = fix.speed_mps;
            if (mps < 0.5) return 'stationary';
            const kph = mps * 3.6;
            return `${kph.toFixed(1)} km/h`;
        }

        _formatDevice(device) {
            if (!device) return 'static config';
            const model = device.model || device.driver || 'GPS';
            const path = device.path ? ` @ ${device.path}` : '';
            return `${model}${path}`;
        }

        _formatSource(status) {
            const name = (status.source || 'static').toLowerCase();
            if (!status.available) return `${name} (offline)`;
            if (name === 'gpsd' && !status.fix) return 'gpsd (waiting)';
            return name;
        }

        _formatLastFix(status) {
            const ts = (status.fix && status.fix.time) || status.last_update;
            if (!ts) return '—';
            try {
                const d = new Date(ts);
                if (Number.isNaN(d.getTime())) return ts;
                return d.toISOString().replace('T', ' ').slice(0, 19) + ' UTC';
            } catch (e) {
                return ts;
            }
        }
    }

    window.GpsStatsColumn = GpsStatsColumn;
}());
