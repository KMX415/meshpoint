/**
 * Channel configuration card for the Radio tab.
 *
 * Renders the Meshtastic channel table (name, PSK, computed hash,
 * enabled toggle). The table itself is intentionally boring per the
 * v0.7.1 redesign scope -- structure and behavior unchanged from
 * v0.6.x, only restyled to match the surrounding cards.
 */
class RadioChannels {
    constructor(containerEl) {
        this._container = containerEl;
        this._channels = [];
        this._focusedRow = null;
    }

    render(channels) {
        this._channels = channels || [];

        const rows = this._channels.map((ch, i) => `
            <tr class="ch-table__row" data-index="${i}">
                <td class="ch-table__idx">${ch.index}</td>
                <td>
                    <input class="ch-table__name-input" data-field="name"
                           value="${this._esc(ch.name || '')}"
                           placeholder="Channel name" />
                </td>
                <td class="ch-table__psk-cell">
                    <input class="ch-table__name-input" data-field="psk_b64"
                           type="password"
                           value="${this._esc(ch.psk_b64 || '')}"
                           placeholder="Base64 PSK" />
                    <button class="ch-table__reveal" data-index="${i}"
                            title="Show/hide key">&#128065;</button>
                </td>
                <td class="ch-table__hash">${ch.hash || '--'}</td>
                <td>
                    <input type="checkbox" data-field="enabled"
                           ${ch.enabled ? 'checked' : ''} />
                </td>
            </tr>
        `).join('');

        this._container.classList.add('r-card');
        this._container.innerHTML = `
            <div class="r-card__header">
                <h3 class="r-card__title">Channels</h3>
                <span class="r-card__subtitle">
                    ${this._channels.length} configured
                </span>
            </div>
            <table class="ch-table">
                <thead>
                    <tr>
                        <th>#</th>
                        <th>Name</th>
                        <th>PSK (Base64)</th>
                        <th>Hash</th>
                        <th>On</th>
                    </tr>
                </thead>
                <tbody id="r-ch-body">${rows}</tbody>
            </table>
            <div class="r-card__actions">
                <button class="r-btn r-btn--warn" id="r-ch-delete"
                        style="display:none">
                    Delete Channel
                </button>
                <button class="r-btn r-btn--secondary" id="r-ch-add">
                    + Add Channel
                </button>
                <button class="r-btn r-btn--primary" id="r-ch-save">
                    Save Channels
                </button>
            </div>
        `;

        this._wireRowHandlers(this._container);
        document.getElementById('r-ch-add').addEventListener(
            'click', () => this._addEmptyRow(),
        );
        document.getElementById('r-ch-save').addEventListener(
            'click', () => this._save(),
        );

        const delBtn = document.getElementById('r-ch-delete');
        // preventDefault on mousedown keeps focus on the row input so blur
        // does not fire before click, which would hide the button too early.
        delBtn.addEventListener('mousedown', (e) => e.preventDefault());
        delBtn.addEventListener('click', () => this._deleteRow());
    }

    _wireRowHandlers(scope) {
        scope.querySelectorAll('.ch-table__reveal').forEach((btn) => {
            btn.addEventListener('click', () => {
                const row = btn.closest('tr');
                const input = row.querySelector('[data-field="psk_b64"]');
                input.type = input.type === 'password' ? 'text' : 'password';
            });
        });

        scope.querySelectorAll('[data-field="psk_b64"]').forEach((input) => {
            input.addEventListener('input', () => this._refreshHash(input.closest('tr')));
        });

        scope.querySelectorAll('[data-field="name"]').forEach((input) => {
            input.addEventListener('input', () => this._refreshHash(input.closest('tr')));
        });

        scope.querySelectorAll('.ch-table__row input').forEach((input) => {
            input.addEventListener('focus', () => {
                const row = input.closest('tr');
                const tbody = document.getElementById('r-ch-body');
                const isPrimary = Array.from(tbody.rows).indexOf(row) === 0;
                this._focusedRow = isPrimary ? null : row;
                this._syncDeleteBtn();
            });
            input.addEventListener('blur', () => {
                // Defer so focus can settle on another row input before we hide.
                setTimeout(() => {
                    if (!this._container.querySelector('.ch-table__row input:focus')) {
                        this._focusedRow = null;
                        this._syncDeleteBtn();
                    }
                }, 0);
            });
        });
    }

    _syncDeleteBtn() {
        const btn = document.getElementById('r-ch-delete');
        if (btn) btn.style.display = this._focusedRow ? '' : 'none';
    }

    _deleteRow() {
        if (!this._focusedRow) return;
        if (!confirm('Delete this channel?')) return;
        this._focusedRow.remove();
        this._focusedRow = null;
        this._syncDeleteBtn();
    }

    _refreshHash(row) {
        const name = row.querySelector('[data-field="name"]').value;
        const psk = row.querySelector('[data-field="psk_b64"]').value;
        row.querySelector('.ch-table__hash').textContent = this._computeHash(name, psk);
    }

    _addEmptyRow() {
        const tbody = document.getElementById('r-ch-body');
        const newIndex = tbody.querySelectorAll('tr').length;
        const tr = document.createElement('tr');
        tr.className = 'ch-table__row';
        tr.dataset.index = newIndex;
        tr.innerHTML = `
            <td class="ch-table__idx">${newIndex}</td>
            <td>
                <input class="ch-table__name-input" data-field="name"
                       value="" placeholder="Channel name" />
            </td>
            <td class="ch-table__psk-cell">
                <input class="ch-table__name-input" data-field="psk_b64"
                       type="password" value="" placeholder="Base64 PSK" />
                <button class="ch-table__reveal"
                        title="Show/hide key">&#128065;</button>
            </td>
            <td class="ch-table__hash">--</td>
            <td>
                <input type="checkbox" data-field="enabled" checked />
            </td>
        `;
        this._wireRowHandlers(tr);
        tbody.appendChild(tr);
    }

    async _save() {
        const rows = document.querySelectorAll('#r-ch-body tr');
        const channels = [];

        rows.forEach((row, i) => {
            const name = row.querySelector('[data-field="name"]').value.trim();
            const psk = row.querySelector('[data-field="psk_b64"]').value.trim();
            const enabled = row.querySelector('[data-field="enabled"]').checked;
            if (i === 0) {
                channels.push({ index: 0, name, psk_b64: psk, enabled });
                return;
            }
            if (name || psk) channels.push({ name, psk_b64: psk, enabled });
        });

        try {
            const res = await fetch('/api/config/channels', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ channels }),
            });
            if (res.ok) {
                this._toast('Channels saved');
            } else {
                const err = await res.json().catch(() => ({}));
                this._toast(`Error: ${err.detail || res.status}`);
            }
        } catch (e) {
            this._toast(`Save failed: ${e.message}`);
        }
    }

    _computeHash(name, pskB64) {
        try {
            if (!pskB64) return '--';
            const raw = atob(pskB64);
            const expanded = this._expandKey(raw);
            let h = 0;
            for (let i = 0; i < name.length; i++) h ^= name.charCodeAt(i);
            for (let i = 0; i < expanded.length; i++) h ^= expanded.charCodeAt(i);
            h &= 0xFF;
            return '0x' + h.toString(16).toUpperCase().padStart(2, '0');
        } catch {
            return '??';
        }
    }

    _expandKey(raw) {
        if (raw.length === 0) return '\0'.repeat(16);
        if (raw.length === 16 || raw.length === 32) return raw;
        if (raw.length === 1) {
            const DEFAULT_PSK = [
                0xD4, 0xF1, 0xBB, 0x3A, 0x20, 0x29, 0x07, 0x59,
                0xF0, 0xBC, 0xFF, 0xAB, 0xCF, 0x4E, 0x69, 0x01,
            ];
            const idx = raw.charCodeAt(0);
            if (idx === 0) return '\0'.repeat(16);
            const key = [...DEFAULT_PSK];
            key[15] = (key[15] + idx - 1) & 0xFF;
            return String.fromCharCode(...key);
        }
        return (raw + '\0'.repeat(16)).slice(0, 16);
    }

    _toast(msg) {
        let toast = document.getElementById('r-toast');
        if (!toast) {
            toast = document.createElement('div');
            toast.id = 'r-toast';
            toast.className = 'r-toast';
            document.body.appendChild(toast);
        }
        toast.textContent = msg;
        toast.classList.add('r-toast--visible');
        setTimeout(() => toast.classList.remove('r-toast--visible'), 2500);
    }

    _esc(str) {
        const el = document.createElement('span');
        el.textContent = str || '';
        return el.innerHTML;
    }
}
