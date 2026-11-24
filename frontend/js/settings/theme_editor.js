/**
 * Settings → Themes.
 *
 *  - Default-theme picker (moved here from Settings → System): PUTs
 *    dashboard.theme so a fresh browser lands on it.
 *  - Theme builder: pick a base theme, tweak its palette with colour
 *    inputs, preview live on the whole dashboard, download a
 *    `theme.css` (+ `theme.json`) to drop into `frontend/themes/<id>/`.
 *    Download-only : nothing is written server-side.
 *
 * Preview: the base theme stays applied via `data-theme`; only the
 * tokens the user changed are pushed as inline custom properties on
 * <html>, and `meshpoint:themechange` fires so charts / the terminal
 * follow. Leaving the page clears the inline overrides.
 */
(function () {
    const COLOR = 'color';
    const ALPHA = 'alpha';

    const GROUPS = [
        {
            legend: 'Base',
            tokens: [
                ['--bg-primary', COLOR], ['--bg-secondary', COLOR], ['--bg-card', COLOR],
                ['--border', COLOR],
                ['--text-primary', COLOR], ['--text-secondary', COLOR], ['--text-muted', COLOR],
            ],
        },
        {
            legend: 'Accents',
            tokens: [
                ['--accent-green', COLOR], ['--accent-cyan', COLOR], ['--accent-blue', COLOR],
                ['--accent-purple', COLOR], ['--accent-amber', COLOR], ['--accent-red', COLOR],
            ],
        },
        {
            legend: 'Sidebar',
            tokens: [
                ['--sidebar-bg', COLOR], ['--sidebar-border', COLOR], ['--sidebar-accent', COLOR],
                ['--sidebar-text', COLOR], ['--sidebar-text-muted', COLOR],
            ],
        },
        {
            legend: 'Surfaces & overlays',
            tokens: [
                ['--bg-glass', ALPHA], ['--bg-inset', COLOR], ['--bg-popover', COLOR],
                ['--hairline', ALPHA], ['--overlay-weak', ALPHA], ['--overlay-med', ALPHA],
                ['--overlay-strong', ALPHA], ['--sunken', ALPHA], ['--scrim', ALPHA],
                ['--border-glow', ALPHA],
                ['--sidebar-item-hover', ALPHA], ['--sidebar-item-active-bg', ALPHA],
            ],
        },
    ];

    // Only expose tokens present in this dashboard's design system.
    GROUPS.forEach((group) => {
        group.tokens = group.tokens.filter(([token]) =>
            getComputedStyle(document.documentElement).getPropertyValue(token).trim());
    });
    const ALL_TOKENS = GROUPS.flatMap((g) => g.tokens.map((t) => t[0]));

    // Not editable in the builder (you can't see the Messages panel /
    // Terminal from here), but carried into the downloaded theme.css so
    // the file is complete : pick the base, download, hand-tune these.
    const CARRIED_TOKENS = [
        '--msg-bg', '--msg-bg-deep', '--msg-bg-strip', '--msg-border', '--msg-border-strong',
        '--msg-accent', '--msg-accent-soft', '--msg-text', '--msg-text-dim', '--msg-text-faint',
        '--msg-mt', '--msg-mc', '--msg-danger',
        '--term-bg', '--term-bg-deep', '--term-bg-strip', '--term-border', '--term-border-strong',
        '--term-accent', '--term-accent-soft', '--term-text', '--term-text-dim', '--term-text-faint',
        '--term-danger', '--term-success',
    ];

    const root = document.documentElement;

    // ---- colour parsing -------------------------------------------------
    const {resolveVar, toRgba, toHex, toRgbaStr} = window.ThemeColors;

    function readTheme(themeId, names) {
        names = names || ALL_TOKENS;
        const prev = root.getAttribute('data-theme');
        // Drop any live-preview inline props so we read the theme's own values.
        const stash = {};
        ALL_TOKENS.forEach((n) => {
            const v = root.style.getPropertyValue(n);
            if (v) { stash[n] = v; root.style.removeProperty(n); }
        });
        if (themeId === 'dark') root.removeAttribute('data-theme');
        else root.setAttribute('data-theme', themeId);
        const out = {};
        names.forEach((name) => {
            out[name] = resolveVar(getComputedStyle(root).getPropertyValue(name), 0);
        });
        if (prev) root.setAttribute('data-theme', prev);
        else root.removeAttribute('data-theme');
        Object.entries(stash).forEach(([n, v]) => root.style.setProperty(n, v));
        return out;
    }

    class ThemeEditor {
        constructor(el) {
            this.el = el;
            this.defaultSel = el.querySelector('[data-default-theme]');
            this.defaultStatus = el.querySelector('[data-default-theme-status]');
            this.baseSel = el.querySelector('[data-te-base]');
            this.nameInput = el.querySelector('[data-te-name]');
            this.authorInput = el.querySelector('[data-te-author]');
            this.homepageInput = el.querySelector('[data-te-homepage]');
            this.descInput = el.querySelector('[data-te-desc]');
            this.baseMeta = el.querySelector('[data-te-base-meta]');
            this.groupsEl = el.querySelector('[data-te-groups]');
            this.carryRef = el.querySelector('[data-te-carry-ref]');
            this.status = el.querySelector('[data-te-status]');
            this.installedEl = el.querySelector('[data-te-installed]');
            this._modal = null;
            this.themes = [];
            this.base = 'dark';
            this._nameAuto = true;   // track auto-vs-typed name
            this.values = {};      // working values, keyed by token
            this.baseValues = {};   // the chosen base theme's values
            this.darkValues = {};   // the :root baseline
            this.active = false;
        }

        bind() {
            this.baseSel?.addEventListener('change', () => this._loadBase(this.baseSel.value));
            this.nameInput?.addEventListener('input', () => {
                this._nameAuto = !this.nameInput.value.trim();
            });
            this.defaultSel?.addEventListener('change', () => this._saveDefault());
            this.el.querySelector('[data-te-reset]')?.addEventListener('click', () => this._loadBase(this.base));
            this.el.querySelector('[data-te-save]')?.addEventListener('click', () => this._saveToDevice());
            this.el.querySelector('[data-te-download]')?.addEventListener('click', () => this._download());
            this.el.querySelector('[data-te-download-json]')?.addEventListener('click', () => this._downloadJson());
            this.installedEl?.addEventListener('click', (e) => {
                const btn = e.target.closest('[data-te-del]');
                if (btn) this._deleteTheme(btn.dataset.teDel);
            });
        }

        _esc(s) {
            return String(s == null ? '' : s).replace(/[&<>"]/g, (c) => (
                { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]
            ));
        }

        async _confirm(message) {
            if (window.DangerousModal) {
                this._modal = this._modal || new window.DangerousModal();
                return this._modal.confirm({ label: 'Delete theme?', command: 'Delete', description: message });
            }
            return window.confirm(message);
        }

        async onActivated() {
            this.active = true;
            const tc = window.themeController;
            this._enteredTheme = tc ? tc.current() : (root.getAttribute('data-theme') || 'dark');
            if (!this._loaded) {
                await this._fetchThemes();
                if (!this.active) return;
                this.darkValues = readTheme('dark', ALL_TOKENS.concat(CARRIED_TOKENS));
                this._renderGroups();
                this._loaded = true;
                this._loadBase(this._enteredTheme || 'dark');
            } else if (this.base !== this._enteredTheme && !this._hasEdits()) {
                // Re-entering after the active theme changed elsewhere (topbar
                // toggle): start from what's on screen now. Keep in-progress
                // swatch edits though : don't wipe unsaved work.
                this._loadBase(this._enteredTheme);
            }
            this.active = true;
            this._applyPreview();
            this._renderInstalled();
        }

        _hasEdits() {
            return ALL_TOKENS.some((t) => (this.values[t] || '') !== (this.baseValues[t] || ''));
        }

        onLeft() {
            this.active = false;
            ALL_TOKENS.forEach((n) => root.style.removeProperty(n));
            this._setTheme(this._enteredTheme || 'dark');
        }

        _setTheme(themeId) {
            const tc = window.themeController;
            if (tc && typeof tc._setAttr === 'function') { tc._setAttr(themeId); return; }
            if (themeId === 'dark') root.removeAttribute('data-theme');
            else root.setAttribute('data-theme', themeId);
            try { window.dispatchEvent(new CustomEvent('meshpoint:themechange')); } catch (_e) {}
        }

        async _fetchThemes() {
            try {
                const res = await fetch('/api/themes', { credentials: 'same-origin' });
                const data = res.ok ? await res.json() : {};
                this.themes = Array.isArray(data.themes) ? data.themes : [];
                const opts = this._groupedOptions();
                if (this.defaultSel) { this.defaultSel.innerHTML = opts; this.defaultSel.value = data.default || 'dark'; }
                if (this.baseSel) { this.baseSel.innerHTML = opts; this.baseSel.value = this.base; }
            } catch (_e) {
                this._set(this.status, 'error', 'Could not load the theme list.');
            }
        }

        // Built-in themes and plugin drop-ins in separate <optgroup>s so
        // the picker shows the curated set first, then a labelled divider.
        _groupedOptions() {
            const esc = (s) => this._esc(s);
            const opt = (t) => `<option value="${esc(t.id)}">${esc(t.label || t.id)}</option>`;
            const group = (label, src) => {
                const rows = this.themes.filter((t) => (t.source || 'builtin') === src);
                return rows.length ? `<optgroup label="${label}">${rows.map(opt).join('')}</optgroup>` : '';
            };
            return group('Built-in', 'builtin') + group('Community', 'plugin');
        }

        _renderGroups() {
            this.groupsEl.innerHTML = GROUPS.map((g) => `
                <div class="te-group">
                    <div class="te-group__legend">${g.legend}</div>
                    <div class="te-swatches">
                        ${g.tokens.map(([name, type]) => `
                            <label class="te-swatch" data-token="${name}">
                                <input type="color" class="te-swatch__chip" data-role="hex">
                                <span class="te-swatch__meta">
                                    <span class="te-swatch__name">${name.replace(/^--/, '')}</span>
                                    <span class="te-swatch__value" data-role="val"></span>
                                </span>
                                ${type === ALPHA ? '<input type="range" class="te-swatch__alpha" min="0" max="1" step="0.01" data-role="alpha" title="opacity">' : ''}
                            </label>`).join('')}
                    </div>
                </div>`).join('');

            this.groupsEl.querySelectorAll('.te-swatch').forEach((sw) => {
                const token = sw.dataset.token;
                const hex = sw.querySelector('[data-role="hex"]');
                const alpha = sw.querySelector('[data-role="alpha"]');
                const on = () => {
                    const c = toRgba(hex.value) || { r: 0, g: 0, b: 0, a: 1 };
                    if (alpha) c.a = parseFloat(alpha.value);
                    this.values[token] = alpha ? toRgbaStr(c) : toHex(c);
                    this._syncSwatch(sw);
                    if (this.active) {
                        root.style.setProperty(token, this.values[token]);
                        try { window.dispatchEvent(new CustomEvent('meshpoint:themechange')); } catch (_e) {}
                    }
                };
                hex.addEventListener('input', on);
                alpha?.addEventListener('input', on);
            });
        }

        _loadBase(themeId) {
            this.base = themeId || 'dark';
            if (this.baseSel) this.baseSel.value = this.base;
            this.baseValues = readTheme(this.base);
            this.values = { ...this.baseValues };
            this.groupsEl.querySelectorAll('.te-swatch').forEach((sw) => this._syncSwatch(sw, true));
            if (this.active) this._applyPreview();
            if (this._nameAuto) this.nameInput.value = `${this.base}-custom`;
            this._renderBaseMeta();
        }

        _renderBaseMeta() {
            const node = this.baseMeta;
            if (!node) return;
            const t = this.themes.find((x) => x.id === this.base) || {};
            const bits = [];
            if (t.description) bits.push(t.description);
            if (t.author) bits.push(`by ${t.author}`);
            node.textContent = bits.join(' · ');
            if (/^https?:\/\//i.test(t.homepage || "")) {
                const a = document.createElement('a');
                a.href = t.homepage;
                a.target = '_blank';
                a.rel = 'noopener noreferrer';
                a.textContent = ' ↗';
                node.appendChild(a);
            }
            node.hidden = !node.textContent.trim();
        }

        _syncSwatch(sw, fromBase) {
            const token = sw.dataset.token;
            const val = this.values[token] || '';
            const c = toRgba(val);
            const hex = sw.querySelector('[data-role="hex"]');
            const alpha = sw.querySelector('[data-role="alpha"]');
            const label = sw.querySelector('[data-role="val"]');
            if (c) {
                if (fromBase) hex.value = toHex(c);
                if (alpha && fromBase) alpha.value = String(c.a);
            }
            label.textContent = val;
            sw.classList.toggle('te-swatch--changed', val && val !== this.baseValues[token]);
        }

        _applyPreview() {
            ALL_TOKENS.forEach((n) => {
                if (this.values[n] && this.values[n] !== this.baseValues[n]) {
                    root.style.setProperty(n, this.values[n]);
                } else {
                    root.style.removeProperty(n);
                }
            });
            this._setTheme(this.base);
        }

        _slug() {
            return (this.nameInput.value || 'my-theme').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'my-theme';
        }

        _label() {
            const raw = (this.nameInput.value || 'My theme').trim();
            return raw.charAt(0).toUpperCase() + raw.slice(1);
        }

        _themeCss() {
            const slug = this._slug();
            // Include every token that differs from the :root (dark) baseline,
            // so the file is self-contained regardless of base polarity.
            const lines = ALL_TOKENS
                .filter((t) => (this.values[t] || '') && this.values[t] !== this.darkValues[t])
                .map((t) => `    ${t}: ${this.values[t]};`);

            // Messages panel / Terminal chrome -- not editable here (you can't
            // see those surfaces from the builder). Every one is listed so you
            // have the full set to hand-tune: tokens that already differ from
            // the dark baseline are active, the rest are commented out and
            // inherit until you uncomment them.
            const withRef = !!this.carryRef?.checked;
            const carried = readTheme(this.base, CARRIED_TOKENS);
            const carriedLines = CARRIED_TOKENS.map((t) => {
                const v = carried[t] || this.darkValues[t] || '';
                if (v && v !== this.darkValues[t]) return `    ${t}: ${v};`;
                return withRef ? `    /* ${t}: ${v}; */` : null;
            }).filter(Boolean);
            const carriedBlock = carriedLines.length
                ? `\n\n    /* Messages panel + Terminal -- carried from "${this.base}".`
                  + (withRef ? ' Uncomment + edit to override; they inherit otherwise.' : ' Adjust to taste.')
                  + ` */\n${carriedLines.join('\n')}`
                : '';

            return `/* ${this._label()} -- generated by the Meshpoint theme builder`
                + ` (based on ${this.base}). Drop this folder in plugins/themes/. */\n\n`
                + `html[data-theme="${slug}"] {\n${lines.join('\n')}${carriedBlock}\n}\n`;
        }

        _themeJson() {
            const j = { id: this._slug(), label: this._label(), icon: 'palette' };
            const author = (this.authorInput?.value || '').trim();
            const homepage = (this.homepageInput?.value || '').trim();
            const description = (this.descInput?.value || '').trim();
            if (author) j.author = author;
            if (homepage) j.homepage = homepage;
            if (description) j.description = description;
            return JSON.stringify(j, null, 2) + '\n';
        }

        _download() {
            const css = this._themeCss();
            const tokenCount = (css.match(/^\s+--/gm) || []).length;
            if (!tokenCount) { this._set(this.status, 'error', 'Nothing to save : the palette still matches the dark baseline.'); return; }
            this._save('theme.css', css, 'text/css');
            this._set(this.status, 'success', `Saved theme.css (${tokenCount} tokens). Put it in plugins/themes/${this._slug()}/ with theme.json, then restart.`);
        }

        _downloadJson() {
            this._save('theme.json', this._themeJson(), 'application/json');
        }

        _save(filename, text, mime) {
            const blob = new Blob([text], { type: mime });
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            a.remove();
            setTimeout(() => URL.revokeObjectURL(a.href), 1000);
        }

        async _saveDefault() {
            const theme = this.defaultSel.value;
            try {
                const res = await fetch('/api/config/dashboard/theme', {
                    method: 'PUT',
                    credentials: 'same-origin',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ theme }),
                });
                if (!res.ok) {
                    const err = await res.json().catch(() => ({}));
                    this._set(this.defaultStatus, 'error', err.detail || `Could not save (${res.status}).`);
                    return;
                }
                this._set(this.defaultStatus, 'success', 'Saved. New sessions default to this theme.');
            } catch (_e) {
                this._set(this.defaultStatus, 'error', 'Could not reach the server.');
            }
        }

        async _saveToDevice() {
            const css = this._themeCss();
            const tokenCount = (css.match(/^\s+--/gm) || []).length;
            if (!tokenCount) {
                this._set(this.status, 'error', 'Nothing to save : the palette still matches the dark baseline.');
                return;
            }
            const id = this._slug();
            const clash = this.themes.find((t) => t.id === id && t.source === 'plugin');
            if (clash?.locked) {
                this._set(this.status, 'error', `"${id}" is a built-in community theme and can't be overwritten. Pick a different name.`);
                return;
            }
            if (clash && !(await this._confirm(`A theme called "${id}" already exists in plugins/themes/. Overwrite it?`))) {
                return;
            }

            this._set(this.status, 'pending', 'Saving…');
            try {
                const res = await fetch('/api/themes', {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        id,
                        label: this._label(),
                        icon: 'palette',
                        author: (this.authorInput?.value || '').trim(),
                        homepage: (this.homepageInput?.value || '').trim(),
                        description: (this.descInput?.value || '').trim(),
                        css,
                    }),
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    this._set(this.status, 'error', data.detail || `Could not save (${res.status}).`);
                    return;
                }
                this._set(this.status, 'success',
                    `${data.overwritten ? 'Updated' : 'Saved'} theme. Reload the dashboard to use it.`);
                await this._fetchThemes();
                this._renderInstalled();
            } catch (_e) {
                this._set(this.status, 'error', 'Could not reach the server.');
            }
        }

        _renderInstalled() {
            const el = this.installedEl;
            if (!el) return;
            if (!this.themes.length) { el.innerHTML = '<p class="cfg-card__hint">No themes found.</p>'; return; }
            const glyph = (key) => (window.themeGlyph ? window.themeGlyph(key, 18) : '');
            const row = (t) => {
                const isPlugin = (t.source || 'builtin') === 'plugin';
                const locked = isPlugin && !!t.locked;
                const badgeMod = isPlugin ? (locked ? 'plugin' : 'custom') : 'builtin';
                const badgeLabel = isPlugin ? (locked ? 'Community' : 'Custom') : 'Built-in';
                const meta = [t.author, t.description].filter(Boolean).map((s) => this._esc(s)).join(' : ');
                return `<tr>
                    <td class="te-installed__name">
                        <span class="te-installed__icon">${glyph(t.icon)}</span>
                        <span>${this._esc(t.label || t.id)}<br><code class="te-installed__id">${this._esc(t.id)}</code></span>
                    </td>
                    <td><span class="te-installed__badge te-installed__badge--${badgeMod}">${badgeLabel}</span></td>
                    <td class="te-installed__meta">${meta}</td>
                    <td class="te-installed__act">${isPlugin && !locked ? `<button type="button" class="te-installed__del" data-te-del="${this._esc(t.id)}">Delete</button>` : ''}</td>
                </tr>`;
            };
            el.innerHTML = `<table class="te-installed">
                <thead><tr><th>Theme</th><th>Source</th><th>By</th><th></th></tr></thead>
                <tbody>${this.themes.map(row).join('')}</tbody>
            </table>`;
        }

        async _deleteTheme(id) {
            if (!id) return;
            if (!(await this._confirm(`Delete the "${id}" theme from plugins/themes/? This removes the folder on the device.`))) return;
            this._set(this.status, 'pending', `Deleting ${id}…`);
            try {
                const res = await fetch(`/api/themes/${encodeURIComponent(id)}`, {
                    method: 'DELETE',
                    credentials: 'same-origin',
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    this._set(this.status, 'error', data.detail || `Could not delete (${res.status}).`);
                    return;
                }
                this._set(this.status, 'success', `Deleted ${id}.`);
                await this._fetchThemes();
                this._renderInstalled();
                if (this.base === id) this._loadBase(this.defaultSel?.value || 'dark');
            } catch (_e) {
                this._set(this.status, 'error', 'Could not reach the server.');
            }
        }

        _set(node, kind, msg) {
            if (!node) return;
            node.dataset.kind = kind;
            node.textContent = msg;
        }
    }

    window.ThemeEditor = ThemeEditor;
})();
