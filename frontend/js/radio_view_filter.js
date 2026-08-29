/**
 * Shared preset pill state. All is always visible.
 * Named pills appear only after that preset is heard.
 */
class MeshpointRadioViewFilter {
    static STORAGE_KEY = 'meshpoint.radioView.preset';
    static EVENT = 'meshpoint:radioView';

    static _heard = new Set();
    static _root = null;
    static _pillRaf = 0;

    static current() {
        try {
            const v = localStorage.getItem(MeshpointRadioViewFilter.STORAGE_KEY);
            return ModemPresetLabel.isFilterKey(v) ? v : 'all';
        } catch (_e) {
            return 'all';
        }
    }

    static set(key) {
        if (!ModemPresetLabel.isFilterKey(key)) return;
        try {
            localStorage.setItem(MeshpointRadioViewFilter.STORAGE_KEY, key);
        } catch (_e) { /* private mode / quota */ }
        document.dispatchEvent(new CustomEvent(MeshpointRadioViewFilter.EVENT, {
            detail: { preset: key },
        }));
        MeshpointRadioViewFilter._renderPills();
    }

    static matchesPreset(preset, filterKey) {
        if (!filterKey || filterKey === 'all') return true;
        return preset != null && preset.key === filterKey;
    }

    static matchesPacket(packet, filterKey) {
        return MeshpointRadioViewFilter.matchesPreset(
            ModemPresetLabel.fromPacket(packet),
            filterKey || MeshpointRadioViewFilter.current(),
        );
    }

    static matchesNode(node, filterKey) {
        return MeshpointRadioViewFilter.matchesPreset(
            ModemPresetLabel.fromNode(node),
            filterKey || MeshpointRadioViewFilter.current(),
        );
    }

    static notePreset(preset) {
        if (!preset || preset.key === 'all') return;
        if (!ModemPresetLabel.isFilterKey(preset.key)) return;
        if (MeshpointRadioViewFilter._heard.has(preset.key)) return;
        MeshpointRadioViewFilter._heard.add(preset.key);
        MeshpointRadioViewFilter._schedulePills();
    }

    static notePacket(packet) {
        MeshpointRadioViewFilter.notePreset(ModemPresetLabel.fromPacket(packet));
    }

    static noteNodes(nodes) {
        if (!Array.isArray(nodes)) return;
        for (const node of nodes) {
            MeshpointRadioViewFilter.notePreset(ModemPresetLabel.fromNode(node));
        }
    }

    static wirePills(root) {
        if (!root) return;
        MeshpointRadioViewFilter._root = root;
        MeshpointRadioViewFilter._renderPills();
        document.addEventListener(MeshpointRadioViewFilter.EVENT, () => {
            MeshpointRadioViewFilter._renderPills();
        });
    }

    static _schedulePills() {
        if (MeshpointRadioViewFilter._pillRaf) return;
        MeshpointRadioViewFilter._pillRaf = requestAnimationFrame(() => {
            MeshpointRadioViewFilter._pillRaf = 0;
            MeshpointRadioViewFilter._renderPills();
        });
    }

    static _visibleKeys() {
        const selected = MeshpointRadioViewFilter.current();
        const keys = ['all'];
        for (const row of ModemPresetLabel.CATALOG) {
            if (MeshpointRadioViewFilter._heard.has(row.key) || row.key === selected) {
                keys.push(row.key);
            }
        }
        return keys;
    }

    static _renderPills() {
        const root = MeshpointRadioViewFilter._root;
        if (!root) return;
        const selected = MeshpointRadioViewFilter.current();
        root.replaceChildren();
        for (const key of MeshpointRadioViewFilter._visibleKeys()) {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'nc-pill';
            if (key === selected) btn.classList.add('nc-pill--active');
            btn.dataset.radioView = key;
            btn.textContent = ModemPresetLabel.chipForKey(key);
            btn.addEventListener('click', () => MeshpointRadioViewFilter.set(key));
            root.appendChild(btn);
        }
    }
}

window.MeshpointRadioViewFilter = MeshpointRadioViewFilter;
