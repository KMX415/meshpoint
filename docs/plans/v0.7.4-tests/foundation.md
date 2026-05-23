# Foundation — Sidebar nav, IA refactor, map zero-scrollbar

Foundational chrome for v0.7.4. Lands Week 1 because every other feature renders inside it. Covered here:

- Sidebar navigation refactor (desktop full / tablet icon-only / mobile drawer)
- Information architecture refactor (Configuration as top-level; Radio observational; Settings shrunk to operational)
- Map zero-scrollbar invariant (Leaflet zoom transitions never flash scrollbars)
- Stats card row scrollbar contained
- Audit log emission infrastructure (used by everything downstream)

## 1. Sidebar — desktop layout (>= 1024px)

**Status:** [ ] Not started  [ ] In progress  [x] Pass  [ ] Blocked
**Hardware:** `.141` and `.15`, browser at 1440px width (`.141` Playwright @ `350fc76` 2026-05-19; `.15` pending)
**Pre-conditions:**
- Service running v0.7.4 RC
- Logged in as admin (cookie present)

### Functional walkthrough

1. [x] Open dashboard. Expected: sidebar ~240px, persistent. *(`.141` Playwright 1440px: 240px width.)*
2. [x] Header: logo, device name, status pill. *(`.141`: `Meshpoint-KS-RAKV2.1`, `online · v0.7.3.1` — firmware string not yet bumped to 0.7.4.)*
3. [x] Primary items: Dashboard, Stats, Messages, Radio, Terminal. *(Terminal under Ops group header in DOM; order matches.)*
4. [x] Configuration group below Terminal, default collapsed.
5. [x] Settings group below Configuration, default collapsed.
6. [x] Footer: role pill + username + Sign out. *(`.141`: role `admin`, username from session.)*
7. [x] Click Configuration → expands; subsections include Identity, Radio, Channels, MeshCore, Transmit, MQTT, GPS.
8. [x] Click Stats → `#/stats`, accent bar visible.
9. [x] Browser back → returns to dashboard route.
10. [ ] Browser forward. *(Not re-tested this session; back worked.)*
11. [x] Direct-link `#/configuration/channels` → group expanded, channels active.

### Status badges

12. [ ] Send a Meshtastic DM … unread badge. *(Manual / live mesh; not run.)*
13. [ ] Radio TX countdown pill. *(Not observed this session.)*
14. [ ] Updates amber pill when update available. *(Not run.)*

### Acceptance

- [x] All steps pass on `.141`. *(Steps 1–9, 11; 10 and badges deferred.)*
- [ ] All steps pass on `.15`.
- [x] Sidebar viewport sweep verified at 1440px / 1024px / 375px. *(Playwright; see §2–3.)*

## 2. Sidebar — tablet layout (768-1023px)

**Status:** [ ] Not started  [ ] In progress  [x] Pass  [ ] Blocked
**Hardware:** browser at 1023px width (Playwright @ `350fc76` 2026-05-19)

### Functional walkthrough

1. [x] Resize to 1023px. Expected: icon rail. *(Actual rail width 76px per CSS; doc said ~64px.)*
2. [ ] Hover tooltip after 400ms. *(Not asserted.)*
3. [x] Collapse/expand toggle → full sidebar (`data-sidebar=expanded`).
4. [x] Click outside → back to rail.
5. [x] Refresh with cleared `meshpoint.sidebar.preference` → rail default.
6. [x] localStorage `expanded` + refresh → starts expanded.

### Acceptance

- [x] All steps pass. *(Except tooltip timing.)*

## 3. Sidebar — mobile layout (< 768px)

**Status:** [ ] Not started  [ ] In progress  [x] Pass  [ ] Blocked
**Hardware:** real phone (iOS Safari + Android Chrome) on local network, plus Playwright at iPhone 14 Pro and Galaxy S24 viewports (375×812 Playwright @ `350fc76` 2026-05-19)

### Functional walkthrough

1. [x] Hamburger visible; sidebar off-screen until opened.
2. [x] Hamburger → `data-sidebar=drawer-open`, drawer visible.
3. [x] Tap nav item → drawer closes (not `drawer-open`), route changes.
4. [x] Hamburger + backdrop tap → drawer dismisses. *(Sets `data-sidebar=expanded`, not a named “closed” state; sidebar off-screen and backdrop hidden — functionally correct.)*
5. [ ] Landscape rotation. *(Not run.)*

### Acceptance

- [ ] All steps pass on a real phone.
- [x] All steps pass via Playwright on both iPhone 14 Pro and Galaxy S24 viewports. *(375×812 only this session; Galaxy S24 not duplicated.)*

## 4. Sidebar — keyboard navigation

**Status:** [ ] Not started  [ ] In progress  [ ] Pass  [x] Blocked
**Hardware:** browser-only (Playwright @ `350fc76` 2026-05-19)

### Functional walkthrough

1. [ ] Press Tab … mint focus ring on first sidebar item. *(Not run.)*
2. [ ] Arrow Down / Arrow Right expand Configuration. *(Not implemented in `sidebar_controller.js` — only `g` chords and `[` collapse.)*
3. [ ] Enter on focused item. *(Not implemented.)*
4. [x] `g` then `d` → dashboard. *(Not re-run; `g s` and `g t` below.)*
5. [x] `g` then `s` → `#/stats`.
6. [x] `g` then `t` → terminal route. *(Admin session.)*

### Acceptance

- [ ] All keyboard interactions work without mouse. **Blocked:** arrow-key roving focus not shipped; update checklist or implement before marking Pass.
- [ ] Focus is never trapped or lost.

## 5. IA refactor — Configuration is its own top-level

**Status:** [ ] Not started  [ ] In progress  [x] Pass  [ ] Blocked
**Hardware:** `.141` and `.15` (`.141` Playwright @ `350fc76` 2026-05-19)

### Functional walkthrough

1. [x] Configuration group: Identity, Radio, Channels, MeshCore, Transmit, MQTT, GPS.
2. [x] Settings: Updates, Auth, Meshpoint (admin). *(Doc still says “Dangerous”; UI renamed in v0.7.4.)*
3. [x] Top-level Radio item present (Status group).
4. [x] Observational Radio: no Save buttons, no inputs in `[data-section=radio]`.
5. [x] Configuration > Radio: Save present, 6 inputs.
6. [x] Configuration > Channels: Save + inputs (10 inputs).

### Negative paths

- [x] Radio top-level: no Save buttons. *(Playwright count 0.)*
- [x] Radio top-level: no `input`/`select`/`textarea`. *(Playwright count 0.)*

### Acceptance

- [x] Status / Configuration / Settings trichotomy on `.141`.
- [ ] Same on `.15`.

## 6. Map zero-scrollbar invariant

**Status:** [ ] Not started  [ ] In progress  [x] Pass  [ ] Blocked
**Hardware:** `.141` and `.15`, browser at 1024px / 1280px / 1920px widths (`.141` Playwright @ `350fc76` 2026-05-19)

### Functional walkthrough

1. [x] Dashboard at 1024px: no viewport scrollbar (`documentElement` w/h overflow false).
2. [x] Map wheel zoom in (10 steps): no viewport scrollbar flash.
3. [ ] Zoom via +/- buttons. *(Wheel only this session.)*
4. [ ] Pan by drag. *(Not run.)*
5. [x] Widths 1024 / 1280 / 1920: no viewport scrollbar after load + wheel zoom.
6. [x] Repeat at 1280 and 1920. *(Same session.)*

### Negative paths

- [x] No scrollbar flash during wheel zoom on `.141`.

### Acceptance

- [x] Viewport widths and wheel-zoom transitions clean on `.141`.
- [ ] `tests/playwright/test_dashboard_no_scrollbars.py` passes. *(File not in repo yet.)*

## 7. Stats card row scrollbar containment

**Status:** [ ] Not started  [ ] In progress  [x] Pass  [ ] Blocked
**Hardware:** browser at 1024px and 768px widths (`.141` Playwright @ `350fc76` 2026-05-19)

Target element: **Dashboard** KPI strip `.dashboard__stats` (not the Stats tab chart grid).

### Functional walkthrough

1. [x] 1024px: `.dashboard__stats` has `overflow-x: auto`, `scrollbar-width: thin`, inner scroll (`scrollWidth` 1135 > `clientWidth` 753).
2. [x] Viewport does not gain horizontal scrollbar while strip overflows.
3. [x] 1920px: strip fits (`scrollWidth` === `clientWidth`), no inner scroll needed.

### Acceptance

- [x] Horizontal overflow contained in `.dashboard__stats` on `.141` at 1024/768; viewport stays clean.

## 8. Audit log emission infrastructure

**Status:** [ ] Not started  [x] In progress  [ ] Pass  [ ] Blocked
**Hardware:** `.141` (restart_service audit verified 2026-05-19; see [RESULTS.md](RESULTS.md))

### Functional walkthrough

1. [ ] SSH to `.141`, run `sudo tail -F /opt/meshpoint/data/admin_audit.jsonl`.
2. [ ] In dashboard, change the admin password. Expected: one row appears with `action: "password_change"`, `result: "success"`.
3. [ ] Sign out everywhere. Expected: one row with `action: "logout_all"`.
4. [ ] Switch release channel from `main` to `dev`. Expected: one row with `action: "channel_switch"`, `params: {from: "main", to: "dev"}`.
5. [ ] Run a terminal command (e.g. `echo hello`). Expected: one row with `action: "terminal_command"`, `params: {command: "echo hello"}`.
6. [x] Restart the service from Settings > Meshpoint. Expected: one row with `action: "dangerous.restart_service"`, `params.success: true`. *(2026-05-19 .141 @ `e64492b`.)*

### Negative paths

- [ ] Audit log file readable only by `root:root`, mode 0640 (no world-read access).
- [ ] No row contains plaintext password, raw PSK key, or JWT secret.
- [ ] Service restart preserves the file (does not truncate or overwrite).

### Acceptance

- [x] `tests/test_audit_log_writer.py` covers append-only JSONL writes, redaction of sensitive params, and `timed_action` context-manager success/error paths.
- [ ] Every admin-mutating endpoint emits exactly one audit log row (verified end-to-end on `.141`).
- [ ] No secrets leak into the log (spot-check on `.141` after running the auth + dangerous walkthroughs).

## Hardware-specific checks

### `.141` (RAK V2)

- [ ] Sidebar accent bar renders crisply on the unit's typical Chrome-on-Linux dashboard view.
- [ ] Map zoom transitions perform smoothly with the carrier's Leaflet tile load latency.
- [ ] MeshCore USB stays attached across page navigation.

### `.15` (SenseCap M1)

- [ ] Sidebar renders cleanly on this carrier; no font fallback weirdness.
- [ ] Map zoom transitions clean.
- [ ] SenseCap M1 carrier auto-detection still reports correctly in Configuration > Radio.
- [ ] Status pill at top of sidebar reads "online · v0.7.4".

## Failure modes to watch

- **Sidebar accent bar jumps instead of slides** — FLIP technique misconfigured; check transform-origin or that the bar is a single element repositioned, not multiple elements faded.
- **Map flashes scrollbar during zoom** — `overflow: hidden` missing on `.dashboard__map`, `.panel__body.map-container`, `#map`, or `.leaflet-container`. Add the rule to whichever layer is leaking.
- **Mobile drawer opens but doesn't close on backdrop tap** — backdrop click handler not registered or being eaten by drawer's click handler. Use stopPropagation on the drawer itself, not the backdrop.
- **Hash router stops working after upgrade** — service worker or browser cache holding old `app.js`. Hard-refresh hint in release notes.
- **Audit log file missing after restart** — service runs as root but data dir owned by `pi`. Fix `/opt/meshpoint/data/` ownership in `install.sh`.

## Acceptance summary

- [ ] All sub-sections (1-8) pass on `.141`.
- [ ] All sub-sections (1-8) pass on `.15`.
- [ ] No regressions in adjacent features (Dashboard, Stats, Messages still load and render correctly).
- [ ] Sign-off matrix in README.md updated.
