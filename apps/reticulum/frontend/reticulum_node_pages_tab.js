/**
 * Reticulum plugin page: "Pages" tab -- an editor for the local `.mu`
 * files a hosted NomadNet node serves (`plugins.reticulum.node_pages_dir`).
 *
 * Only shown when node hosting is on. Left: the file list (`index.mu`
 * first) + New. Right: a Micron formatting toolbar, a textarea of raw
 * Micron, and a live preview rendered by the same `window.MicronParser`
 * the Browse tab uses. Save PUTs `/api/reticulum/nomad/pages/{name}`; the
 * backend re-registers the node's request handlers so a new page is served
 * without a restart.
 *
 * Toolbar: bold/underline/italic, fg + bg colour (native picker ->
 * nearest 3-hex), H1/H2/H3, left/centre/right align, divider, link,
 * an emoji picker, a box-drawing/symbols palette, the interactive-field
 * trio (text field / checkbox / radio), and a ? cheat-sheet popover.
 * Each inserts the Micron code at the cursor or wraps the selection.
 * Note the field/checkbox/radio widgets render but only *submit* to an
 * executable NomadNet page -- this node serves plain files, so a form on
 * your own page is display-only unless it POSTs to another node.
 *
 * Plain fetch()-driven, same shape as reticulum_settings_tab.js.
 */

class ReticulumNodePagesTab {
    constructor(el) {
        this._el = el;
        this._mounted = false;
        this._pages = [];
        this._current = null;        // { name, isNew }
        this._parser = window.MicronParser ? new window.MicronParser(true) : null;
        this._previewTimer = null;
        this._dirty = false;
    }

    show() {
        if (!this._mounted) this._mount();
        this._loadList();
    }

    hide() {
        clearTimeout(this._previewTimer);
    }

    _mount() {
        this._mounted = true;
        this._el.innerHTML = `
            <div class="rt-pages">
                <aside class="rt-pages__list">
                    <div class="rt-pages__list-head">
                        <span>Pages</span>
                        <button type="button" class="terminal-button rt-pages__new" data-pg-new>+ New</button>
                    </div>
                    <ul data-pg-list></ul>
                    <p class="rt-pages__dir" data-pg-dir></p>
                    <p class="rt-pages__hint" data-pg-hosting></p>
                </aside>
                <section class="rt-pages__editor">
                    <div class="rt-pages__editor-head">
                        <input type="text" class="cfg-field__input rt-pages__name" data-pg-name
                               placeholder="index.mu" autocomplete="off" spellcheck="false" hidden>
                        <span class="rt-pages__name-static" data-pg-name-static></span>
                        <div class="rt-pages__actions">
                            <button type="button" class="terminal-button" data-pg-sample>Load sample</button>
                            <button type="button" class="terminal-button" data-pg-delete hidden>Delete</button>
                            <button type="button" class="terminal-button terminal-button--primary" data-pg-save disabled>Save</button>
                        </div>
                    </div>
                    <p class="cfg-status" data-pg-status aria-live="polite"></p>
                    <div class="rt-pages__toolbar" data-pg-toolbar role="toolbar" aria-label="Micron formatting">
                        <button type="button" data-mu="bold" title="Bold (\`!)"><b>B</b></button>
                        <button type="button" data-mu="underline" title="Underline (\`_)"><u>U</u></button>
                        <button type="button" data-mu="italic" title="Italic (\`*)"><i>I</i></button>
                        <label class="rt-pages__tb-color" title="Text colour (\`F)">
                            <span>A</span>
                            <input type="color" data-mu-color="fg" value="#3388ff" aria-label="Text colour">
                        </label>
                        <label class="rt-pages__tb-color" title="Background colour (\`B)">
                            <span>▚</span>
                            <input type="color" data-mu-color="bg" value="#222222" aria-label="Background colour">
                        </label>
                        <span class="rt-pages__tb-sep"></span>
                        <button type="button" data-mu="h1" title="Heading (&gt;)">H1</button>
                        <button type="button" data-mu="h2" title="Sub-heading (&gt;&gt;)">H2</button>
                        <button type="button" data-mu="h3" title="Sub-sub-heading (&gt;&gt;&gt;)">H3</button>
                        <button type="button" data-mu="left" title="Left align (\`l)">◀</button>
                        <button type="button" data-mu="center" title="Centre (\`c … \`a)">↔</button>
                        <button type="button" data-mu="right" title="Right align (\`r)">▶</button>
                        <button type="button" data-mu="divider" title="Divider (-)">─</button>
                        <span class="rt-pages__tb-sep"></span>
                        <button type="button" data-mu="link" title="Link (\`[label\`url])">🔗</button>
                        <button type="button" data-mu="field" title="Text input field">Field</button>
                        <button type="button" data-mu="checkbox" title="Checkbox">☑</button>
                        <button type="button" data-mu="radio" title="Radio button">◉</button>
                        <span class="rt-pages__tb-emoji">
                            <button type="button" data-mu-emoji-toggle title="Insert emoji">😀</button>
                            <div class="rt-pages__tb-emoji-menu" data-mu-emoji-menu hidden></div>
                        </span>
                        <span class="rt-pages__tb-emoji">
                            <button type="button" data-mu-ascii-toggle title="Box-drawing &amp; symbols">▛</button>
                            <div class="rt-pages__tb-emoji-menu rt-pages__tb-ascii-menu" data-mu-ascii-menu hidden></div>
                        </span>
                        <span class="rt-pages__tb-sep"></span>
                        <button type="button" data-mu="reset" title="Reset formatting (\`\`)">⌫</button>
                        <span class="rt-pages__tb-emoji">
                            <button type="button" data-pg-help-toggle title="Micron cheat-sheet">?</button>
                            <div class="rt-pages__help" data-pg-help hidden>${this._helpHtml()}</div>
                        </span>
                    </div>
                    <div class="rt-pages__split">
                        <textarea class="rt-pages__src" data-pg-src spellcheck="false"
                                  placeholder="Pick a page on the left, or New, to start editing."
                                  disabled></textarea>
                        <div class="rt-nomad__page rt-pages__preview" data-pg-preview></div>
                    </div>
                </section>
            </div>
        `;
        this._list = this._q('[data-pg-list]');
        this._dirEl = this._q('[data-pg-dir]');
        this._hostingEl = this._q('[data-pg-hosting]');
        this._nameEl = this._q('[data-pg-name]');
        this._nameStaticEl = this._q('[data-pg-name-static]');
        this._srcEl = this._q('[data-pg-src]');
        this._previewEl = this._q('[data-pg-preview]');
        this._statusEl = this._q('[data-pg-status]');
        this._saveBtn = this._q('[data-pg-save]');
        this._deleteBtn = this._q('[data-pg-delete]');
        this._sampleBtn = this._q('[data-pg-sample]');
        this._toolbarEl = this._q('[data-pg-toolbar]');
        this._setToolbarEnabled(false);

        this._q('[data-pg-new]').addEventListener('click', () => this._newPage());
        this._saveBtn.addEventListener('click', () => this._save());
        this._deleteBtn.addEventListener('click', () => this._delete());
        this._sampleBtn.addEventListener('click', () => this._loadSample());
        this._srcEl.addEventListener('input', () => {
            this._dirty = true;
            this._saveBtn.disabled = false;
            this._schedulePreview();
        });
        this._nameEl.addEventListener('input', () => {
            this._saveBtn.disabled = !this._nameEl.value.trim();
        });

        this._q('[data-pg-toolbar]').addEventListener('click', (e) => {
            const btn = e.target.closest('[data-mu]');
            if (btn) this._insertMarkup(btn.dataset.mu);
        });
        this._el.querySelectorAll('[data-mu-color]').forEach((inp) => {
            inp.addEventListener('change', (e) => {
                this._insertMarkup(e.target.dataset.muColor === 'bg' ? 'bgcolor' : 'color', e.target.value);
            });
        });
        this._buildCharMenu('[data-mu-emoji-menu]', [
            '📡', '📻', '🛰️', '🌐', '🔗', '⚡', '📶', '🔋', '🖥️', '💾',
            '📍', '🗺️', '🧭', '⭐', '✅', '❌', '⚠️', 'ℹ️', '➡️', '⬅️',
            '🔒', '🔓', '🐧', '🍓', '🤝', '👋', '🎛️', '🔧', '📊', '🕒',
        ]);
        this._buildCharMenu('[data-mu-ascii-menu]', [
            '─', '│', '┌', '┐', '└', '┘', '├', '┤', '┬', '┴', '┼',
            '═', '║', '╔', '╗', '╚', '╝', '╠', '╣', '╦', '╩', '╬',
            '█', '▓', '▒', '░', '▀', '▄', '▌', '▐', '■', '□',
            '→', '←', '↑', '↓', '↔', '»', '«', '•', '·', '°',
        ]);
        this._el.querySelectorAll('[data-mu-emoji-toggle], [data-mu-ascii-toggle]').forEach((btn) => {
            btn.addEventListener('click', () => {
                const menu = btn.parentElement.querySelector('.rt-pages__tb-emoji-menu');
                const wasHidden = menu.hidden;
                this._el.querySelectorAll('.rt-pages__tb-emoji-menu').forEach((m) => { m.hidden = true; });
                menu.hidden = !wasHidden;
            });
        });
        this._q('[data-pg-help-toggle]').addEventListener('click', () => {
            const p = this._q('[data-pg-help]');
            p.hidden = !p.hidden;
        });
        document.addEventListener('click', (e) => {
            if (!e.target.closest('.rt-pages__tb-emoji')) {
                this._el.querySelectorAll('.rt-pages__tb-emoji-menu').forEach((m) => { m.hidden = true; });
                const help = this._q('[data-pg-help]');
                if (help) help.hidden = true;
            }
        });
        this._el.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                this._el.querySelectorAll('.rt-pages__tb-emoji-menu, [data-pg-help]')
                    .forEach((m) => { m.hidden = true; });
            }
        });
    }

    _helpHtml() {
        const rows = [
            ['`! `_ `*', 'bold / underline / italic : toggle, repeat to close'],
            ['`Fxxx … `f', 'text colour (3 hex, e.g. `F38f) … revert'],
            ['`Bxxx … `b', 'background colour … revert'],
            ['``', 'reset every format at once'],
            ['`c `l `r `a', 'centre / left / right align … `a reverts'],
            ['&gt; &gt;&gt; &gt;&gt;&gt;', 'H1 / H2 / H3 (rest of the line)'],
            ['-', 'divider : on its own line'],
            ['`[label`url]', 'link : `url can be https://… or :/page/x.mu (this node)'],
            ['`&lt;name`&gt;', 'text field · `&lt;?|n|1`Lbl&gt; checkbox · `&lt;^|g|v`Lbl&gt; radio'],
        ];
        const note = 'Keep lines under ~130 chars for phone / MeshChat clients. '
            + '<b>Centre aligns each line on its own</b> : multi-line ASCII art must '
            + 'be left-aligned or it fragments.';
        return '<h4>Micron quick reference</h4><dl>'
            + rows.map(([c, d]) => `<dt><code>${c}</code></dt><dd>${d}</dd>`).join('')
            + `</dl><p class="rt-pages__help-note">${note}</p>`;
    }

    _buildCharMenu(sel, chars) {
        const menu = this._q(sel);
        if (!menu) return;
        chars.forEach((ch) => {
            const b = document.createElement('button');
            b.type = 'button';
            b.textContent = ch;
            b.addEventListener('click', () => {
                menu.hidden = true;
                this._insertText(ch);
            });
            menu.appendChild(b);
        });
    }

    _q(sel) { return this._el.querySelector(sel); }

    async _loadList() {
        try {
            const r = await fetch('/api/reticulum/nomad/pages', { credentials: 'same-origin' });
            if (!r.ok) { this._setStatus('error', `Could not load pages (HTTP ${r.status}).`); return; }
            const body = await r.json();
            this._pages = body.pages || [];
            this._dirEl.textContent = body.pages_dir ? `Folder: ${body.pages_dir}` : '';
            this._hostingEl.textContent = body.node_hosting
                ? 'Node is hosting : saved pages are served immediately.'
                : 'Node is not hosting right now : edits save but aren’t served until it starts.';
            this._renderList();
        } catch (_e) {
            this._setStatus('error', 'Network error loading pages.');
        }
    }

    _renderList() {
        this._list.innerHTML = '';
        this._pages.forEach((p) => {
            const li = document.createElement('li');
            li.className = 'rt-pages__item';
            li.setAttribute('role', 'button');
            li.tabIndex = 0;
            li.addEventListener('keydown', (event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    this._open(p.name);
                }
            });
            if (this._current && !this._current.isNew && this._current.name === p.name) {
                li.classList.add('rt-pages__item--active');
            }
            li.textContent = p.name;
            if (!p.exists) {
                const tag = document.createElement('span');
                tag.className = 'rt-pages__tag';
                tag.textContent = 'not created';
                li.appendChild(tag);
            }
            li.addEventListener('click', () => this._open(p.name));
            this._list.appendChild(li);
        });
    }

    async _open(name) {
        if (!(await this._confirmDiscard())) return;
        try {
            const r = await fetch(`/api/reticulum/nomad/pages/${encodeURIComponent(name)}`,
                { credentials: 'same-origin' });
            if (!r.ok) { this._setStatus('error', `Could not open ${name} (HTTP ${r.status}).`); return; }
            const body = await r.json();
            this._current = { name, isNew: false };
            this._nameEl.hidden = true;
            this._nameStaticEl.textContent = name;
            this._srcEl.disabled = false;
            this._setToolbarEnabled(true);
            this._srcEl.value = body.content || '';
            this._deleteBtn.hidden = false;
            this._saveBtn.disabled = true;
            this._dirty = false;
            this._setStatus('', '');
            this._renderList();
            this._renderPreview();
        } catch (_e) {
            this._setStatus('error', 'Network error opening page.');
        }
    }

    async _newPage() {
        if (!(await this._confirmDiscard())) return;
        this._current = { name: null, isNew: true };
        this._nameEl.hidden = false;
        this._nameEl.value = '';
        this._nameStaticEl.textContent = '';
        this._srcEl.disabled = false;
        this._setToolbarEnabled(true);
        this._srcEl.value = '';
        this._deleteBtn.hidden = true;
        this._saveBtn.disabled = true;
        this._dirty = false;
        this._setStatus('', 'New page : name it (e.g. about.mu) and Save.');
        this._renderList();
        this._renderPreview();
        this._nameEl.focus();
    }

    async _loadSample() {
        if (this._srcEl.disabled) {
            this._setStatus('error', 'Open a page or start a new one first.');
            return;
        }
        if (this._srcEl.value.trim() && !(await this._confirm({
            label: 'Load sample?',
            description: 'Replace the current editor contents with the sample page?',
        }))) {
            return;
        }
        try {
            const r = await fetch('/api/reticulum/nomad/sample-page', { credentials: 'same-origin' });
            const body = await r.json();
            this._srcEl.value = body.content || '';
            this._dirty = true;
            this._saveBtn.disabled = this._current?.isNew && !this._nameEl.value.trim();
            this._renderPreview();
        } catch (_e) {
            this._setStatus('error', 'Could not load the sample.');
        }
    }

    async _save() {
        const name = this._current?.isNew ? this._nameEl.value.trim() : this._current?.name;
        if (!name) return;
        this._saveBtn.disabled = true;
        this._setStatus('pending', 'Saving…');
        try {
            const r = await fetch(`/api/reticulum/nomad/pages/${encodeURIComponent(name)}`, {
                method: 'PUT',
                credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ content: this._srcEl.value }),
            });
            const body = await r.json().catch(() => ({}));
            if (!r.ok) {
                this._setStatus('error', body.detail || `Save failed (HTTP ${r.status}).`);
                this._saveBtn.disabled = false;
                return;
            }
            this._current = { name, isNew: false };
            this._nameEl.hidden = true;
            this._nameStaticEl.textContent = name;
            this._deleteBtn.hidden = false;
            this._dirty = false;
            this._setStatus('success', body.served
                ? `Saved : ${name} is live on the node.`
                : `Saved. Enable node hosting to serve it.`);
            await this._loadList();
        } catch (_e) {
            this._setStatus('error', 'Network error saving page.');
            this._saveBtn.disabled = false;
        }
    }

    async _delete() {
        const name = this._current?.name;
        if (!name || this._current.isNew) return;
        const ok = await this._confirm({
            label: 'Delete page?',
            description: `Remove "${name}" from the node's pages folder on the device. `
                + `If the node is hosting, it stops serving that page.`,
        });
        if (!ok) return;
        try {
            const r = await fetch(`/api/reticulum/nomad/pages/${encodeURIComponent(name)}`, {
                method: 'DELETE', credentials: 'same-origin',
            });
            if (!r.ok) {
                const body = await r.json().catch(() => ({}));
                this._setStatus('error', body.detail || `Delete failed (HTTP ${r.status}).`);
                return;
            }
            this._current = null;
            this._srcEl.value = '';
            this._srcEl.disabled = true;
            this._setToolbarEnabled(false);
            this._deleteBtn.hidden = true;
            this._nameStaticEl.textContent = '';
            this._saveBtn.disabled = true;
            this._previewEl.innerHTML = '';
            this._setStatus('success', `${name} deleted.`);
            await this._loadList();
        } catch (_e) {
            this._setStatus('error', 'Network error deleting page.');
        }
    }

    // --- formatting toolbar (Micron codes at the cursor / around selection) ---

    _setToolbarEnabled(on) {
        if (!this._toolbarEl) return;
        this._toolbarEl.classList.toggle('rt-pages__toolbar--off', !on);
        // the cheat-sheet (?) stays usable even with no page open
        this._toolbarEl.querySelectorAll('button:not([data-pg-help-toggle]), input').forEach((el) => {
            el.disabled = !on;
        });
    }

    _insertMarkup(kind, colorHex) {
        const ta = this._srcEl;
        if (ta.disabled) return;
        const start = ta.selectionStart;
        const end = ta.selectionEnd;
        const val = ta.value;
        const sel = val.slice(start, end);
        let out = null;      // replacement text for [start,end)
        let caret = null;    // where to put the cursor after

        const wrap = (open, close) => {
            out = open + sel + close;
            caret = sel ? start + out.length : start + open.length;
        };
        const linePrefix = (prefix) => {
            const ls = val.lastIndexOf('\n', start - 1) + 1;
            ta.value = val.slice(0, ls) + prefix + ' ' + val.slice(ls);
            caret = start + prefix.length + 1;
        };

        const slug = (s) => (s || 'name').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'name';

        switch (kind) {
        case 'bold': wrap('`!', '`!'); break;
        case 'underline': wrap('`_', '`_'); break;
        case 'italic': wrap('`*', '`*'); break;
        case 'reset': wrap('``', '``'); break;
        case 'left': wrap('`l', '`a'); break;
        case 'center': wrap('`c', '`a'); break;
        case 'right': wrap('`r', '`a'); break;
        case 'color': wrap('`F' + this._to3hex(colorHex), '`f'); break;
        case 'bgcolor': wrap('`B' + this._to3hex(colorHex), '`b'); break;
        case 'h1': linePrefix('>'); break;
        case 'h2': linePrefix('>>'); break;
        case 'h3': linePrefix('>>>'); break;
        case 'divider': {
            const onOwnLine = start === 0 || val[start - 1] === '\n';
            out = (onOwnLine ? '' : '\n') + '-\n';
            caret = start + out.length;
            break;
        }
        case 'link': {
            const label = window.prompt('Link text:', sel || '');
            if (label == null) return;
            const url = window.prompt(
                'Link target (https://…  or  :/page/name.mu for this node):', 'https://',
            );
            if (url == null) return;
            out = '`[' + label + '`' + url + ']';
            caret = start + out.length;
            break;
        }
        case 'field': {
            const name = window.prompt('Field name (submitted as var_<name>):', 'message');
            if (name == null) return;
            out = '`<' + slug(name) + '`>';
            caret = start + out.length;
            break;
        }
        case 'checkbox': {
            const label = window.prompt('Checkbox label:', sel || 'I agree');
            if (label == null) return;
            out = '`<?|' + slug(label) + '|1`' + label + '>';
            caret = start + out.length;
            break;
        }
        case 'radio': {
            const label = window.prompt("Radio option label (group 'choice'):", sel || 'Option A');
            if (label == null) return;
            out = '`<^|choice|' + slug(label) + '`' + label + '>';
            caret = start + out.length;
            break;
        }
        default: return;
        }

        if (out !== null) {
            ta.value = val.slice(0, start) + out + val.slice(end);
        }
        ta.focus();
        if (caret != null) ta.setSelectionRange(caret, caret);
        this._dirty = true;
        this._saveBtn.disabled = !!(this._current?.isNew && !this._nameEl.value.trim());
        this._renderPreview();
    }

    /** Drop plain text at the cursor (emoji picker). */
    _insertText(str) {
        const ta = this._srcEl;
        if (ta.disabled) return;
        const { selectionStart: s, selectionEnd: e, value: v } = ta;
        ta.value = v.slice(0, s) + str + v.slice(e);
        ta.focus();
        ta.setSelectionRange(s + str.length, s + str.length);
        this._dirty = true;
        this._saveBtn.disabled = !!(this._current?.isNew && !this._nameEl.value.trim());
        this._renderPreview();
    }

    /** #rrggbb -> Micron's 3-hex-digit form (each channel 0..f). */
    _to3hex(hex) {
        const m = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex || '');
        if (!m) return '888';
        return m.slice(1)
            .map((c) => Math.round((parseInt(c, 16) / 255) * 15).toString(16))
            .join('');
    }

    _schedulePreview() {
        clearTimeout(this._previewTimer);
        this._previewTimer = setTimeout(() => this._renderPreview(), 200);
    }

    _renderPreview() {
        if (!this._previewEl) return;
        this._previewEl.innerHTML = '';
        const text = this._srcEl.value;
        if (!text.trim()) return;
        if (this._parser) {
            try {
                this._previewEl.appendChild(this._parser.parseToHtml(text));
            } catch (_e) {
                this._previewEl.textContent = text;
            }
        } else {
            this._previewEl.textContent = text;
        }
    }

    async _confirmDiscard() {
        if (!this._dirty) return true;
        return this._confirm({
            label: 'Discard changes?',
            description: 'This page has unsaved edits : discard them?',
        });
    }

    /** Styled dashboard confirm modal, falling back to window.confirm. */
    _confirm(opts) {
        if (typeof window.confirmModal === 'function') return window.confirmModal(opts);
        return Promise.resolve(window.confirm(
            [opts.label, opts.description].filter(Boolean).join('\n\n'),
        ));
    }

    _setStatus(kind, msg) {
        if (!this._statusEl) return;
        this._statusEl.dataset.kind = kind;
        this._statusEl.textContent = msg;
    }
}

window.ReticulumNodePagesTab = ReticulumNodePagesTab;
