/**
 * Reticulum plugin page: "Browse" tab -- a minimal NomadNet browser.
 *
 * Lists `nomadnetwork.node` peers, fetches a node's pages via
 * POST /api/reticulum/nomad/page, renders the Micron markup with
 * window.MicronParser (reticulum_micron.js), and lets you follow links
 * and submit page forms. Back/forward history, same-node (`:/path`) and
 * cross-node (`<hash>:/path`) links.
 *
 * Admin-only (like Send/Settings) -- POST /api/reticulum/nomad/page
 * requires admin, and browsing establishes real RNS Links.
 *
 * The node picker filters live (the network carries 1000+ nomadnetwork.node
 * announces, capped at 300 server-side) and keeps a per-browser favourites
 * list in localStorage -- favourites show in their own optgroup at the top
 * and stay reachable even after they age off the recent list.
 */

const RT_NOMAD_FAV_KEY = 'meshpoint.rtNomadFavourites';

class ReticulumNomadTab {
    constructor(el) {
        this._el = el;
        this._mounted = false;
        this._nodes = [];
        this._history = [];      // [{hash, path, field_data}]
        this._historyIdx = -1;
        this._parser = null;
        this._loading = false;
        this._filter = '';
        this._currentHash = '';
    }

    show() {
        if (!this._mounted) this._mount();
        this._loadNodes();
    }

    hide() {}

    /** Called by the panel when a Peers-row "Browse" button is clicked. */
    openNode(destinationHash) {
        if (!this._mounted) this._mount();
        this._loadNodes();
        this._go(destinationHash, '/page/index.mu');
    }

    _mount() {
        this._mounted = true;
        this._parser = window.MicronParser ? new window.MicronParser(true) : null;
        this._el.innerHTML = `
            <div class="rt-nomad">
                <div class="rt-nomad__bar">
                    <input type="search" class="cfg-field__input rt-nomad__search" data-nomad-search
                           placeholder="Filter nodes…" autocomplete="off" spellcheck="false"
                           aria-label="Filter NomadNet nodes">
                    <select class="cfg-field__input rt-nomad__nodes" data-nomad-nodes>
                        <option value="">: pick a node :</option>
                    </select>
                    <button class="terminal-button rt-nomad__fav" type="button" data-nomad-fav
                            title="Favourite the current node" disabled>&#9734;</button>
                    <input type="text" class="cfg-field__input rt-nomad__addr" data-nomad-addr
                           placeholder="&lt;hash&gt;:/page/x.mu  :  or  :/page/info.mu on the current node"
                           autocomplete="off" spellcheck="false">
                    <button class="terminal-button" type="button" data-nomad-go>Go</button>
                    <button class="terminal-button" type="button" data-nomad-back title="Back" disabled>&larr;</button>
                    <button class="terminal-button" type="button" data-nomad-fwd title="Forward" disabled>&rarr;</button>
                    <button class="terminal-button" type="button" data-nomad-reload title="Reload" disabled>&#x21bb;</button>
                </div>
                <p class="cfg-status" data-nomad-status aria-live="polite"></p>
                <div class="rt-nomad__page" data-nomad-page>
                    <p class="lw-empty">Pick a NomadNet node above, or type an address
                    (<code>&lt;hash&gt;:/page/x.mu</code>). Once you're on a node, the bar
                    holds its full address : edit the path (e.g. <code>:/page/info.mu</code>)
                    and press Go.</p>
                </div>
            </div>
        `;

        this._nodesEl = this._q('[data-nomad-nodes]');
        this._addrEl = this._q('[data-nomad-addr]');
        this._statusEl = this._q('[data-nomad-status]');
        this._pageEl = this._q('[data-nomad-page]');
        this._searchEl = this._q('[data-nomad-search]');
        this._favBtn = this._q('[data-nomad-fav]');

        this._nodesEl.addEventListener('change', () => {
            if (this._nodesEl.value) this._go(this._nodesEl.value, '/page/index.mu');
        });
        this._searchEl.addEventListener('input', () => {
            this._filter = this._searchEl.value.trim().toLowerCase();
            this._renderNodeOptions();
        });
        this._favBtn.addEventListener('click', () => this._toggleFavourite());
        this._q('[data-nomad-go]').addEventListener('click', () => this._goFromAddr());
        this._addrEl.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') { e.preventDefault(); this._goFromAddr(); }
        });
        this._q('[data-nomad-back]').addEventListener('click', () => this._history_go(-1));
        this._q('[data-nomad-fwd]').addEventListener('click', () => this._history_go(1));
        this._q('[data-nomad-reload]').addEventListener('click', () => {
            const e = this._history[this._historyIdx];
            if (e) this._fetch(e.hash, e.path, e.field_data, false);
        });

        // Delegated: a Micron link inside the rendered page.
        this._pageEl.addEventListener('click', (e) => {
            const a = e.target.closest('a[data-nomad-url]');
            if (!a) return;
            e.preventDefault();
            this._followLink(a);
        });
    }

    _q(sel) { return this._el.querySelector(sel); }

    async _loadNodes() {
        try {
            const r = await fetch('/api/reticulum/nomad/nodes', { credentials: 'same-origin' });
            if (!r.ok) return;
            this._nodes = await r.json();
        } catch (_) { return; }
        this._renderNodeOptions();
    }

    /** Rebuild the <select>: a "★ Favourites" optgroup (merged in even when
     * a favourite has aged off the recent list), then "Recent nodes", both
     * filtered by the search box. */
    _renderNodeOptions() {
        if (!this._nodesEl) return;
        const favs = this._favourites();
        const favHashes = new Set(favs.map((f) => f.hash));
        const q = this._filter;
        const match = (name, hash) => !q
            || (name || '').toLowerCase().includes(q)
            || (hash || '').toLowerCase().includes(q);

        // The native <select> popup sizes itself to the widest option, and
        // CSS can't touch it -- one node with a 140-char name blows the
        // whole dropdown wide. Cap the visible label; the full name still
        // matches the filter box and rides in the option's title.
        const cap = (s) => (s.length > 46 ? s.slice(0, 45).trimEnd() + '…' : s);
        const opt = (hash, name, star) => {
            const full = name || hash;
            return `<option value="${this._esc(hash)}" title="${this._esc(full)}">`
                + `${star ? '★ ' : ''}${this._esc(cap(full))}</option>`;
        };

        const recent = this._nodes
            .filter((n) => match(n.display_name, n.destination_hash))
            .map((n) => opt(n.destination_hash, n.display_name, favHashes.has(n.destination_hash)));

        const favOpts = favs
            .filter((f) => match(f.name, f.hash))
            .map((f) => opt(f.hash, f.name, true));

        const current = this._nodesEl.value || this._currentHash;
        let html = '<option value="">: pick a node :</option>';
        if (favOpts.length) html += `<optgroup label="★ Favourites">${favOpts.join('')}</optgroup>`;
        html += `<optgroup label="Recent nodes">${recent.join('')
            || '<option value="" disabled>no match</option>'}</optgroup>`;
        this._nodesEl.innerHTML = html;
        if (current) this._nodesEl.value = current;
        this._syncFavBtn();
    }

    // --- favourites (per-browser, localStorage) ------------------------

    _favourites() {
        try {
            const v = JSON.parse(localStorage.getItem(RT_NOMAD_FAV_KEY) || '[]');
            return Array.isArray(v) ? v.filter((f) => f && f.hash) : [];
        } catch (_) { return []; }
    }

    _saveFavourites(list) {
        try { localStorage.setItem(RT_NOMAD_FAV_KEY, JSON.stringify(list)); } catch (_) {}
    }

    _isFavourite(hash) {
        return this._favourites().some((f) => f.hash === hash);
    }

    _toggleFavourite() {
        const hash = this._currentHash;
        if (!hash) return;
        const list = this._favourites();
        const idx = list.findIndex((f) => f.hash === hash);
        if (idx >= 0) {
            list.splice(idx, 1);
        } else {
            const known = this._nodes.find((n) => n.destination_hash === hash);
            list.push({ hash, name: (known && known.display_name) || `${hash.slice(0, 12)}…` });
        }
        this._saveFavourites(list);
        this._renderNodeOptions();
    }

    _syncFavBtn() {
        if (!this._favBtn) return;
        const on = !!this._currentHash && this._isFavourite(this._currentHash);
        this._favBtn.disabled = !this._currentHash;
        this._favBtn.innerHTML = on ? '&#9733;' : '&#9734;';  // ★ / ☆
        this._favBtn.classList.toggle('rt-nomad__fav--on', on);
        this._favBtn.title = !this._currentHash ? 'Open a node to favourite it'
            : (on ? 'Remove from favourites' : 'Add to favourites');
    }

    _goFromAddr() {
        const raw = (this._addrEl.value || '').trim();
        if (!raw) return;
        // ":/page/x.mu" and "/page/x.mu" resolve against the node we're on --
        // so you can edit just the path in the pre-filled address bar.
        const { hash, path } = this._splitAddr(raw, this._currentHash);
        if (!hash) {
            this._status('error', 'Type <hash>:/page/x.mu : or :/page/x.mu once you\'re on a node');
            return;
        }
        this._go(hash, path);
    }

    /** "<hex>:/page/x.mu" -> {hash, path}. A bare "/page/x.mu" or ":/page/x.mu"
     * resolves against the current node. */
    _splitAddr(raw, currentHash) {
        raw = raw.replace(/^nomadnetwork:\/\//, '');
        if (raw.startsWith(':')) return { hash: currentHash || '', path: raw.slice(1) || '/page/index.mu' };
        if (raw.startsWith('/')) return { hash: currentHash || '', path: raw };
        const idx = raw.indexOf(':');
        if (idx === -1) return { hash: raw, path: '/page/index.mu' };
        return { hash: raw.slice(0, idx), path: raw.slice(idx + 1) || '/page/index.mu' };
    }

    _go(hash, path, fieldData) {
        this._fetch(hash, path, fieldData, true);
    }

    _history_go(delta) {
        const next = this._historyIdx + delta;
        if (next < 0 || next >= this._history.length) return;
        this._historyIdx = next;
        const e = this._history[next];
        this._fetch(e.hash, e.path, e.field_data, false);
        this._syncNav();
    }

    async _fetch(hash, path, fieldData, pushHistory) {
        if (this._loading) return;
        this._loading = true;
        this._status('pending', `Fetching ${hash.slice(0, 8)}… ${path}`);
        this._addrEl.value = `${hash}:${path}`;
        try {
            const r = await fetch('/api/reticulum/nomad/page', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'same-origin',
                body: JSON.stringify({ destination_hash: hash, path, field_data: fieldData || null }),
            });
            const data = await r.json().catch(() => ({}));
            if (!r.ok || !data.ok) {
                this._status('error', data.error || `Failed (HTTP ${r.status})`);
                return;
            }
            this._render(data.content || '');
            this._status('success', `${hash.slice(0, 8)}… ${path}`);
            this._currentHash = hash;
            if (this._nodesEl) this._nodesEl.value = hash;
            this._syncFavBtn();
            if (pushHistory) {
                this._history = this._history.slice(0, this._historyIdx + 1);
                this._history.push({ hash, path, field_data: fieldData || null });
                this._historyIdx = this._history.length - 1;
            }
            this._syncNav();
        } catch (e) {
            this._status('error', `Network error: ${e.message}`);
        } finally {
            this._loading = false;
        }
    }

    _render(micron) {
        this._pageEl.textContent = '';
        if (!this._parser) {
            this._pageEl.textContent = micron;   // parser missing -- show raw
            return;
        }
        this._pageEl.appendChild(this._parser.parseToHtml(micron));
    }

    _followLink(a) {
        const currentHash = this._history[this._historyIdx]?.hash || '';
        const rawUrl = a.dataset.nomadUrl || '';
        // rawUrl may carry `key=val|key2=val2 request vars after a backtick
        let addrPart = rawUrl;
        const varData = {};
        const btick = rawUrl.indexOf('`');
        if (btick !== -1) {
            addrPart = rawUrl.slice(0, btick);
            for (const pair of rawUrl.slice(btick + 1).split('|')) {
                const eq = pair.indexOf('=');
                if (eq !== -1) varData[`var_${pair.slice(0, eq)}`] = pair.slice(eq + 1);
            }
        }
        // an external http(s) link opens a normal browser tab instead of
        // being parsed as a <hash>:/page/... Reticulum address
        if (/^https?:\/\//i.test(addrPart)) {
            window.open(addrPart, '_blank', 'noopener');
            return;
        }

        const { hash, path } = this._splitAddr(addrPart, currentHash);
        if (!hash) { this._status('error', 'Link has no node : nothing to open'); return; }

        // a /file/... link downloads instead of rendering
        if (path.startsWith('/file/')) {
            this._downloadFile(hash, path);
            return;
        }

        // gather form fields this link asks to submit
        const fieldData = { ...varData };
        const spec = a.dataset.nomadFields;
        if (spec) {
            const wantAll = spec === '*';
            const wanted = wantAll ? null : new Set(spec.split('|'));
            this._pageEl.querySelectorAll('input[name], select[name], textarea[name]').forEach((inp) => {
                if (!wantAll && !wanted.has(inp.name)) return;
                if ((inp.type === 'checkbox' || inp.type === 'radio') && !inp.checked) return;
                fieldData[`field_${inp.name}`] = inp.value;
            });
        }
        this._go(hash, path, Object.keys(fieldData).length ? fieldData : null);
    }

    async _downloadFile(hash, path) {
        this._status('pending', `Downloading ${path.split('/').pop()}…`);
        try {
            const r = await fetch('/api/reticulum/nomad/file', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'same-origin',
                body: JSON.stringify({ destination_hash: hash, path }),
            });
            if (!r.ok) {
                const err = await r.json().catch(() => ({}));
                this._status('error', err.detail || `Download failed (HTTP ${r.status})`);
                return;
            }
            const blob = await r.blob();
            const cd = r.headers.get('Content-Disposition') || '';
            const m = cd.match(/filename="?([^"]+)"?/);
            const name = m ? m[1] : (path.split('/').pop() || 'downloaded_file');
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = name;
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(url);
            this._status('success', `Downloaded ${name}`);
        } catch (e) {
            this._status('error', `Download error: ${e.message}`);
        }
    }

    _syncNav() {
        this._q('[data-nomad-back]').disabled = this._historyIdx <= 0;
        this._q('[data-nomad-fwd]').disabled = this._historyIdx >= this._history.length - 1;
        this._q('[data-nomad-reload]').disabled = this._historyIdx < 0;
    }

    _status(kind, msg) {
        if (!this._statusEl) return;
        this._statusEl.dataset.kind = kind;
        this._statusEl.textContent = msg;
    }

    _esc(s) {
        const el = document.createElement('span');
        el.textContent = s == null ? '' : String(s);
        return el.innerHTML;
    }
}

window.ReticulumNomadTab = ReticulumNomadTab;
