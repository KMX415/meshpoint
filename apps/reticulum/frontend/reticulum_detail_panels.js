/**
 * Reticulum plugin: click-to-detail panels for the Peers and Activity
 * tabs -- the Peers drawer and Activity popup, matching Meshtastic/
 * MeshCore's node drawer + packet-detail modal *exactly*, pixel for
 * pixel: this renders the literal core CSS class names
 * (`nd-drawer`/`nd-section`/`nd-row` from node_drawer.css,
 * `pdm-modal`/`pdm-layer`/`pdm-row` from packet_detail_modal.css)
 * rather than a hand-copied approximation. Those class names are just
 * layout/color rules with no protocol-specific behaviour baked in --
 * reusing them is exactly like this plugin already reusing `mt-badge`/
 * `lw-*`/`terminal-button`/`cfg-*` elsewhere, not a special case.
 *
 * What stays plugin-owned is the *markup construction and data* --
 * this never touches `NodeDrawer`/`PacketDetailModal`'s own JS classes
 * or their singleton DOM elements (`#node-drawer`, `#packet-detail-*`).
 * Reticulum peers/announces don't have Meshtastic/MeshCore's shape
 * (source_id/destination_id/decoded_payload, a `packets` table row) --
 * teaching those classes a Reticulum branch would be the same
 * core-grows-a-protocol-special-case problem this app's whole plugin
 * architecture exists to avoid. Own small classes, own DOM, core's
 * existing CSS applied to both -- same visual system, zero shared
 * runtime coupling.
 */

function _rtEsc(s) {
    return String(s == null ? '' : s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
}

function _rtFullTime(ts) {
    if (!ts) return '--';
    try {
        return new Date(ts).toLocaleString([], { hour12: false });
    } catch (_) { return ts; }
}

// The telemetry INFORMATION sensor is one free-text "·"-joined line, not
// separate fields on the wire (see telemetry.py::_info_line -- Sideband's
// structured PROCESSOR/RAM/NVM sensors don't have a verified pack format,
// so this string is the only place that data travels). Split it back into
// its own labelled row per segment for the modal, instead of one dense
// paragraph -- the leading node-name segment is dropped since the modal's
// own title already shows it. Unrecognised segments (a differently-built
// sender, a future field) still get their own row rather than being lost.
function _rtInfoRows(info, nodeName) {
    const segments = String(info || '').split(' · ').filter(Boolean);
    return segments.map((seg) => {
        if (seg === nodeName) return null;
        const load = /^load (.+)$/.exec(seg);
        if (load) return { key: 'Load', val: load[1] };
        const ram = /^RAM (.+)$/.exec(seg);
        if (ram) return { key: 'RAM', val: ram[1] };
        const disk = /^disk (.+) free$/.exec(seg);
        if (disk) return { key: 'Disk free', val: disk[1] };
        const space = /^space (OPEN|CLOSED)$/.exec(seg);
        if (space) {
            return { key: 'Space', val: space[1], valClass: space[1] === 'OPEN' ? 'pdm-row__val--good' : 'pdm-row__val--bad' };
        }
        return { key: 'Info', val: seg };
    }).filter(Boolean);
}

// Duplicated from reticulum_panel.js's own RT_ASPECT_BADGES (a top-level
// `const` there, not a window property, so not reachable from here) --
// four entries, not worth a cross-file export for.
const _RT_ASPECT_BADGES = {
    'lxmf.delivery': 'mt-badge--text',
    'lxmf.propagation': 'mt-badge--routing',
    'nomadnetwork.node': 'mt-badge--nodeinfo',
    'call.audio': 'mt-badge--routing',
};

function _rtAspectBadge(aspect) {
    const cls = _RT_ASPECT_BADGES[aspect] || '';
    return `<span class="mt-badge ${cls}">${_rtEsc(aspect || '--')}</span>`;
}

// Same tier breaks as node_drawer.js's _signalQuality() -- same physical
// quantity (LoRa RSSI in dBm), same meaning, so the same thresholds.
function _rtSignalQuality(rssi) {
    if (rssi > -80) return 'Excellent';
    if (rssi >= -100) return 'Good';
    if (rssi >= -115) return 'Fair';
    return 'Poor';
}

// RNS interface names are full descriptors, e.g.
// "TCPInterface[ReticulumNet Internet/node.reticulumnet.nl:4242]" --
// much longer than anything Meshtastic/MeshCore's own rows ever show
// (hardware names, dBm numbers), so unlike those it needs its own
// shortening rather than just reusing the plain-text row helper: shows
// the interface class name only, full descriptor as a hover title.
function _rtShortInterfaceName(name) {
    const short = name.split('[')[0].trim() || name;
    return `<span title="${_rtEsc(name)}">${_rtEsc(short)}</span>`;
}

// Identical to node_drawer.js's own _hashColor -- same avatar-color
// scheme for the same visual language.
function _rtHashColor(str) {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
        hash = str.charCodeAt(i) + ((hash << 5) - hash);
    }
    return `hsl(${Math.abs(hash) % 360}, 55%, 45%)`;
}

// Same localStorage key + {hash, name} shape as reticulum_nomad.js's own
// Browse-tab favourites (RT_NOMAD_FAV_KEY) -- duplicated on purpose
// (same small-duplication convention as _RT_ASPECT_BADGES above) so a
// node favourited from either the Peers drawer or the Browse tab shows
// up in both: one shared list, not two. Scoped to nomadnetwork.node
// peers only -- that's the only aspect the Browse picker actually does
// anything useful with; favouriting an lxmf.delivery/propagation peer
// here would just add a dead entry to that picker.
const _RT_FAV_KEY = 'meshpoint.rtNomadFavourites';

function _rtFavourites() {
    try {
        const v = JSON.parse(localStorage.getItem(_RT_FAV_KEY) || '[]');
        return Array.isArray(v) ? v.filter((f) => f && f.hash) : [];
    } catch (_) { return []; }
}

function _rtIsFavourite(hash) {
    return _rtFavourites().some((f) => f.hash === hash);
}

function _rtToggleFavourite(hash, name) {
    const list = _rtFavourites();
    const idx = list.findIndex((f) => f.hash === hash);
    if (idx >= 0) list.splice(idx, 1);
    else list.push({ hash, name: name || `${hash.slice(0, 12)}…` });
    try { localStorage.setItem(_RT_FAV_KEY, JSON.stringify(list)); } catch (_) {}
    return idx < 0;  // true if it's now favourited
}

/** One collapsible `.nd-section` (node_drawer.css), populated with
 * plain `.nd-row` label/value pairs -- same shell + toggle behaviour as
 * NodeDrawer's own `_buildSection`. `rows` entries with a null/empty
 * value are dropped; an empty section shows the same "No data
 * available" placeholder NodeDrawer uses. `value` is inserted as HTML
 * (callers are responsible for escaping plain text themselves via
 * `_rtEsc`) so a caller can pass a badge or other markup through. */
function _rtSection(title, rows, expanded) {
    const kept = rows.filter((r) => r.value != null && r.value !== '');

    const section = document.createElement('div');
    section.className = 'nd-section';

    const header = document.createElement('div');
    header.className = 'nd-section__header';
    header.innerHTML = `<span class="nd-section__title">${_rtEsc(title)}</span>
        <span class="nd-section__arrow">${expanded ? '▼' : '▶'}</span>`;

    const content = document.createElement('div');
    content.className = 'nd-section__content';
    if (!kept.length) {
        content.innerHTML = '<div class="nd-section__empty">No data available</div>';
    } else {
        kept.forEach(({ label, value }) => {
            const row = document.createElement('div');
            row.className = 'nd-row';
            row.innerHTML = `<span class="nd-row__label">${_rtEsc(label)}</span>
                <span class="nd-row__value">${value}</span>`;
            content.appendChild(row);
        });
    }
    content.style.display = expanded ? '' : 'none';

    header.addEventListener('click', () => {
        const visible = content.style.display !== 'none';
        content.style.display = visible ? 'none' : '';
        header.querySelector('.nd-section__arrow').textContent = visible ? '▶' : '▼';
    });

    section.appendChild(header);
    section.appendChild(content);
    return section;
}

/** Right-side slide-in panel for a single Peers-tab row -- same
 * `nd-drawer`/`nd-header`/`nd-section` chrome as the Meshtastic/
 * MeshCore node drawer. */
class ReticulumPeerDrawer {
    constructor() {
        this._backdrop = null;
        this._drawer = null;
        this._onViewAnnounce = null;
        this._openToken = 0;
    }

    /**
     * @param {object} peer -- {destination_hash, display_name, aspect, first_seen, last_seen}
     * @param {object[]} recentAnnounces -- this peer's own entries from the Activity ring buffer, newest first
     * @param {{onBrowse?: function, onViewAnnounce?: function}} opts
     */
    open(peer, recentAnnounces, opts = {}) {
        this.close();
        this._onViewAnnounce = opts.onViewAnnounce || null;
        this._peer = peer;
        this._recentAnnounces = recentAnnounces || [];
        this._opts = opts;
        const token = ++this._openToken;

        const backdrop = document.createElement('div');
        backdrop.className = 'nd-backdrop';
        backdrop.addEventListener('click', () => this.close());

        const drawer = document.createElement('div');
        drawer.className = 'nd-drawer';
        drawer.addEventListener('click', (e) => e.stopPropagation());

        const contact = opts.contact || null;
        const petname = (contact && contact.petname) || '';
        const announced = peer.display_name || '';
        const name = _rtEsc(petname || announced || peer.destination_hash);
        const announcedSub = (petname && announced && announced !== petname)
            ? `<div class="nd-header__sub">announced as ${_rtEsc(announced)}</div>` : '';
        const shortLabel = _rtEsc((peer.destination_hash || '').slice(0, 2)).toUpperCase();
        const color = _rtHashColor(peer.destination_hash || '');
        const canFavourite = peer.aspect === 'nomadnetwork.node';
        const isFav = canFavourite && _rtIsFavourite(peer.destination_hash);

        drawer.innerHTML = `
            <div class="nd-header">
                <div class="nd-header__left">
                    <div class="nd-avatar" style="background:${color}">${shortLabel}</div>
                    <div class="nd-header__info">
                        <div class="nd-header__name">${name}</div>
                        <div class="nd-header__id">${_rtEsc(peer.destination_hash)}</div>
                        ${announcedSub}
                    </div>
                </div>
                ${canFavourite ? `
                    <button class="nd-header__favorite${isFav ? ' nd-header__favorite--on' : ''}"
                            data-favorite-toggle
                            aria-pressed="${isFav ? 'true' : 'false'}"
                            title="${isFav ? 'Remove from favourites' : 'Add to favourites'}">${isFav ? '★' : '☆'}</button>
                ` : ''}
                <button class="nd-close" title="Close">&times;</button>
            </div>
            <div class="nd-body">
                <div class="nd-loading">Loading routing info…</div>
            </div>
        `;
        drawer.querySelector('.nd-close').addEventListener('click', () => this.close());
        const favBtn = drawer.querySelector('[data-favorite-toggle]');
        if (favBtn) {
            favBtn.addEventListener('click', () => {
                const nowOn = _rtToggleFavourite(peer.destination_hash, peer.display_name);
                favBtn.classList.toggle('nd-header__favorite--on', nowOn);
                favBtn.setAttribute('aria-pressed', nowOn ? 'true' : 'false');
                favBtn.title = nowOn ? 'Remove from favourites' : 'Add to favourites';
                favBtn.innerHTML = nowOn ? '★' : '☆';
            });
        }

        document.body.appendChild(backdrop);
        document.body.appendChild(drawer);
        this._backdrop = backdrop;
        this._drawer = drawer;
        requestAnimationFrame(() => {
            backdrop.classList.add('nd-backdrop--visible');
            drawer.classList.add('nd-drawer--open');
        });

        this._renderSections(null);  // identity + recent activity immediately, routing/signal once fetched
        this._fetchLink(peer.destination_hash, token);
    }

    async _fetchLink(destinationHash, token) {
        let info = null;
        try {
            const r = await fetch(
                `/api/reticulum/peers/${encodeURIComponent(destinationHash)}/link`,
                { credentials: 'same-origin' },
            );
            if (r.ok) info = await r.json();
        } catch (_) { /* leave info null -- rendered as unavailable below */ }
        // The drawer may have been closed or reopened on a different peer
        // by the time this resolves -- only render if we're still the
        // open() call that kicked this fetch off.
        if (token !== this._openToken || !this._drawer) return;
        this._renderSections(info);
    }

    _renderSections(link) {
        const body = this._drawer?.querySelector('.nd-body');
        if (!body) return;
        const peer = this._peer;
        const opts = this._opts;

        body.innerHTML = '';

        const canSend = peer.aspect === 'lxmf.delivery' && typeof opts.onSendMessage === 'function';
        const canBrowse = peer.aspect === 'nomadnetwork.node' && typeof opts.onBrowse === 'function';
        if (canSend || canBrowse) {
            const actions = document.createElement('div');
            actions.className = 'nd-actions';
            if (canSend) {
                const sendBtn = document.createElement('button');
                sendBtn.className = 'nd-action-btn nd-action-btn--primary';
                sendBtn.textContent = 'Send Message';
                sendBtn.addEventListener('click', () => {
                    this.close();
                    opts.onSendMessage(peer.destination_hash);
                });
                actions.appendChild(sendBtn);
            }
            if (canBrowse) {
                const browseBtn = document.createElement('button');
                browseBtn.className = 'nd-action-btn nd-action-btn--primary';
                browseBtn.textContent = 'Browse this node';
                browseBtn.addEventListener('click', () => {
                    this.close();
                    opts.onBrowse(peer.destination_hash);
                });
                actions.appendChild(browseBtn);
            }
            body.appendChild(actions);
        }

        body.appendChild(_rtSection('Identity', [
            { label: 'Destination', value: `<span class="nd-row__value">${_rtEsc(peer.destination_hash)}</span>` },
            { label: 'Aspect', value: _rtAspectBadge(peer.aspect) },
            { label: 'First seen', value: _rtEsc(_rtFullTime(peer.first_seen)) },
            { label: 'Last seen', value: _rtEsc(_rtFullTime(peer.last_seen)) },
        ], true));

        if (opts.canEditContact && typeof opts.onSaveContact === 'function') {
            body.appendChild(this._buildContactSection(peer, opts));
        }

        if (link === null) {
            const loading = document.createElement('div');
            loading.className = 'nd-loading';
            loading.textContent = 'Loading routing info…';
            body.appendChild(loading);
        } else if (link) {
            body.appendChild(_rtSection('Routing', [
                { label: 'Hops', value: _rtEsc(link.hops != null ? String(link.hops) : 'unknown') },
                { label: 'Path known', value: _rtEsc(link.has_path ? 'Yes' : 'No') },
                { label: 'Next hop interface', value: link.next_hop_interface ? _rtShortInterfaceName(link.next_hop_interface) : null },
                { label: 'Identity resolved', value: _rtEsc(link.identity_resolved ? 'Yes' : 'No') },
                { label: 'Announces this session', value: link.announces_this_session ? _rtEsc(String(link.announces_this_session)) : null },
            ], true));

            const hasSignal = link.rssi != null || link.snr != null || link.quality != null;
            if (hasSignal) {
                body.appendChild(_rtSection('Signal (most recent announce)', [
                    { label: 'RSSI', value: link.rssi != null ? `${Number(link.rssi).toFixed(0)} dBm` : null },
                    { label: 'SNR', value: link.snr != null ? `${Number(link.snr).toFixed(1)} dB` : null },
                    { label: 'Quality', value: link.rssi != null ? _rtSignalQuality(link.rssi) : (link.quality != null ? `${link.quality}/100` : null) },
                    { label: 'As of', value: link.signal_at ? _rtEsc(_rtFullTime(link.signal_at)) : null },
                ], true));
            }
        }

        const activitySection = _rtSection('Recent Activity', [], true);
        const activityContent = activitySection.querySelector('.nd-section__content');
        if (!this._recentAnnounces.length) {
            activityContent.innerHTML = '<div class="nd-section__empty">No announces from this peer yet this session.</div>';
        } else {
            activityContent.innerHTML = '';
            this._recentAnnounces.slice(0, 20).forEach((a) => {
                const row = document.createElement('button');
                row.type = 'button';
                row.className = 'nd-row rt-activity-row';
                const sig = a.rssi != null ? `<span class="nd-row__value">${Number(a.rssi).toFixed(0)} dBm</span>` : '';
                row.innerHTML = `<span class="nd-row__label">${_rtEsc(_rtFullTime(a.ts))}</span> ${_rtAspectBadge(a.aspect)} ${sig}`;
                row.addEventListener('click', () => {
                    if (this._onViewAnnounce) this._onViewAnnounce(a);
                });
                activityContent.appendChild(row);
            });
        }
        body.appendChild(activitySection);
    }

    /** Editable "Contact" section -- an operator-assigned name (+ note,
     * + a "known" flag) for this destination hash, saved via the panel's
     * onSaveContact / onDeleteContact callbacks (PUT/DELETE
     * /api/reticulum/contacts). Local only; never announced. Same
     * `.nd-section` chrome as the read-only sections, but its content is a
     * small form rather than `.nd-row` pairs. */
    _buildContactSection(peer, opts) {
        const contact = opts.contact || {};
        const section = document.createElement('div');
        section.className = 'nd-section';

        const header = document.createElement('div');
        header.className = 'nd-section__header';
        header.innerHTML = `<span class="nd-section__title">Contact</span>
            <span class="nd-section__arrow">▼</span>`;

        const content = document.createElement('div');
        content.className = 'nd-section__content';
        content.innerHTML = `
            <form class="rt-contact-form">
                <label>Name
                    <input type="text" class="cfg-field__input rt-contact-form__name" maxlength="64"
                           placeholder="e.g. Philster" value="${_rtEsc(contact.petname || '')}">
                </label>
                <label>Note
                    <input type="text" class="cfg-field__input rt-contact-form__note" maxlength="280"
                           placeholder="optional" value="${_rtEsc(contact.note || '')}">
                </label>
                <label class="rt-contact-form__check">
                    <input type="checkbox" class="rt-contact-form__trust"${contact.trusted ? ' checked' : ''}>
                    Mark as known
                </label>
                <div class="rt-contact-form__actions">
                    <button type="submit" class="nd-action-btn nd-action-btn--primary rt-contact-form__save">Save</button>
                    <button type="button" class="nd-action-btn rt-contact-form__remove"${contact.petname ? '' : ' hidden'}>Remove</button>
                    <span class="rt-contact-form__status" aria-live="polite"></span>
                </div>
            </form>
        `;

        const form = content.querySelector('form');
        const nameEl = content.querySelector('.rt-contact-form__name');
        const noteEl = content.querySelector('.rt-contact-form__note');
        const trustEl = content.querySelector('.rt-contact-form__trust');
        const saveBtn = content.querySelector('.rt-contact-form__save');
        const removeBtn = content.querySelector('.rt-contact-form__remove');
        const statusEl = content.querySelector('.rt-contact-form__status');

        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const petname = nameEl.value.trim();
            saveBtn.disabled = true;
            statusEl.textContent = 'Saving…';
            const ok = await opts.onSaveContact(peer.destination_hash, {
                petname, note: noteEl.value.trim(), trusted: trustEl.checked,
            });
            saveBtn.disabled = false;
            statusEl.textContent = ok ? (petname ? 'Saved.' : 'Removed.') : 'Could not save.';
            if (ok) {
                opts.contact = petname
                    ? { petname, note: noteEl.value.trim(), trusted: trustEl.checked }
                    : null;
                removeBtn.hidden = !petname;
                this._refreshHeaderName(peer, opts);
            }
        });

        removeBtn.addEventListener('click', async () => {
            removeBtn.disabled = true;
            statusEl.textContent = 'Removing…';
            const ok = await opts.onDeleteContact(peer.destination_hash);
            removeBtn.disabled = false;
            if (ok) {
                nameEl.value = ''; noteEl.value = ''; trustEl.checked = false;
                removeBtn.hidden = true;
                statusEl.textContent = 'Removed.';
                opts.contact = null;
                this._refreshHeaderName(peer, opts);
            } else {
                statusEl.textContent = 'Could not remove.';
            }
        });

        header.addEventListener('click', () => {
            const visible = content.style.display !== 'none';
            content.style.display = visible ? 'none' : '';
            header.querySelector('.nd-section__arrow').textContent = visible ? '▶' : '▼';
        });

        section.appendChild(header);
        section.appendChild(content);
        return section;
    }

    /** Re-point the drawer header's name/sub-line after a contact edit,
     * without a full re-render (which would drop the open form). */
    _refreshHeaderName(peer, opts) {
        if (!this._drawer) return;
        const petname = (opts.contact && opts.contact.petname) || '';
        const announced = peer.display_name || '';
        const nameEl = this._drawer.querySelector('.nd-header__name');
        if (nameEl) nameEl.textContent = petname || announced || peer.destination_hash;
        let subEl = this._drawer.querySelector('.nd-header__sub');
        const wantSub = petname && announced && announced !== petname;
        if (wantSub && !subEl) {
            subEl = document.createElement('div');
            subEl.className = 'nd-header__sub';
            this._drawer.querySelector('.nd-header__id')?.after(subEl);
        }
        if (subEl) {
            if (wantSub) subEl.textContent = `announced as ${announced}`;
            else subEl.remove();
        }
    }

    close() {
        if (this._drawer) { this._drawer.remove(); this._drawer = null; }
        if (this._backdrop) { this._backdrop.remove(); this._backdrop = null; }
    }
}

/** Center modal with one Activity-tab announce's full detail -- same
 * `pdm-overlay`/`pdm-modal`/`pdm-layer` chrome as the Meshtastic/
 * MeshCore packet-detail modal. */
class ReticulumAnnounceModal {
    constructor() {
        this._overlay = null;
        this._onKeyDown = this._onKeyDown.bind(this);
    }

    /**
     * @param {object} entry -- {ts, destination_hash, display_name, aspect, app_data_hex, rssi, snr, quality}
     * @param {{knownPeer?: boolean, onViewPeer?: function}} opts
     */
    show(entry, opts = {}) {
        this.close();

        const overlay = document.createElement('div');
        overlay.className = 'pdm-overlay';
        overlay.setAttribute('role', 'dialog');
        overlay.setAttribute('aria-modal', 'true');
        overlay.setAttribute('aria-label', 'Announce detail');
        overlay.addEventListener('click', () => this.close());

        const modal = document.createElement('div');
        modal.className = 'pdm-modal';
        modal.addEventListener('click', (e) => e.stopPropagation());

        modal.innerHTML = `
            <header class="pdm-modal__header">
                <div>
                    <h2 class="pdm-modal__title">Announce detail</h2>
                    <div class="pdm-modal__meta">${_rtEsc(_rtFullTime(entry.ts))}</div>
                </div>
                <button type="button" class="pdm-modal__close" aria-label="Close">&times;</button>
            </header>
            <div class="pdm-modal__body"></div>
        `;

        const body = modal.querySelector('.pdm-modal__body');
        for (const layer of [
            this._buildLayer('Routing', [
                { key: 'Destination', val: entry.destination_hash },
                { key: 'Aspect', val: entry.aspect, html: () => _rtAspectBadge(entry.aspect) },
            ]),
            this._buildSignalLayer(entry),
            this._buildPayloadLayer(entry),
        ]) {
            if (layer) body.appendChild(layer);
        }

        if (opts.knownPeer && typeof opts.onViewPeer === 'function') {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'terminal-button rt-amodal__view-peer';
            btn.textContent = 'View peer';
            btn.addEventListener('click', () => {
                this.close();
                opts.onViewPeer(entry.destination_hash);
            });
            body.appendChild(btn);
        }

        modal.querySelector('.pdm-modal__close').addEventListener('click', () => this.close());
        overlay.appendChild(modal);
        document.body.appendChild(overlay);
        this._overlay = overlay;
        document.addEventListener('keydown', this._onKeyDown);
        modal.querySelector('.pdm-modal__close').focus();
    }

    _buildSignalLayer(entry) {
        const hasSignal = entry.rssi != null || entry.snr != null || entry.quality != null;
        if (!hasSignal) return null;
        return this._buildLayer('Signal', [
            { key: 'RSSI', val: entry.rssi != null ? `${Number(entry.rssi).toFixed(0)} dBm` : null },
            { key: 'SNR', val: entry.snr != null ? `${Number(entry.snr).toFixed(1)} dB` : null },
            { key: 'Quality', val: entry.rssi != null ? _rtSignalQuality(entry.rssi) : (entry.quality != null ? `${entry.quality}/100` : null) },
        ]);
    }

    _buildPayloadLayer(entry) {
        const rows = [];
        if (entry.petname) rows.push({ key: 'Contact', val: entry.petname });
        rows.push({ key: 'Display name', val: entry.display_name || '--' });
        if (entry.app_data_hex) {
            rows.push({ key: 'App data (hex)', expandable: true, full: entry.app_data_hex, previewLen: 120 });
        }
        return this._buildLayer('Payload', rows);
    }

    /** Mirrors packet_detail_modal.js's own _buildLayer/_row/
     * _expandableBlock -- same class names, same "drop the layer if
     * every row was empty" behaviour. */
    _buildLayer(label, rows) {
        const rowsEl = document.createElement('div');
        rowsEl.className = 'pdm-layer__rows';
        for (const row of rows) {
            if (row.expandable) {
                rowsEl.appendChild(this._expandableRow(row.key, row.full, row.previewLen));
                continue;
            }
            if (row.val == null || row.val === '') continue;
            rowsEl.appendChild(this._row(row.key, row.html ? row.html() : _rtEsc(row.val), !!row.html));
        }
        if (!rowsEl.children.length) return null;

        const layer = document.createElement('section');
        layer.className = 'pdm-layer';
        layer.innerHTML = `<div class="pdm-layer__label">${_rtEsc(label)}</div>`;
        layer.appendChild(rowsEl);
        return layer;
    }

    _row(key, val, isHtml) {
        const row = document.createElement('div');
        row.className = 'pdm-row';
        row.innerHTML = `
            <span class="pdm-row__key">${_rtEsc(key)}:</span>
            <span class="pdm-row__val">${isHtml ? val : val}</span>
        `;
        return row;
    }

    _expandableRow(key, fullText, previewLen) {
        const wrap = document.createElement('div');
        wrap.className = 'pdm-row';
        const needsToggle = fullText.length > previewLen;
        const preview = needsToggle ? fullText.slice(0, previewLen) + '…' : fullText;

        const keySpan = document.createElement('span');
        keySpan.className = 'pdm-row__key';
        keySpan.textContent = `${key}:`;

        const pre = document.createElement('pre');
        pre.className = 'pdm-payload-text';
        pre.textContent = preview;

        wrap.appendChild(keySpan);
        wrap.appendChild(pre);

        if (needsToggle) {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'pdm-expand';
            btn.textContent = 'Show more';
            let expanded = false;
            btn.addEventListener('click', () => {
                expanded = !expanded;
                pre.textContent = expanded ? fullText : preview;
                btn.textContent = expanded ? 'Show less' : 'Show more';
            });
            wrap.appendChild(btn);
        }
        return wrap;
    }

    close() {
        document.removeEventListener('keydown', this._onKeyDown);
        if (this._overlay) { this._overlay.remove(); this._overlay = null; }
    }

    _onKeyDown(e) {
        if (e.key === 'Escape') this.close();
    }
}

/** Telemetry tab: clicking a row used to just open the Peers drawer --
 * identity/routing, none of the actual reading (temperature, status
 * line, location, when it was heard) the row itself is about. This is
 * the Telemetry equivalent of ReticulumAnnounceModal: same pdm-* shell,
 * its own small set of rows for a telemetry entry instead of an
 * announce. Deliberately its own class rather than a generalised base --
 * matches this file's existing one-class-per-tab shape (see the header
 * comment), and the two modals' row sets don't overlap enough to be
 * worth threading a shared abstraction through. */
class ReticulumTelemetryModal {
    constructor() {
        this._overlay = null;
        this._onKeyDown = this._onKeyDown.bind(this);
    }

    /**
     * @param {object} entry -- one row from GET /api/reticulum/telemetry/peers:
     *   {destination_hash, name, received_at, temperature_c, info, latitude, longitude}
     * @param {{knownPeer?: boolean, onViewPeer?: function}} opts
     */
    show(entry, opts = {}) {
        this.close();

        const overlay = document.createElement('div');
        overlay.className = 'pdm-overlay';
        overlay.setAttribute('role', 'dialog');
        overlay.setAttribute('aria-modal', 'true');
        overlay.setAttribute('aria-label', 'Telemetry detail');
        overlay.addEventListener('click', () => this.close());

        const modal = document.createElement('div');
        modal.className = 'pdm-modal';
        modal.addEventListener('click', (e) => e.stopPropagation());

        const heard = entry.received_at ? new Date(entry.received_at * 1000).toISOString() : null;
        modal.innerHTML = `
            <header class="pdm-modal__header">
                <div>
                    <h2 class="pdm-modal__title">${_rtEsc(entry.name || 'Telemetry')}</h2>
                    <div class="pdm-modal__meta">${_rtEsc(_rtFullTime(heard))}</div>
                </div>
                <button type="button" class="pdm-modal__close" aria-label="Close">&times;</button>
            </header>
            <div class="pdm-modal__body"></div>
        `;

        const body = modal.querySelector('.pdm-modal__body');
        const layer = this._buildReadingLayer(entry);
        if (layer) body.appendChild(layer);

        if (opts.knownPeer && typeof opts.onViewPeer === 'function') {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'terminal-button rt-amodal__view-peer';
            btn.textContent = 'View peer';
            btn.addEventListener('click', () => {
                this.close();
                opts.onViewPeer(entry.destination_hash);
            });
            body.appendChild(btn);
        }

        modal.querySelector('.pdm-modal__close').addEventListener('click', () => this.close());
        overlay.appendChild(modal);
        document.body.appendChild(overlay);
        this._overlay = overlay;
        document.addEventListener('keydown', this._onKeyDown);
        modal.querySelector('.pdm-modal__close').focus();
    }

    _buildReadingLayer(entry) {
        const rows = [
            { key: 'Temperature', val: entry.temperature_c != null ? `${entry.temperature_c}°C` : null },
            ..._rtInfoRows(entry.info, entry.name),
            {
                key: 'Location',
                val: (entry.latitude != null && entry.longitude != null)
                    ? `${entry.latitude.toFixed(4)}, ${entry.longitude.toFixed(4)}` : null,
                html: (entry.latitude != null && entry.longitude != null) ? () =>
                    `<a href="https://www.openstreetmap.org/?mlat=${entry.latitude}&mlon=${entry.longitude}#map=13/${entry.latitude}/${entry.longitude}" target="_blank" rel="noopener">${entry.latitude.toFixed(4)}, ${entry.longitude.toFixed(4)}</a>`
                    : null,
            },
            { key: 'Destination', val: entry.destination_hash },
        ];
        const rowsEl = document.createElement('div');
        rowsEl.className = 'pdm-layer__rows';
        for (const row of rows) {
            if (row.val == null || row.val === '') continue;
            rowsEl.appendChild(this._row(row.key, row.html ? row.html() : _rtEsc(row.val), !!row.html, row.valClass));
        }
        if (!rowsEl.children.length) return null;

        const layer = document.createElement('section');
        layer.className = 'pdm-layer';
        layer.innerHTML = '<div class="pdm-layer__label">Reading</div>';
        layer.appendChild(rowsEl);
        return layer;
    }

    _row(key, val, isHtml, valClass) {
        const row = document.createElement('div');
        row.className = 'pdm-row';
        row.innerHTML = `
            <span class="pdm-row__key">${_rtEsc(key)}:</span>
            <span class="pdm-row__val${valClass ? ` ${valClass}` : ''}">${isHtml ? val : val}</span>
        `;
        return row;
    }

    close() {
        document.removeEventListener('keydown', this._onKeyDown);
        if (this._overlay) { this._overlay.remove(); this._overlay = null; }
    }

    _onKeyDown(e) {
        if (e.key === 'Escape') this.close();
    }
}

window.ReticulumPeerDrawer = ReticulumPeerDrawer;
window.ReticulumAnnounceModal = ReticulumAnnounceModal;
window.ReticulumTelemetryModal = ReticulumTelemetryModal;
