# Polish — Real radar blips, smart upgrade indicator

Cosmetic and informational polish that completes the v0.7.4 story.

## 1. Real radar blips on /login and /setup

**Status:** [ ] Not started  [x] In progress  [ ] Pass  [ ] Blocked
**Hardware:** `.141` (active mesh traffic) and `.49` (fresh install, no traffic yet)

### Functional walkthrough on `.141` (active traffic)

1. [ ] Open `/login` in a private window on `.141`.
2. [ ] Wait for the radar to render with the rotating cyan sweep.
3. [ ] Within ~4 s of page load, real RX-driven blips begin appearing on the radar disc. Each blip:
       - Renders at radius proportional to RSSI bucket (strong = closer to center, medium = mid, weak = outer).
       - Angle randomized (we do not have AoA data); fuzzed by a few degrees per poll so repeat reads don't stack on top of each other.
       - Animates with a 6 s pop-then-fade keyframe; CSS-driven so the JS stays out of the animation hot path.
       - Strong blips are mint green, medium are amber, weak are muted blue.
4. [ ] Blip frequency tracks roughly with the actual RX rate from the concentrator (verify via `meshpoint status` or `journalctl`).
5. [ ] Open `/setup` (logged out, fresh device path). Same blip behavior visible.

### Functional walkthrough on `.49` (no traffic yet)

6. [ ] Fresh install, dashboard at `/setup`. Radar shows the rotating sweep, no blips yet (because no RX events).
7. [ ] After completing setup and waiting for at least one packet to be received, blips begin appearing on subsequent visits to `/login`.

### Endpoint security

8. [x] `GET /api/public/recent_rx` is intentionally unauthenticated (no cookie required).
9. [x] Response payload shape:
       ```json
       {"blips": [{"timestamp": 1715712760, "rssi_bucket": "strong", "bearing": 142.3, "distance": 0.18}, ...]}
       ```
10. [x] No node IDs, no source addresses, no GPS coordinates, no decoded content, no channel names.
11. [ ] Rate-limited per remote IP (sliding window). Hit it tightly in a loop on `.141`: expect later requests to drop to 429 / empty payload depending on header.

### Negative paths

- [x] Endpoint serves a bounded ring buffer; never returns more than the configured cap of recent blips.
- [x] If concentrator is down (no RX history), endpoint returns `{"blips": []}` not 500.

### Acceptance

- [ ] Real blips visible on `.141`.
- [x] Endpoint scrub assertions enforce no leakage of node id / GPS / channel / payload bytes (`tests/test_public_radar_routes.py`).
- [x] Rate-limit and ring-buffer cap enforced in tests.
- [x] RSSI bucketing covers weak / medium / strong bands; distance stays in [0, 1].

## 2. Smart upgrade indicator (in-panel preview)

**Status:** [ ] Not started  [x] In progress  [ ] Pass  [ ] Blocked
**Hardware:** `.141`

The "smart" part is the bullet list rendered inline in the Settings -> Updates panel. As soon as the operator picks a release channel, a "What's coming" / "What's new" preview block appears above the apply log with the headline + detail bullets pulled from `docs/CHANGELOG.md`. Replaces a generic "are you sure you want to apply?" prompt with concrete content.

### Functional walkthrough

1. [ ] Settings > Updates on `.141`.
2. [ ] Pick the **rc-074** channel from the picker. Expected: preview block fades in below the card with eyebrow "What's coming", header "Unreleased", and chevron-bulleted list of the bullets staged in `docs/CHANGELOG.md`'s Unreleased section. Headline rendered prominent, detail muted.
3. [ ] Pick the **stable** channel. Expected: eyebrow flips to "What's new", header reads `v<latest released>` (e.g. `v0.7.3.1 (May 13, 2026)`), bullets switch to the most recent shipped release.
4. [ ] Pick the **custom** channel. Expected: preview shows "No release-notes preview ... custom branches surface only the commit log."
5. [ ] Switch channels rapidly back and forth. Expected: only the latest selection's payload renders (race-condition guard via the controller's request token).
6. [ ] Click the bullets' container. Expected: passive copy element; no click handler attached.

### Endpoint contract

7. [x] `GET /api/update/release_notes?channel_id=<id>` is admin-only.
8. [x] Response surfaces `channel_id`, `channel_label`, `channel_tier`, `current_installed_version`, and `preview_section` (or null for custom).
9. [x] The parser is tolerant of CRLF line endings and skips header lines that aren't `Unreleased` or `vX.Y.Z (date)` shaped.
10. [x] Invalid `channel_id` returns 400. Anonymous returns 401. Viewer returns 403.

### Negative paths

- [x] If `docs/CHANGELOG.md` is unreadable on disk, the route returns `preview_section: null` (does not crash).
- [ ] If the picker is opened before channels load, no stale preview lingers.

### Acceptance

- [x] Backend parser unit tests (`tests/test_update_release_notes.py`) cover Unreleased + versioned dispatch, bullet decomposition, CRLF tolerance, and the channel-tier dispatch helper.
- [x] Backend route tests (`tests/test_update_routes.py::TestReleaseNotesRoute`) cover the rc / stable / custom paths and the role-guard 3-case.
- [ ] Pass on `.141`: visual preview matches the on-disk CHANGELOG bullets and channel switches feel instant.

## Hardware-specific checks

### `.141` (active traffic)

- [ ] Real blips visible immediately on auth pages.
- [ ] Smart upgrade indicator fires when a newer version exists in `meshpoint-channels.json` or via tag check.

### `.49` (fresh install)

- [ ] Auth pages render correctly with empty blip state.
- [ ] After first packet RX, blips populate.

## Failure modes to watch

- **Blips render at the same radius regardless of RSSI** — frontend ignoring `rssi_bin` field. Check `RealBlips._radiusFromRssi` mapping.
- **Endpoint returns 401** — accidentally added to `Depends(require_auth)`. Must be unauthenticated.
- **Rate limit easily bypassed by changing User-Agent** — limiter keying on UA, not IP. Switch to `request.client.host`.
- **Modal copy raw markdown** — server returning unparsed markdown; frontend should render via a small markdown-to-HTML helper or pre-render on the server.

## Acceptance summary

- [ ] Real blips pass on `.141`.
- [ ] Empty blip state pass on `.49`.
- [ ] Smart upgrade indicator pass on `.141`.
- [ ] Sign-off matrix updated.
