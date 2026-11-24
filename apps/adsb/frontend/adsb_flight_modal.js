/**
 * Modal showing everything known about one aircraft row clicked in the
 * ADS-B table -- the raw ADS-B fields already in hand (no extra call for
 * those), plus three enrichment lookups dump1090 itself never does. A
 * check of the bundled dump1090 web UI (dump1090/public_html/planeObject.js,
 * script.js) turned up no registration/type/route/photo lookup at all --
 * it only builds plain outbound links to fr24/flightstats/flightaware for
 * the human to click. This modal fetches the same category of data
 * client-side instead, from two free no-auth-required public APIs also
 * used by other open dump1090-derived web UIs (tar1090 etc):
 *   - hexdb.io  -- registration/type/manufacturer/operator by hex, and
 *     route (origin-destination ICAO) by callsign, plus airport name
 *     lookups to turn those ICAO codes into readable names.
 *   - planespotters.net -- a real photo of the airframe by hex, when one
 *     of their contributors has one.
 * All three are independent and best-effort: a 404 (aircraft/route/photo
 * not in that service's database, which is common for GA/military/older
 * aircraft) just renders as "not found", not an error.
 */
class AdsbFlightModal {
    constructor() {
        this._overlay = null;
        this._onKeyDown = this._onKeyDown.bind(this);
    }

    show(aircraft, metric) {
        this.close();

        const overlay = document.createElement('div');
        overlay.className = 'pdm-overlay';
        overlay.setAttribute('role', 'dialog');
        overlay.setAttribute('aria-modal', 'true');
        overlay.setAttribute('aria-label', 'Flight detail');

        const modal = document.createElement('div');
        modal.className = 'pdm-modal';
        modal.addEventListener('click', (e) => e.stopPropagation());

        const label = aircraft.flight || aircraft.hex || 'Aircraft';
        modal.innerHTML = `
            <header class="pdm-modal__header">
                <div>
                    <h2 class="pdm-modal__title">${this._esc(label)}</h2>
                    <div class="pdm-modal__meta">${this._esc(aircraft.hex || '')}</div>
                </div>
                <button type="button" class="pdm-modal__close" aria-label="Close">&times;</button>
            </header>
            <div class="pdm-modal__body"></div>
        `;

        const body = modal.querySelector('.pdm-modal__body');
        body.appendChild(this._buildLayer('Flight', this._flightRows(aircraft, !!metric)));
        const aircraftLayer = this._buildLayer('Aircraft', [{ key: 'Registration', val: 'looking up…' }]);
        const routeLayer = this._buildLayer('Route', [{ key: 'Route', val: 'looking up…' }]);
        const photoLayer = this._buildLayer('Photo', [{ key: 'Photo', val: 'looking up…' }]);
        body.appendChild(aircraftLayer);
        body.appendChild(routeLayer);
        body.appendChild(photoLayer);

        modal.querySelector('.pdm-modal__close').addEventListener('click', () => this.close());
        overlay.addEventListener('click', () => this.close());
        overlay.appendChild(modal);
        document.body.appendChild(overlay);
        this._overlay = overlay;

        document.addEventListener('keydown', this._onKeyDown);
        modal.querySelector('.pdm-modal__close').focus();

        this._loadAircraft(aircraft.hex, aircraftLayer);
        this._loadRoute(aircraft.flight, routeLayer);
        this._loadPhoto(aircraft.hex, photoLayer);
    }

    close() {
        document.removeEventListener('keydown', this._onKeyDown);
        if (this._overlay) {
            this._overlay.remove();
            this._overlay = null;
        }
    }

    _onKeyDown(e) {
        // stopImmediatePropagation -- this modal can open on top of another
        // (e.g. AdsbMapModal, when opened from a marker click), and both
        // bind their own Escape handler to `document`; without this, one
        // Escape press would close both instead of just the top one.
        if (e.key === 'Escape') {
            e.stopImmediatePropagation();
            this.close();
        }
    }

    _flightRows(a, metric) {
        const pos = (a.lat != null && a.lon != null) ? `${a.lat.toFixed(3)}, ${a.lon.toFixed(3)}` : 'n/a';
        const alt = a.altitude != null ? `${a.altitude} ${metric ? 'm' : 'ft'}` : 'n/a';
        const speed = a.speed != null ? `${a.speed} ${metric ? 'km/h' : 'kt'}` : 'n/a';
        const track = a.track != null ? `${a.track}°` : 'n/a';
        return [
            { key: 'ICAO hex', val: a.hex || 'n/a' },
            { key: 'Squawk', val: a.squawk || 'n/a' },
            { key: 'Altitude', val: alt },
            { key: 'Speed', val: speed },
            { key: 'Track', val: track },
            { key: 'Position', val: pos },
            { key: 'Messages', val: a.messages != null ? String(a.messages) : 'n/a' },
            { key: 'Seen', val: a.seen != null ? `${a.seen}s ago` : 'n/a' },
        ];
    }

    async _loadAircraft(hex, layer) {
        if (!hex) return this._replaceLayer(layer, [{ key: 'Registration', val: 'no hex' }]);
        try {
            const res = await fetch(`https://hexdb.io/api/v1/aircraft/${encodeURIComponent(hex.toUpperCase())}`);
            if (!res.ok) return this._replaceLayer(layer, [{ key: 'Registration', val: 'not found in hexdb.io' }]);
            const data = await res.json();
            this._replaceLayer(layer, [
                { key: 'Registration', val: data.Registration || 'n/a' },
                { key: 'Type', val: data.Type || data.ICAOTypeCode || 'n/a' },
                { key: 'Manufacturer', val: data.Manufacturer || 'n/a' },
                { key: 'Operator', val: data.RegisteredOwners || 'n/a' },
            ]);
        } catch (_e) {
            this._replaceLayer(layer, [{ key: 'Registration', val: 'lookup failed' }]);
        }
    }

    async _loadRoute(flight, layer) {
        const callsign = (flight || '').trim();
        if (!callsign) return this._replaceLayer(layer, [{ key: 'Route', val: 'no callsign' }]);
        try {
            const res = await fetch(`https://hexdb.io/api/v1/route/icao/${encodeURIComponent(callsign)}`);
            if (!res.ok) return this._replaceLayer(layer, [{ key: 'Route', val: 'not found in hexdb.io' }]);
            const data = await res.json();
            const [origin, destination] = (data.route || '').split('-');
            const [originName, destName] = await Promise.all([
                this._airportName(origin),
                this._airportName(destination),
            ]);
            this._replaceLayer(layer, [
                { key: 'Origin', val: originName ? `${origin} : ${originName}` : (origin || 'n/a') },
                { key: 'Destination', val: destName ? `${destination} : ${destName}` : (destination || 'n/a') },
            ]);
        } catch (_e) {
            this._replaceLayer(layer, [{ key: 'Route', val: 'lookup failed' }]);
        }
    }

    async _airportName(icao) {
        if (!icao) return null;
        try {
            const res = await fetch(`https://hexdb.io/api/v1/airport/icao/${encodeURIComponent(icao)}`);
            if (!res.ok) return null;
            const data = await res.json();
            return data.airport || null;
        } catch (_e) {
            return null;
        }
    }

    async _loadPhoto(hex, layer) {
        if (!hex) return this._replaceLayer(layer, [{ key: 'Photo', val: 'no hex' }]);
        try {
            const res = await fetch(`https://api.planespotters.net/pub/photos/hex/${encodeURIComponent(hex.toUpperCase())}`);
            if (!res.ok) return this._replaceLayer(layer, [{ key: 'Photo', val: 'lookup failed' }]);
            const data = await res.json();
            const photo = (data.photos || [])[0];
            if (!photo) return this._replaceLayer(layer, [{ key: 'Photo', val: 'no photo found' }]);
            this._replaceLayer(layer, [{ el: this._photoRow(photo) }]);
        } catch (_e) {
            this._replaceLayer(layer, [{ key: 'Photo', val: 'lookup failed' }]);
        }
    }

    /**
     * A hotlinked photo's thumbnail can fail to load in the browser even
     * when the lookup itself succeeded (CDN hiccup, ad-blocker, extension)
     * -- shown live: registration/route/credit all resolved but the <img>
     * still came up broken. Built with real DOM nodes (not an HTML string)
     * so an `error` listener can swap in a text fallback instead of
     * leaving the ugly broken-image glyph on screen.
     */
    _photoRow(photo) {
        const wrap = document.createElement('div');
        wrap.className = 'pdm-row';

        const link = document.createElement('a');
        link.href = photo.link;
        link.target = '_blank';
        link.rel = 'noopener noreferrer';

        const img = document.createElement('img');
        img.className = 'adsb-photo';
        img.src = photo.thumbnail_large.src;
        img.alt = 'Aircraft photo';
        img.width = photo.thumbnail_large.size.width;
        img.height = photo.thumbnail_large.size.height;
        img.addEventListener('error', () => {
            wrap.innerHTML = `<span class="pdm-row__val">Photo failed to load in this browser -- <a href="${this._esc(photo.link)}" target="_blank" rel="noopener noreferrer">view on planespotters.net</a></span>`;
        }, { once: true });

        link.appendChild(img);
        wrap.appendChild(link);

        const credit = document.createElement('div');
        credit.className = 'pdm-row';
        credit.innerHTML = `
            <span class="pdm-row__key">Credit:</span>
            <span class="pdm-row__val">${this._esc(photo.photographer || 'unknown')} · <a href="${this._esc(photo.link)}" target="_blank" rel="noopener noreferrer">planespotters.net</a></span>
        `;

        const group = document.createElement('div');
        group.appendChild(wrap);
        group.appendChild(credit);
        return group;
    }

    _replaceLayer(layer, rows) {
        if (!this._overlay || !this._overlay.contains(layer)) return; // modal closed/replaced meanwhile
        const rowsEl = layer.querySelector('.pdm-layer__rows');
        rowsEl.innerHTML = '';
        for (const row of rows) {
            if (row.el) {
                rowsEl.appendChild(row.el);
            } else if (row.html) {
                rowsEl.insertAdjacentHTML('beforeend', row.html);
            } else {
                rowsEl.appendChild(this._row(row.key, row.val));
            }
        }
    }

    _buildLayer(label, rows) {
        const layer = document.createElement('section');
        layer.className = 'pdm-layer';
        layer.innerHTML = `<div class="pdm-layer__label">${this._esc(label)}</div>`;
        const rowsEl = document.createElement('div');
        rowsEl.className = 'pdm-layer__rows';
        for (const row of rows) {
            rowsEl.appendChild(this._row(row.key, row.val));
        }
        layer.appendChild(rowsEl);
        return layer;
    }

    _row(key, val) {
        const row = document.createElement('div');
        row.className = 'pdm-row';
        row.innerHTML = `
            <span class="pdm-row__key">${this._esc(key)}:</span>
            <span class="pdm-row__val">${this._esc(val)}</span>
        `;
        return row;
    }

    _esc(str) {
        const el = document.createElement('span');
        el.textContent = str == null ? '' : String(str);
        return el.innerHTML;
    }
}

window.AdsbFlightModal = new AdsbFlightModal();
