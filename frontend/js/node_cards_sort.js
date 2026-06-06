/**
 * Pure comparator helpers for the node cards grid.
 *
 * Extracted from node_cards.js to keep that file under the 400-line
 * threshold per the project file-length rule. These functions take
 * plain node objects + a sort key and return a comparator suitable
 * for Array.prototype.sort. No DOM, no localStorage, no class state.
 *
 * Sort key contract:
 *   last_heard -> descending; null/NaN at end
 *   signal     -> latest_rssi descending; null at end; tie-break by last_heard
 *   hops       -> latest_hops ascending (direct first); null at end; tie-break by last_heard
 *   name       -> locale-aware case-insensitive ascending
 *
 * Filter modes (node list + map markers):
 *   all       -> pass through
 *   direct    -> keep nodes with hop_count == 0
 *   relayed   -> keep nodes with hop_count  > 0
 */

class MeshpointNodeCardsSort {
    static FILTER_STORAGE_KEY = 'meshpoint.nodeCards.filter';
    static FILTER_KEYS = new Set(['all', 'direct', 'relayed']);

    static readSavedFilter() {
        try {
            const v = localStorage.getItem(MeshpointNodeCardsSort.FILTER_STORAGE_KEY);
            return MeshpointNodeCardsSort.FILTER_KEYS.has(v) ? v : 'all';
        } catch (_e) {
            return 'all';
        }
    }

    static applyFilter(nodes, filter) {
        if (filter === 'direct') {
            return nodes.filter((n) => Number(n.latest_hops ?? n.hop_count ?? 0) === 0);
        }
        if (filter === 'relayed') {
            return nodes.filter((n) => Number(n.latest_hops ?? n.hop_count ?? 0) > 0);
        }
        return nodes;
    }

    /**
     * Sort with optional favorites pin: when favIds (Set or Array) is
     * provided and non-empty, favorited nodes always come before non-
     * favorites; ties within each group fall back to baseCmp(sortBy).
     */
    static applySort(nodes, sortBy, favIds = null) {
        const baseCmp = MeshpointNodeCardsSort._comparator(sortBy);
        const favSet = favIds instanceof Set ? favIds : new Set(favIds || []);
        const usePin = favSet.size > 0;
        return nodes.slice().sort((a, b) => {
            if (usePin) {
                const af = favSet.has(a.node_id) ? 1 : 0;
                const bf = favSet.has(b.node_id) ? 1 : 0;
                if (af !== bf) return bf - af;
            }
            return baseCmp(a, b);
        });
    }

    static _comparator(sortBy) {
        const heardDesc = MeshpointNodeCardsSort._compareLastHeardDesc;
        switch (sortBy) {
            case 'signal':
                return (a, b) =>
                    MeshpointNodeCardsSort._compareNum(
                        a.latest_rssi ?? a.rssi, b.latest_rssi ?? b.rssi, 'desc'
                    ) || heardDesc(a, b);
            case 'hops':
                return (a, b) =>
                    MeshpointNodeCardsSort._compareNum(
                        a.latest_hops ?? a.hop_count, b.latest_hops ?? b.hop_count, 'asc'
                    ) || heardDesc(a, b);
            case 'name':
                return MeshpointNodeCardsSort._compareName;
            case 'last_heard':
            default:
                return heardDesc;
        }
    }

    static _compareNum(a, b, direction) {
        const an = (a == null || Number.isNaN(Number(a))) ? null : Number(a);
        const bn = (b == null || Number.isNaN(Number(b))) ? null : Number(b);
        if (an === null && bn === null) return 0;
        if (an === null) return 1;
        if (bn === null) return -1;
        return direction === 'asc' ? an - bn : bn - an;
    }

    static _compareLastHeardDesc(a, b) {
        const am = MeshpointNodeCardsSort._heardMs(a.last_heard || a.last_seen);
        const bm = MeshpointNodeCardsSort._heardMs(b.last_heard || b.last_seen);
        const aMissing = Number.isNaN(am);
        const bMissing = Number.isNaN(bm);
        if (aMissing && bMissing) return 0;
        if (aMissing) return 1;
        if (bMissing) return -1;
        return bm - am;
    }

    static _compareName(a, b) {
        const an = (a.long_name || a.short_name || a.node_id || '').toString();
        const bn = (b.long_name || b.short_name || b.node_id || '').toString();
        return an.localeCompare(bn, undefined, { sensitivity: 'base' });
    }

    /** Robust ISO-or-space-separated UTC timestamp parser. */
    static _heardMs(ts) {
        if (!ts) return NaN;
        const raw = String(ts).trim();
        const hasTz = /[zZ]$|[+-]\d{2}:\d{2}$/.test(raw);
        const iso = hasTz ? raw : raw.replace(' ', 'T') + 'Z';
        const ms = Date.parse(iso);
        return Number.isNaN(ms) ? NaN : ms;
    }
}

window.MeshpointNodeCardsSort = MeshpointNodeCardsSort;
