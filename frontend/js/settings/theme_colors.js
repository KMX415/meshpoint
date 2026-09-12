/** Colour helpers adapted from javastraat's theme editor. */
(function () {
    const root = document.documentElement;
    function resolveVar(value, depth) {
        value = (value || '').trim();
        const m = value.match(/^var\(\s*(--[a-z0-9-]+)\s*(?:,([\s\S]*))?\)$/i);
        if (m && depth < 8) {
            const inner = getComputedStyle(root).getPropertyValue(m[1]).trim();
            if (inner) return resolveVar(inner, depth + 1);
            if (m[2]) return resolveVar(m[2], depth + 1);
        }
        return value;
    }

    function toRgba(str) {
        str = (str || '').trim().toLowerCase();
        let m = str.match(/^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})?$/);
        if (m) {
            return {
                r: parseInt(m[1], 16), g: parseInt(m[2], 16), b: parseInt(m[3], 16),
                a: m[4] != null ? parseInt(m[4], 16) / 255 : 1,
            };
        }
        m = str.match(/^#([0-9a-f])([0-9a-f])([0-9a-f])$/);
        if (m) {
            return { r: parseInt(m[1] + m[1], 16), g: parseInt(m[2] + m[2], 16), b: parseInt(m[3] + m[3], 16), a: 1 };
        }
        m = str.match(/^rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)(?:[,\s/]+([\d.]+%?))?\s*\)$/);
        if (m) {
            let a = m[4] == null ? 1 : (m[4].endsWith('%') ? parseFloat(m[4]) / 100 : parseFloat(m[4]));
            return { r: +m[1], g: +m[2], b: +m[3], a };
        }
        return null;
    }

    const hex2 = (n) => Math.max(0, Math.min(255, Math.round(n))).toString(16).padStart(2, '0');
    const toHex = (c) => c ? `#${hex2(c.r)}${hex2(c.g)}${hex2(c.b)}` : '#000000';
    const toRgbaStr = (c) => `rgba(${Math.round(c.r)}, ${Math.round(c.g)}, ${Math.round(c.b)}, ${+c.a.toFixed(3)})`;

    // ---- read a theme's authored token values -------------------------
    window.ThemeColors = {resolveVar, toRgba, toHex, toRgbaStr};
})();
