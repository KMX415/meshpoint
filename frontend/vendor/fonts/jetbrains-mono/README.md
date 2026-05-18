# Vendored JetBrains Mono

Pinned woff2 files for the JetBrains Mono typeface, vendored so the
terminal section ships with proper coding ligatures and stays
self-hosted on offline Pis.

## Files

| File                                | Source                                                                                            | Bytes |
|-------------------------------------|---------------------------------------------------------------------------------------------------|-------|
| `JetBrainsMono-Regular.woff2`       | https://cdn.jsdelivr.net/gh/JetBrains/JetBrainsMono@v2.304/fonts/webfonts/JetBrainsMono-Regular.woff2     | 92164 |
| `JetBrainsMono-Bold.woff2`          | https://cdn.jsdelivr.net/gh/JetBrains/JetBrainsMono@v2.304/fonts/webfonts/JetBrainsMono-Bold.woff2        | 94588 |
| `JetBrainsMono-Italic.woff2`        | https://cdn.jsdelivr.net/gh/JetBrains/JetBrainsMono@v2.304/fonts/webfonts/JetBrainsMono-Italic.woff2      | 95864 |
| `JetBrainsMono-BoldItalic.woff2`    | https://cdn.jsdelivr.net/gh/JetBrains/JetBrainsMono@v2.304/fonts/webfonts/JetBrainsMono-BoldItalic.woff2  | 98152 |

## Version

`v2.304` -- the most recent stable release on the JetBrainsMono
GitHub repo when the v0.7.4 terminal polish landed.

## License

SIL Open Font License 1.1. See `OFL.txt` for the full text. The font
files are unmodified and the license accompanies them per OFL.

## Refresh procedure

```bash
v=v2.304
base="https://cdn.jsdelivr.net/gh/JetBrains/JetBrainsMono@${v}/fonts/webfonts"
dst="frontend/vendor/fonts/jetbrains-mono"
for face in Regular Bold Italic BoldItalic; do
    curl -fsSLo "${dst}/JetBrainsMono-${face}.woff2"  "${base}/JetBrainsMono-${face}.woff2"
done
curl -fsSLo "${dst}/OFL.txt" "https://cdn.jsdelivr.net/gh/JetBrains/JetBrainsMono@${v}/OFL.txt"
```

Then update the byte counts in the table above.
