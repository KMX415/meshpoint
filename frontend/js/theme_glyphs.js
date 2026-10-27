/**
 * Theme icon glyphs — one place, used by the topbar theme button, its
 * hold-to-open picker, and the Settings → Themes "Installed" list.
 *
 * A theme's `theme.json` "icon" is a keyword from this set; an unknown
 * keyword falls back to `moon`, so a new theme folder still gets a
 * usable icon with no code change. Keep THEME_GLYPH_KEYS in sync with
 * `_KNOWN_ICONS` in src/api/theme_store.py (the save endpoint validates
 * against that list).
 */
(function () {
    const SVG = (inner, size) => `
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
             stroke-linecap="round" stroke-linejoin="round" width="${size}" height="${size}"
             aria-hidden="true">${inner}</svg>`;

    const PATHS = {
        moon: '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>',
        contrast: '<circle cx="12" cy="12" r="9"/>'
            + '<path d="M12 3a9 9 0 0 1 0 18z" fill="currentColor" stroke="none"/>',
        sun: '<circle cx="12" cy="12" r="4"/>'
            + '<path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4'
            + 'M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
        day: '<circle cx="12" cy="12" r="5" fill="currentColor" stroke="none"/>'
            + '<path d="M12 1v3M12 20v3M1 12h3M20 12h3M4 4l2 2M18 18l2 2M4 20l2-2M18 6l2-2"/>',
        monitor: '<rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8M12 17v4"/>',
        terminal: '<rect x="2" y="3" width="20" height="18" rx="2"/><path d="M6 8l3 3-3 3M12 14h6"/>',
        palette: '<path d="M12 3a9 9 0 1 0 0 18c1 0 1.5-.7 1.5-1.5 0-.4-.2-.8-.4-1'
            + '-.3-.3-.4-.6-.4-1 0-.8.7-1.5 1.5-1.5H16a5 5 0 0 0 5-5c0-4.4-4-8-9-8z"/>'
            + '<circle cx="7.5" cy="10.5" r="1" fill="currentColor" stroke="none"/>'
            + '<circle cx="12" cy="7.5" r="1" fill="currentColor" stroke="none"/>'
            + '<circle cx="16.5" cy="10.5" r="1" fill="currentColor" stroke="none"/>',
        circle: '<circle cx="12" cy="12" r="9"/>',
        // added for the community theme pack
        snowflake: '<path d="M12 2v20M3.5 7l17 10M20.5 7l-17 10"/>'
            + '<path d="M12 6l2-2M12 6l-2-2M12 18l2 2M12 18l-2 2'
            + 'M6.5 9L4 8M6.5 9L6 6.5M17.5 15l2.5 1M17.5 15l.5 2.5'
            + 'M6.5 15L4 16M6.5 15L6 17.5M17.5 9l2.5-1M17.5 9l.5-2.5"/>',
        leaf: '<path d="M4 20c0-9 6-16 16-16 0 10-6 16-16 16z"/><path d="M4 20C8 16 12 13 20 4"/>',
        flower: '<circle cx="12" cy="12" r="2.5"/><circle cx="12" cy="6.5" r="2.5"/>'
            + '<circle cx="12" cy="17.5" r="2.5"/><circle cx="6.5" cy="12" r="2.5"/>'
            + '<circle cx="17.5" cy="12" r="2.5"/>',
        wave: '<path d="M2 8c3-4 6 4 9 0s6-4 9 0M2 16c3-4 6 4 9 0s6-4 9 0"/>',
        droplet: '<path d="M12 3c5 6 7 9 7 12a7 7 0 0 1-14 0c0-3 2-6 7-12z"/>',
        sparkles: '<path d="M12 3l1.6 4.8L18 9l-4.4 1.2L12 15l-1.6-4.8L6 9l4.4-1.2z"/>'
            + '<path d="M18 14l.8 2.2L21 17l-2.2.8L18 20l-.8-2.2L15 17l2.2-.8z"/>',
        atom: '<circle cx="12" cy="12" r="1.5" fill="currentColor" stroke="none"/>'
            + '<ellipse cx="12" cy="12" rx="9.5" ry="4"/>'
            + '<ellipse cx="12" cy="12" rx="9.5" ry="4" transform="rotate(60 12 12)"/>'
            + '<ellipse cx="12" cy="12" rx="9.5" ry="4" transform="rotate(120 12 12)"/>',
        mountain: '<path d="M3 20l5.5-9 3.5 5 2.5-3.5L21 20z"/><circle cx="17" cy="6" r="2"/>',
        eye: '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7z"/>'
            + '<circle cx="12" cy="12" r="3"/>',
    };

    window.THEME_GLYPH_KEYS = Object.keys(PATHS);

    /** SVG markup string for an icon keyword; falls back to `moon`. */
    window.themeGlyph = function themeGlyph(key, size = 16) {
        return SVG(PATHS[key] || PATHS.moon, size);
    };
})();
