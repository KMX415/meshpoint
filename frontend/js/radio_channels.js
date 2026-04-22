/**
 * Channel configuration component for the Radio tab.
 * Renders a table of Meshtastic channels with name, PSK,
 * computed hash preview, enable/disable toggles, concentrator
 * slot assignment, and per-row delete (except the primary channel).
 */
class RadioChannels {
    constructor(containerEl) {
        this._container = containerEl;
        this._channels = [];
        this._slots = [];
        this._presets = [];
    }

    render(channels, slots, presets) {
        this._channels = channels || [];
        this._slots = slots || [];
        this._presets = presets || [];

        const rows = this._channels.map((ch, i) => this._buildRow(ch, i)).join('');

        this._container.innerHTML = `
            <h3 class="radio-card__title">Channels</h3>
            <table class="radio-ch__table">
                <thead>
                    <tr>
                        <th>#</th>
                        <th>Name</th>
                        <th>PSK (Base64)</th>
                        <th>Hash</th>
                        <th>Slot</th>
                        <th>On</th>
                        <th></th>
                    </tr>
                </thead>
                <tbody id="radio-ch-body">${rows}</tbody>
            </table>
            <div class="radio-ch__actions">
                <button class="radio-save-btn radio-save-btn--secondary" id="radio-ch-add">+ Add Channel</button>
                <button class="radio-save-btn" id="radio-ch-save">Save Channels</button>
            </div>
        `;

        this._bindRowEvents(this._container.querySelectorAll('.radio-ch__row'));

        document.getElementById('radio-ch-add').addEventListener('click', () => {
            this._addEmptyRow();
        });

        document.getElementById('radio-ch-save').addEventListener('click', async () => {
            await this._save();
        });
    }

    _buildRow(ch, i) {
        const isPrimary = ch.index === 0;
        const slotOpts = this._slotOptions(ch.concentrator_slot);
        const delCell = isPrimary
            ? '<td></td>'
            : `<td><button class="radio-ch__del" title="Delete channel">&times;</button></td>`;

        return `
            <tr class="radio-ch__row" data-index="${i}" data-ch-index="${ch.index}">
                <td class="radio-ch__idx">${ch.index}</td>
                <td><input class="radio-input radio-ch__name" value="${this._esc(ch.name || '')}" placeholder="Channel name" data-field="name"></td>
                <td class="radio-ch__psk-cell">
                    <input class="radio-input radio-input--mono radio-ch__psk" type="password" value="${this._esc(ch.psk_b64 || '')}" placeholder="Base64 PSK" data-field="psk_b64">
                    <button class="radio-ch__reveal" title="Show/hide key">&#128065;</button>
                </td>
                <td class="radio-ch__hash radio-value--mono">${ch.hash || '--'}</td>
                <td><select class="radio-ch__slot" ${isPrimary ? 'disabled' : ''}>${slotOpts}</select></td>
                <td><input type="checkbox" class="radio-ch__enabled" data-field="enabled" ${ch.enabled ? 'checked' : ''}></td>
                ${delCell}
            </tr>
        `;
    }

    _slotOptions(selectedSlot) {
        const noneSelected = selectedSlot == null ? 'selected' : '';
        let opts = `<option value="" ${noneSelected}>—</option>`;
        for (const s of this._slots) {
            if (!s.enabled) continue;
            const preset = this._presets.find(p => p.name === s.preset);
            const label = `IF ${s.slot_index} — ${preset ? preset.display_name : s.preset} @ ${s.frequency_slot}`;
            const sel = selectedSlot === s.slot_index ? 'selected' : '';
            opts += `<option value="${s.slot_index}" ${sel}>${label}</option>`;
        }
        return opts;
    }

    _bindRowEvents(rows) {
        rows.forEach(row => {
            const pskInput = row.querySelector('.radio-ch__psk');
            const nameInput = row.querySelector('.radio-ch__name');
            const hashCell = row.querySelector('.radio-ch__hash');
            const revealBtn = row.querySelector('.radio-ch__reveal');
            const delBtn = row.querySelector('.radio-ch__del');

            revealBtn && revealBtn.addEventListener('click', () => {
                pskInput.type = pskInput.type === 'password' ? 'text' : 'password';
            });

            pskInput && pskInput.addEventListener('input', () => {
                hashCell.textContent = this._computeHash(nameInput.value, pskInput.value);
            });

            nameInput && nameInput.addEventListener('input', () => {
                hashCell.textContent = this._computeHash(nameInput.value, pskInput.value);
            });

            delBtn && delBtn.addEventListener('click', () => row.remove());
        });
    }

    _addEmptyRow() {
        const tbody = document.getElementById('radio-ch-body');
        const newIndex = tbody.querySelectorAll('tr').length;
        const tr = document.createElement('tr');
        tr.className = 'radio-ch__row';
        tr.dataset.index = newIndex;
        tr.dataset.chIndex = newIndex;

        tr.innerHTML = `
            <td class="radio-ch__idx">${newIndex}</td>
            <td><input class="radio-input radio-ch__name" value="" placeholder="Channel name" data-field="name"></td>
            <td class="radio-ch__psk-cell">
                <input class="radio-input radio-input--mono radio-ch__psk" type="password" value="" placeholder="Base64 PSK" data-field="psk_b64">
                <button class="radio-ch__reveal" title="Show/hide key">&#128065;</button>
            </td>
            <td class="radio-ch__hash radio-value--mono">--</td>
            <td><select class="radio-ch__slot">${this._slotOptions(null)}</select></td>
            <td><input type="checkbox" class="radio-ch__enabled" data-field="enabled" checked></td>
            <td><button class="radio-ch__del" title="Delete channel">&times;</button></td>
        `;

        this._bindRowEvents([tr]);
        tbody.appendChild(tr);
    }

    async _save() {
        const rows = document.querySelectorAll('#radio-ch-body .radio-ch__row');
        const channels = [];

        rows.forEach(row => {
            const chIndex = parseInt(row.dataset.chIndex);
            const name = row.querySelector('.radio-ch__name').value.trim();
            const psk = row.querySelector('.radio-ch__psk').value.trim();
            const enabled = row.querySelector('.radio-ch__enabled').checked;
            const slotEl = row.querySelector('.radio-ch__slot');
            const slotVal = slotEl && slotEl.value !== '' ? parseInt(slotEl.value) : null;

            if (chIndex === 0) {
                channels.push({ index: 0, name, psk_b64: psk, enabled, concentrator_slot: null });
                return;
            }
            if (name || psk) {
                channels.push({ name, psk_b64: psk, enabled, concentrator_slot: slotVal });
            }
        });

        try {
            const res = await fetch('/api/config/channels', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ channels }),
            });
            if (res.ok) {
                this._showToast('Channels saved');
            } else {
                const err = await res.json().catch(() => ({}));
                this._showToast(`Error: ${err.detail || res.status}`);
            }
        } catch (e) {
            this._showToast('Save failed');
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
            const DEFAULT_PSK = [0xD4,0xF1,0xBB,0x3A,0x20,0x29,0x07,0x59,0xF0,0xBC,0xFF,0xAB,0xCF,0x4E,0x69,0x01];
            const idx = raw.charCodeAt(0);
            if (idx === 0) return '\0'.repeat(16);
            const key = [...DEFAULT_PSK];
            key[15] = (key[15] + idx - 1) & 0xFF;
            return String.fromCharCode(...key);
        }
        return (raw + '\0'.repeat(16)).slice(0, 16);
    }

    _showToast(msg) {
        let toast = document.getElementById('radio-toast');
        if (!toast) {
            toast = document.createElement('div');
            toast.id = 'radio-toast';
            toast.className = 'radio-toast';
            document.body.appendChild(toast);
        }
        toast.textContent = msg;
        toast.classList.add('radio-toast--visible');
        setTimeout(() => toast.classList.remove('radio-toast--visible'), 2500);
    }

    _esc(str) {
        const el = document.createElement('span');
        el.textContent = str || '';
        return el.innerHTML;
    }
}
