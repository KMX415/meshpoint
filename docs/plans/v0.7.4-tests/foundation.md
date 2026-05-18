# Foundation — Sidebar nav, IA refactor, map zero-scrollbar

Foundational chrome for v0.7.4. Lands Week 1 because every other feature renders inside it. Covered here:

- Sidebar navigation refactor (desktop full / tablet icon-only / mobile drawer)
- Information architecture refactor (Configuration as top-level; Radio observational; Settings shrunk to operational)
- Map zero-scrollbar invariant (Leaflet zoom transitions never flash scrollbars)
- Stats card row scrollbar contained
- Audit log emission infrastructure (used by everything downstream)

## 1. Sidebar — desktop layout (>= 1024px)

**Status:** [ ] Not started  [ ] In progress  [ ] Pass  [ ] Blocked
**Hardware:** `.141` and `.15`, browser at 1440px width
**Pre-conditions:**
- Service running v0.7.4 RC
- Logged in as admin (cookie present)

### Functional walkthrough

1. [ ] Open `http://<dashboard-host>:8080` (e.g. via the `.141` unit's hostname or LAN address). Expected: sidebar renders on the left at ~240px wide, persistent, content fills the right pane.
2. [ ] Header of the sidebar shows: Meshpoint logo, device name (`Meshpoint-RAKv2-...`), status pill ("online · v0.7.4").
3. [ ] Primary items visible in order: Dashboard, Stats, Messages, Radio, Terminal.
4. [ ] Configuration group (expandable) sits below Terminal, default state collapsed.
5. [ ] Settings group (expandable) sits below Configuration, default state collapsed.
6. [ ] Footer of the sidebar shows: role pill ("admin: kurt"), sign-out button.
7. [ ] Click Configuration. Expected: chevron rotates 180ms, group expands to reveal Identity, Radio, Channels, Transmit, MQTT, GPS subsections.
8. [ ] Click an item (e.g. Stats). Expected: 2px vertical mint accent bar slides from the previous active item to the new one (FLIP), URL updates to `#/stats`, content cross-fades 220ms.
9. [ ] Browser back button. Expected: previous section reactivates, accent bar slides back.
10. [ ] Browser forward button. Expected: forward navigation re-applies.
11. [ ] Direct-link `http://<dashboard-host>:8080/#/configuration/channels`. Expected: dashboard loads with Configuration group expanded, Channels active.

### Status badges

12. [ ] Send a Meshtastic DM to the Meshpoint from another node. Expected: Messages item shows unread badge counter increment within 1s.
13. [ ] During the next NodeInfo broadcast countdown, Radio item shows a pill like "TX 30s" updating live.
14. [ ] When `update_check` reports an available update, Settings group's Updates subsection shows an amber "1 available" pill.

### Acceptance

- [ ] All steps pass on `.141`.
- [ ] All steps pass on `.15`.
- [ ] Sidebar viewport sweep verified at 1440px / 1024px / 375px.

## 2. Sidebar — tablet layout (768-1023px)

**Status:** [ ] Not started  [ ] In progress  [ ] Pass  [ ] Blocked
**Hardware:** browser at 1024px width

### Functional walkthrough

1. [ ] Resize browser to 1024px width. Expected: sidebar collapses to icon-only rail at ~64px wide.
2. [ ] Hover any sidebar icon. Expected: tooltip appears after 400ms with the section name.
3. [ ] Click the rail's expand toggle (or hover the rail with the right modifier). Expected: rail expands to full sidebar.
4. [ ] Click outside the expanded sidebar. Expected: rail collapses back to icon-only.
5. [ ] Refresh the page. Expected: rail starts in icon-only mode (default for this viewport) unless localStorage preference says otherwise.
6. [ ] Set localStorage preference to "expanded" via the toggle. Refresh. Expected: rail starts expanded.

### Acceptance

- [ ] All steps pass.

## 3. Sidebar — mobile layout (< 768px)

**Status:** [ ] Not started  [ ] In progress  [ ] Pass  [ ] Blocked
**Hardware:** real phone (iOS Safari + Android Chrome) on local network, plus Playwright at iPhone 14 Pro and Galaxy S24 viewports

### Functional walkthrough

1. [ ] Open dashboard on phone. Expected: sidebar hidden, hamburger button visible in topbar.
2. [ ] Tap hamburger. Expected: drawer slides in from the left with backdrop dim, 220ms transition.
3. [ ] Tap a sidebar item. Expected: drawer closes, content navigates.
4. [ ] Tap hamburger, then tap backdrop (outside drawer). Expected: drawer closes without navigating.
5. [ ] Rotate phone to landscape. Expected: layout adapts cleanly, no overflow, drawer behavior preserved.

### Acceptance

- [ ] All steps pass on a real phone.
- [ ] All steps pass via Playwright on both iPhone 14 Pro and Galaxy S24 viewports.

## 4. Sidebar — keyboard navigation

**Status:** [ ] Not started  [ ] In progress  [ ] Pass  [ ] Blocked
**Hardware:** browser-only

### Functional walkthrough

1. [ ] Press Tab from page load. Expected: focus lands on the first sidebar item with a visible mint focus ring.
2. [ ] Arrow Down. Expected: focus moves to next item.
3. [ ] Arrow Right on Configuration group. Expected: group expands.
4. [ ] Arrow Down inside expanded group. Expected: focus moves between subsections.
5. [ ] Enter on a focused item. Expected: navigation occurs.
6. [ ] Press `g d`. Expected: navigates to Dashboard (Linear-style shortcut).
7. [ ] Press `g s`. Expected: navigates to Stats.
8. [ ] Press `g t`. Expected: navigates to Terminal (admin only; no-op for viewer).

### Acceptance

- [ ] All keyboard interactions work without mouse.
- [ ] Focus is never trapped or lost.

## 5. IA refactor — Configuration is its own top-level

**Status:** [ ] Not started  [ ] In progress  [ ] Pass  [ ] Blocked
**Hardware:** `.141` and `.15`

### Functional walkthrough

1. [ ] Sidebar shows Configuration as a top-level group with subsections: Identity, Radio, Channels, Transmit, MQTT, GPS.
2. [ ] Settings group shows only operational subsections: Updates, Auth, Dangerous (admin only).
3. [ ] Radio top-level item still exists but is observational only.
4. [ ] Open Radio. Expected: status panels (signal levels, current preset readback, NodeInfo countdown badge, channel table read-only, RF activity, duty-cycle gauge, status lamps). No Save buttons. No editable inputs.
5. [ ] Open Configuration > Radio. Expected: editable region selector, custom frequency, preset chips, NodeInfo card with preset chips + Save + Send Now.
6. [ ] Open Configuration > Channels. Expected: PSK list with masked keys, Add channel form.

### Negative paths

- [ ] Radio top-level page contains no Save buttons (verified via Playwright `tests/playwright/test_radio_tab_observational.py`).
- [ ] No editable input element in `#tab-radio`.

### Acceptance

- [ ] Status / Configuration / Settings trichotomy is intuitive on `.141` and `.15`.

## 6. Map zero-scrollbar invariant

**Status:** [ ] Not started  [ ] In progress  [ ] Pass  [ ] Blocked
**Hardware:** `.141` and `.15`, browser at 1024px / 1280px / 1920px widths

### Functional walkthrough

1. [ ] Open Dashboard at 1024px width. Expected: no scrollbars anywhere on the page.
2. [ ] Zoom the map from level 13 to level 4 (continent view) using the scroll wheel. Expected: no scrollbars flash at any frame.
3. [ ] Zoom from level 4 to level 13 using the +/- buttons. Expected: no scrollbars flash at any frame.
4. [ ] Pan the map by drag. Expected: no scrollbars flash.
5. [ ] Resize the browser between 1024px and 1920px while the map is rendered. Expected: no scrollbars at any width.
6. [ ] Repeat steps 1-5 at 1280px and 1920px widths.

### Negative paths

- [ ] If a scrollbar appears at any frame during zoom, the regression is real and must be fixed before any other work continues.

### Acceptance

- [ ] All viewport widths and zoom transitions clean.
- [ ] `tests/playwright/test_dashboard_no_scrollbars.py` passes.

## 7. Stats card row scrollbar containment

**Status:** [ ] Not started  [ ] In progress  [ ] Pass  [ ] Blocked
**Hardware:** browser at 1024px and 768px widths

### Functional walkthrough

1. [ ] Resize browser to 1024px. Expected: stats card row has horizontal overflow with a scoped thin scrollbar inside its container.
2. [ ] Scroll the stats row horizontally. Expected: scrollbar moves inside the card row only, never reaches the viewport edge.
3. [ ] Resize to 1920px. Expected: stats row fits without overflow, no scrollbar.

### Acceptance

- [ ] Horizontal scrollbar never bleeds out of the stats container.

## 8. Audit log emission infrastructure

**Status:** [ ] Not started  [x] In progress  [ ] Pass  [ ] Blocked
**Hardware:** `.141`

### Functional walkthrough

1. [ ] SSH to `.141`, run `sudo tail -F /opt/meshpoint/data/admin_audit.jsonl`.
2. [ ] In dashboard, change the admin password. Expected: one row appears with `action: "password_change"`, `result: "success"`.
3. [ ] Sign out everywhere. Expected: one row with `action: "logout_all"`.
4. [ ] Switch release channel from `main` to `dev`. Expected: one row with `action: "channel_switch"`, `params: {from: "main", to: "dev"}`.
5. [ ] Run a terminal command (e.g. `echo hello`). Expected: one row with `action: "terminal_command"`, `params: {command: "echo hello"}`.
6. [ ] Restart the service from Dangerous. Expected: one row with `action: "restart_service"`.

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
