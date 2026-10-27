/**
 * Modal showing currently-tracked ADS-B aircraft over a live OpenStreetMap
 * (Leaflet + the same dark-inverted OSM tiles topology_tab.js and
 * node_map.js already use, so the app has exactly one basemap style).
 * Reuses the
 * pdm-overlay/pdm-modal shell (packet_detail_modal.css) with the
 * wide/flush-body modifiers so the map can fill the dialog.
 *
 * Polls /api/adsb/status itself on a 2 s timer while open -- independent of
 * whether AdsbPanel's own tab happens to be mounted -- and tears the
 * Leaflet instance down on close() (L.map() throws "already initialized"
 * if reused against a stale container, so the map is always rebuilt fresh
 * against a new <div> each time show() runs).
 *
 * The plane marker is a rotated plane-silhouette SVG (a standalone path,
 * not a literal reuse of dump1090's bundled Google-Maps plane icon --
 * dump1090/public_html/planeObject.js `funcGetIcon` builds a
 * `google.maps.Symbol` path string tied to the Google Maps API we don't
 * use here) pointed by `track`. What IS borrowed from planeObject.js:
 * rotate-by-track, the emergency squawk color convention (7500 hijack /
 * 7600 radio failure / 7700 general emergency), and its "stale after 15s
 * unseen" dimming rule.
 *
 * Each aircraft also trails its last MAX_TRAIL_POINTS positions as a
 * polyline in its own squawk color, so you can see where it's been, not
 * just where it is right now. Trails are kept in-memory only
 * (`this._trails`, keyed by hex) and reset whenever the modal closes --
 * same "only while open" scope as the map itself, since Leaflet gets torn
 * down and rebuilt fresh on every show().
 *
 * A contact drops off the MAP (not the Aircraft table) once it's gone
 * MAP_STALE_HIDE_SECONDS without an update -- dump1090 itself only purges
 * a contact from /data.json after 300s of total silence, which is far too
 * long to keep plotting a dimmed ghost at its last known position.
 */
class AdsbMapModal {
    constructor() {
        this._overlay = null;
        this._map = null;
        this._layer = null;
        this._pollTimer = null;
        this._fitted = false;
        this._trails = new Map();
        this._onKeyDown = this._onKeyDown.bind(this);
    }

    show() {
        if (this._overlay) return; // already open

        const overlay = document.createElement('div');
        overlay.className = 'pdm-overlay';
        overlay.setAttribute('role', 'dialog');
        overlay.setAttribute('aria-modal', 'true');
        overlay.setAttribute('aria-label', 'ADS-B aircraft map');

        const modal = document.createElement('div');
        modal.className = 'pdm-modal pdm-modal--wide';
        modal.addEventListener('click', (e) => e.stopPropagation());
        modal.innerHTML = `
            <header class="pdm-modal__header">
                <div>
                    <h2 class="pdm-modal__title">Aircraft map</h2>
                    <div class="pdm-modal__meta" data-adsb-map-meta>0 aircraft</div>
                </div>
                <button type="button" class="pdm-modal__close" aria-label="Close">&times;</button>
            </header>
            <div class="pdm-modal__body pdm-modal__body--flush">
                <div class="adsb-map"></div>
            </div>
        `;
        modal.querySelector('.pdm-modal__close').addEventListener('click', () => this.close());
        overlay.addEventListener('click', () => this.close());
        overlay.appendChild(modal);
        document.body.appendChild(overlay);
        this._overlay = overlay;

        document.addEventListener('keydown', this._onKeyDown);
        modal.querySelector('.pdm-modal__close').focus();

        this._initMap(modal.querySelector('.adsb-map'));
        this._poll();
        this._pollTimer = setInterval(() => this._poll(), 2000);
    }

    close() {
        document.removeEventListener('keydown', this._onKeyDown);
        if (this._pollTimer) {
            clearInterval(this._pollTimer);
            this._pollTimer = null;
        }
        if (this._map) {
            this._map.remove();
            this._map = null;
            this._layer = null;
        }
        this._fitted = false;
        this._trails.clear();
        if (this._overlay) {
            this._overlay.remove();
            this._overlay = null;
        }
    }

    _onKeyDown(e) {
        if (e.key === 'Escape') this.close();
    }

    _initMap(el) {
        if (!window.L) return; // leaflet not loaded yet -- nothing to draw into
        this._map = L.map(el, { zoomControl: true, scrollWheelZoom: true });
        L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>',
            maxZoom: 19,
        }).addTo(this._map);
        this._layer = L.layerGroup().addTo(this._map);
        this._map.setView([52.37, 4.89], 8); // same default center as topology_tab.js
        // Leaflet measures its container on init; the modal has only just
        // been attached to the DOM this same tick.
        setTimeout(() => { if (this._map) this._map.invalidateSize(); }, 50);
    }

    async _poll() {
        try {
            const res = await fetch('/api/adsb/status');
            if (!res.ok) return;
            const status = await res.json();
            this._render(status);
        } catch (_e) { /* transient network hiccup -- next poll retries */ }
    }

    _render(status) {
        if (!this._map || !this._layer || !this._overlay) return;
        const metric = !!status.metric;
        const aircraft = status.aircraft || [];
        this._layer.clearLayers();

        // dump1090 itself only purges a contact from /data.json after
        // MODES_INTERACTIVE_DELETE_TTL (300s / 5 min) of total silence --
        // far too long to keep plotting a dimmed "ghost" at its last known
        // position. Stop showing a contact on the MAP once it's gone this
        // long without an update -- matches MODES_INTERACTIVE_DISPLAY_TTL,
        // the same 60s dump1090's own bundled interactive display uses to
        // decide whether a contact is still worth showing. The Aircraft
        // table is unaffected -- it keeps listing everything dump1090 still
        // reports, stale or not.
        const MAP_STALE_HIDE_SECONDS = 60;
        const placed = aircraft.filter((a) => a.lat != null && a.lon != null
            && (a.seen || 0) <= MAP_STALE_HIDE_SECONDS);
        const meta = this._overlay.querySelector('[data-adsb-map-meta]');
        if (meta) {
            meta.textContent = placed.length === aircraft.length
                ? `${aircraft.length} aircraft`
                : `${placed.length} of ${aircraft.length} aircraft positioned`;
        }

        // Drop trails for aircraft that have gone out of range entirely --
        // keyed off the FULL snapshot (not just `placed`) so a contact that
        // just briefly lost its position isn't wiped mid-trail.
        const seenHex = new Set(aircraft.map((a) => a.hex));
        for (const hex of this._trails.keys()) {
            if (!seenHex.has(hex)) this._trails.delete(hex);
        }
        // Also reset the trail for anything currently hidden for staleness,
        // so if it reappears later it starts a fresh trail instead of
        // drawing one long "teleport" line across the gap.
        for (const a of aircraft) {
            if ((a.seen || 0) > MAP_STALE_HIDE_SECONDS) this._trails.delete(a.hex);
        }

        const bounds = [];
        placed.forEach((a) => {
            bounds.push([a.lat, a.lon]);
            const color = this._color(a);
            const trail = this._updateTrail(a);
            if (trail.length > 1) {
                L.polyline(trail, { color, weight: 2, opacity: 0.55 }).addTo(this._layer);
            }
            const marker = L.marker([a.lat, a.lon], { icon: this._icon(a, color) }).addTo(this._layer);
            marker.bindTooltip(this._tooltipHtml(a, metric), { direction: 'top', offset: [0, -8] });
            marker.on('click', () => {
                if (window.AdsbFlightModal) window.AdsbFlightModal.show(a, metric);
            });
        });

        if (bounds.length && !this._fitted) {
            this._map.fitBounds(bounds, { padding: [40, 40], maxZoom: 10 });
            this._fitted = true;
        }
    }

    /** Appends `a`'s current position to its trail (deduped, capped) and returns it. */
    _updateTrail(a) {
        const MAX_TRAIL_POINTS = 60; // ~2 minutes of history at the 2 s poll rate
        let trail = this._trails.get(a.hex);
        if (!trail) {
            trail = [];
            this._trails.set(a.hex, trail);
        }
        const last = trail[trail.length - 1];
        if (!last || last[0] !== a.lat || last[1] !== a.lon) {
            trail.push([a.lat, a.lon]);
            if (trail.length > MAX_TRAIL_POINTS) trail.shift();
        }
        return trail;
    }

    _color(a) {
        const squawk = String(a.squawk || '');
        const stale = (a.seen || 0) > 15;
        if (squawk === '7500') return '#f87171'; // hijack
        if (squawk === '7600') return '#60a5fa'; // radio failure
        if (squawk === '7700') return '#fbbf24'; // general emergency
        if (stale) return 'rgba(139, 154, 171, 0.6)';
        // Normal aircraft: cyan reads well on the dark basemap; on the
        // light theme's light OSM tiles a near-black silhouette is far
        // more legible (emergency-squawk colours stay as-is).
        return this._lightTheme() ? '#1a2233' : '#22d3ee';
    }

    _lightTheme() {
        return document.documentElement.getAttribute('data-theme') === 'light';
    }

    _icon(a, color) {
        const rotation = a.track != null ? a.track : 0;
        // Top-down plane silhouette (nose at 0deg/up), so rotating by
        // `track` alone points it the right way -- no extra offset needed.
        const html = `<svg viewBox="0 0 24 24" width="22" height="22" `
            + `style="transform: rotate(${rotation}deg)" fill="${color}" fill-opacity="0.9" `
            + `stroke="${color}" stroke-width="0.5" stroke-linejoin="round">`
            + `<path d="M21,16V14L13,9V3.5C13,2.67 12.33,2 11.5,2C10.67,2 10,2.67 10,3.5V9L2,14V16L10,13.5V19L7.5,20.5V22L11.5,21L15.5,22V20.5L13,19V13.5L21,16Z"/></svg>`;
        return L.divIcon({
            html,
            className: 'adsb-marker',
            iconSize: [22, 22],
            iconAnchor: [11, 11],
        });
    }

    _tooltipHtml(a, metric) {
        const label = a.flight ? this._esc(a.flight) : this._esc(a.hex || '');
        const alt = a.altitude != null ? `${a.altitude} ${metric ? 'm' : 'ft'}` : ':';
        const speed = a.speed != null ? `${a.speed} ${metric ? 'km/h' : 'kt'}` : ':';
        return `<strong>${label}</strong><br>${this._esc(a.hex || '')} · ${alt} · ${speed}`;
    }

    _esc(str) {
        const el = document.createElement('span');
        el.textContent = str == null ? '' : String(str);
        return el.innerHTML;
    }
}

window.AdsbMapModal = new AdsbMapModal();
