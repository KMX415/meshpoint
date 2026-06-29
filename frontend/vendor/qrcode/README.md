# Vendored qrcode (node-qrcode)

Pinned browser bundle for Configuration → Channels → Quick Deploy QR.

Vendored so the QR renders on Pis with no outbound CDN access (same rationale
as `frontend/vendor/xterm/`).

## Files

| File            | Source                                                      | Bytes |
|-----------------|-------------------------------------------------------------|------:|
| `qrcode.min.js` | https://cdn.jsdelivr.net/npm/qrcode@1.5.1/build/qrcode.min.js | 23738 |

## Version

- `qrcode` 1.5.1 (soldair/node-qrcode precompiled `build/qrcode.min.js`)

Note: PR #76 referenced `@1.5.4/build/qrcode.min.js`, which returns 404 on
jsDelivr (no browser build published for that tag). 1.5.1 is the latest tag
with a `build/` bundle on the CDN at vendor time.

## Dashboard usage

Loaded from `frontend/index.html` before `quick_deploy_card.js`. Exposes global
`QRCode.toCanvas()` used by `frontend/js/configuration/quick_deploy_card.js`.
