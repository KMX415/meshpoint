# Vendored xterm.js

Pinned, byte-for-byte copies of the xterm.js terminal emulator and its
addons. Vendored so the dashboard `/terminal` section keeps working on
Pis with no internet route off the LAN (factory floors, field kits,
mesh-only deployments, RV / boat / cabin installs).

## Files

| File                          | Source                                                                                  | Bytes  |
|-------------------------------|-----------------------------------------------------------------------------------------|--------|
| `xterm.js`                    | https://cdn.jsdelivr.net/npm/xterm@5.3.0/lib/xterm.js                                   | 283404 |
| `xterm.css`                   | https://cdn.jsdelivr.net/npm/xterm@5.3.0/css/xterm.css                                  |   5383 |
| `xterm-addon-fit.js`          | https://cdn.jsdelivr.net/npm/xterm-addon-fit@0.8.0/lib/xterm-addon-fit.js               |   1503 |
| `xterm-addon-webgl.js`        | https://cdn.jsdelivr.net/npm/xterm-addon-webgl@0.16.0/lib/xterm-addon-webgl.js          |  99112 |
| `xterm-addon-search.js`       | https://cdn.jsdelivr.net/npm/xterm-addon-search@0.13.0/lib/xterm-addon-search.js        |  12157 |
| `xterm-addon-web-links.js`    | https://cdn.jsdelivr.net/npm/xterm-addon-web-links@0.9.0/lib/xterm-addon-web-links.js   |   2921 |
| `xterm-addon-unicode11.js`    | https://cdn.jsdelivr.net/npm/xterm-addon-unicode11@0.6.0/lib/xterm-addon-unicode11.js   |   7202 |

## Versions

- `xterm` 5.3.0
- `xterm-addon-fit` 0.8.0
- `xterm-addon-webgl` 0.16.0
- `xterm-addon-search` 0.13.0
- `xterm-addon-web-links` 0.9.0
- `xterm-addon-unicode11` 0.6.0

## Why these exact versions

Tied to whatever was on the jsdelivr CDN when the v0.7.4 terminal
polish landed. Bumping is a deliberate decision: replace the file,
update the byte count in the table above, re-run `tests/test_terminal_*`,
smoke-test the `/terminal` section on a Pi.

The addon majors must stay in sync with the xterm major (5.x). When
moving to xterm 6 in the future, every addon version needs a matching
bump.

## License

MIT, owned by the xterm.js authors. See https://github.com/xtermjs/xterm.js
for the full text. Vendored copies retain the upstream sourceMappingURL
comment.

## Refresh procedure

```bash
base="https://cdn.jsdelivr.net/npm"
curl -fsSLo frontend/vendor/xterm/xterm.js                   "$base/xterm@5.3.0/lib/xterm.js"
curl -fsSLo frontend/vendor/xterm/xterm.css                  "$base/xterm@5.3.0/css/xterm.css"
curl -fsSLo frontend/vendor/xterm/xterm-addon-fit.js         "$base/xterm-addon-fit@0.8.0/lib/xterm-addon-fit.js"
curl -fsSLo frontend/vendor/xterm/xterm-addon-webgl.js       "$base/xterm-addon-webgl@0.16.0/lib/xterm-addon-webgl.js"
curl -fsSLo frontend/vendor/xterm/xterm-addon-search.js      "$base/xterm-addon-search@0.13.0/lib/xterm-addon-search.js"
curl -fsSLo frontend/vendor/xterm/xterm-addon-web-links.js   "$base/xterm-addon-web-links@0.9.0/lib/xterm-addon-web-links.js"
curl -fsSLo frontend/vendor/xterm/xterm-addon-unicode11.js   "$base/xterm-addon-unicode11@0.6.0/lib/xterm-addon-unicode11.js"
```

Then update the byte counts in the table above.
