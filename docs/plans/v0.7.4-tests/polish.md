# Polish — Real radar blips, smart upgrade indicator

Cosmetic and informational polish that completes the v0.7.4 story.

## 1. Real radar blips on /login and /setup

**Status:** [ ] Not started  [ ] In progress  [ ] Pass  [ ] Blocked
**Hardware:** `.141` (active mesh traffic) and `.49` (fresh install, no traffic yet)

### Functional walkthrough on `.141` (active traffic)

1. [ ] Open `/login` in a private window on `.141`.
2. [ ] Wait for the radar to render with the rotating cyan sweep.
3. [ ] Within 5-10 seconds, real RX-driven blips begin appearing on the radar disc. Each blip:
       - Renders at radius proportional to RSSI (closer to center = stronger signal).
       - Angle randomized (we do not have AoA data).
       - Pings out as a 1.5s expanding ring fading as it grows.
       - Disappears after the ping completes.
4. [ ] Blip frequency tracks roughly with the actual RX rate from the concentrator (verify via `meshpoint status` or `journalctl`).
5. [ ] Open `/setup` (logged out, fresh device path). Same blip behavior visible.

### Functional walkthrough on `.49` (no traffic yet)

6. [ ] Fresh install, dashboard at `/setup`. Radar shows the rotating sweep, no blips yet (because no RX events).
7. [ ] After completing setup and waiting for at least one packet to be received, blips begin appearing on subsequent visits to `/login`.

### Endpoint security

8. [ ] `GET /api/public/recent_rx` is intentionally unauthenticated (no cookie required).
9. [ ] Response payload shape:
       ```json
       {"events": [{"ts": "2026-05-14T19:12:30Z", "rssi_bin": -67, "channel_idx": 3}, ...]}
       ```
10. [ ] No node IDs, no source addresses, no decoded content.
11. [ ] Rate-limited to 1 req/s/IP. Hit it 5 times rapidly: expect a 429 with Retry-After.

### Negative paths

- [ ] Endpoint never returns more than the last 10 events.
- [ ] If concentrator is down (no RX history), endpoint returns `{"events": []}` not 500.

### Acceptance

- [ ] Real blips visible on `.141`.
- [ ] Endpoint scrubbed correctly.
- [ ] Rate-limit enforced.
- [ ] `tests/test_public_recent_rx.py` covers payload + rate-limit.

## 2. Smart upgrade indicator

**Status:** [ ] Not started  [ ] In progress  [ ] Pass  [ ] Blocked
**Hardware:** `.141`

### Functional walkthrough

1. [ ] On `.141` running an older v0.7.4 RC, an update_check fires (manual trigger or scheduled).
2. [ ] When a newer version is available, the topbar update indicator activates (orange triangle, established UX).
3. [ ] Click the indicator. Expected: modal opens.
4. [ ] Modal copy is **NOT** generic ("A new version is available, please upgrade") -- instead it reads the v0.7.4 (or whatever target) entry from `docs/CHANGELOG.md` and renders the bullet highlights.
5. [ ] Modal title: "Meshpoint vX.Y.Z available" with current version below.
6. [ ] Modal body: bullet list of headline items from CHANGELOG entry (truncated to 5-6 bullets if longer, with "Read more on GitHub" link).
7. [ ] Modal actions: "Maybe later" and "Open Update Settings" (which navigates to Settings > Updates).

### Negative paths

- [ ] If CHANGELOG entry is unreachable (e.g. offline), modal falls back to generic copy.
- [ ] Modal does not auto-open; only on indicator click.

### Acceptance

- [ ] Modal copy is changelog-aware.
- [ ] Fallback works.
- [ ] Pass on `.141`.

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
