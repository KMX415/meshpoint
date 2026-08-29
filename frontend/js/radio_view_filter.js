/**
 * Shared All / LF / MF / LT / MC pill state for packet feed, map, and cards.
 */
class MeshpointRadioViewFilter {
    static STORAGE_KEY = 'meshpoint.radioView.preset';
    static EVENT = 'meshpoint:radioView';

    static current() {
        try {
            const v = localStorage.getItem(MeshpointRadioViewFilter.STORAGE_KEY);
            return ModemPresetLabel.KEYS.includes(v) ? v : 'all';
        } catch (_e) {
            return 'all';
        }
    }

    static set(key) {
        if (!ModemPresetLabel.KEYS.includes(key)) return;
        try {
            localStorage.setItem(MeshpointRadioViewFilter.STORAGE_KEY, key);
        } catch (_e) { /* private mode / quota */ }
        document.dispatchEvent(new CustomEvent(MeshpointRadioViewFilter.EVENT, {
            detail: { preset: key },
        }));
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

    static wirePills(root) {
        if (!root) return;
        const buttons = root.querySelectorAll('[data-radio-view]');
        const apply = (key) => {
            buttons.forEach((btn) => {
                btn.classList.toggle('nc-pill--active', btn.dataset.radioView === key);
            });
        };
        apply(MeshpointRadioViewFilter.current());
        buttons.forEach((btn) => {
            btn.addEventListener('click', () => {
                const key = btn.dataset.radioView;
                if (!ModemPresetLabel.KEYS.includes(key)) return;
                MeshpointRadioViewFilter.set(key);
                apply(key);
            });
        });
        document.addEventListener(MeshpointRadioViewFilter.EVENT, (ev) => {
            apply(ev.detail && ev.detail.preset);
        });
    }
}

window.MeshpointRadioViewFilter = MeshpointRadioViewFilter;
