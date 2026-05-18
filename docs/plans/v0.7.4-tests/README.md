# v0.7.4 — Test Checklist

Click-by-click test checklist for the v0.7.4 release. Files in this directory live alongside the features they cover. Boxes get ticked as features land, not pre-filled speculatively.

This file is the master index. It carries the cross-cutting checks (audit log, role guards, design polish, accessibility) that span every feature, plus the sign-off matrix that gates the release.

## Sign-off matrix

One row per feature, one column per hardware unit. Box gets checked when the per-feature file is fully green for that unit. Anything red blocks the release.

| Feature                          | .141 (RAK V2) | .15 (SenseCap M1) | .49 (fresh SD) | Browser-only |
|----------------------------------|---------------|-------------------|----------------|--------------|
| Sidebar nav + IA refactor        | [ ]           | [ ]               | [ ]            | [ ]          |
| Map zero-scrollbar invariant     | [ ]           | [ ]               | n/a            | [ ]          |
| Audit log emission               | [ ]           | [ ]               | n/a            | n/a          |
| Password change                  | [ ]           | [ ]               | [ ]            | [ ]          |
| Sign-out-everywhere              | [ ]           | [ ]               | n/a            | [ ]          |
| Configurable lockout             | [ ]           | [ ]               | n/a            | [ ]          |
| Viewer role end-to-end           | [ ]           | [ ]               | n/a            | [ ]          |
| Web terminal                     | [ ]           | [ ]               | n/a            | [ ]          |
| Update apply + branch picker     | [ ]           | [ ]               | n/a            | n/a          |
| Watchdog auto-rollback           | [ ]           | [ ]               | n/a            | n/a          |
| Configuration > Identity         | [ ]           | [ ]               | n/a            | [ ]          |
| Configuration > Radio            | [ ]           | [ ]               | n/a            | [ ]          |
| Configuration > Channels         | [ ]           | [ ]               | n/a            | [ ]          |
| Configuration > Transmit         | [ ]           | [ ]               | n/a            | [ ]          |
| Configuration > MQTT             | [ ]           | [ ]               | n/a            | [ ]          |
| Configuration > GPS              | [ ]           | [ ]               | n/a            | [ ]          |
| Dangerous actions                | [ ]           | [ ]               | n/a            | n/a          |
| Real radar blips on auth pages   | [ ]           | [ ]               | [ ]            | [ ]          |
| Smart upgrade indicator          | [ ]           | [ ]               | n/a            | [ ]          |
| MQTT hierarchical paths (PR #35) | [ ]           | [ ]               | n/a            | n/a          |
| MeshCore Channel Config (otto)   | [ ]           | [ ]               | n/a            | [ ]          |
| MeshCore map fix (PR #51)        | [ ]           | [ ]               | n/a            | [ ]          |
| Native relay (onboard SX1302)    | [x] .141      | [ ]               | n/a            | n/a          |
| Spectral-scan noise floor        | [ ]           | [ ]               | n/a            | [ ]          |

## Per-feature template

Every entry in the per-feature files follows this template:

- **Status** — Not started / In progress / Pass / Blocked
- **Hardware** — `.141` / `.15` / `.49` / browser-only
- **Pre-conditions** — what must be true before running the steps
- **Functional walkthrough** — numbered click-by-click steps with one expected result per step
- **Negative paths** — auth gates (anonymous 401, viewer 403, admin 200), malformed payloads, concurrent invocation, server restart mid-action
- **Hardware-specific checks** — anything that differs between `.141` and `.15`
- **Failure modes to watch** — symptoms that signal a regression and what they likely mean
- **Acceptance** — final checkboxes that gate the feature

## Cross-cutting checks (apply to every feature)

These are deliberately listed once here rather than duplicated in each file. Each per-feature checklist references this section.

### Audit log emission

For every admin-mutating endpoint:

- [ ] During the feature walkthrough, run `tail -F /opt/meshpoint/data/admin_audit.jsonl` in another terminal.
- [ ] Each click that mutates state writes exactly one row.
- [ ] Each row has `ts`, `user`, `action`, `params`, `result`, `duration_ms`.
- [ ] `user` matches the logged-in admin's username.
- [ ] `action` matches the endpoint that was hit.
- [ ] `result` is `success` for happy paths, `error` with a populated `error` field for failures.
- [ ] No audit entries leak secrets (passwords, raw PSK keys, JWT secret, etc).

### Role guard 3-case

For every protected endpoint:

- [ ] Anonymous (no cookie) -> HTTP 401 with `{"detail":"Authentication required"}`.
- [ ] Viewer cookie -> HTTP 403 with `{"detail":"Admin access required"}` if admin-only; HTTP 200 if viewer-allowed.
- [ ] Admin cookie -> HTTP 200 with the expected payload.

### WebSocket handshake invariant

For every authenticated WS endpoint:

- [ ] Anonymous WS handshake -> server calls `accept()` then `close(code=4401)`. Client receives close code 4401 (not 1006).
- [ ] Bad cookie WS handshake -> same: 4401 reaches the browser.
- [ ] Verified via `tests/test_websocket_auth_close_code.py`.

### Map zero-scrollbar invariant

- [ ] At desktop (1440px), tablet (1024px), and phone (375px) widths, no horizontal or vertical scrollbar appears anywhere on the dashboard.
- [ ] Zoom the map from level 13 down to level 4 with smooth transitions enabled. No scrollbars appear at any frame.
- [ ] Zoom the map from level 4 up to level 13. No scrollbars appear at any frame.
- [ ] Stats card row scrolls horizontally inside its container (if narrow enough), but the scrollbar does not bleed to the viewport edge.
- [ ] Verified via `tests/playwright/test_dashboard_no_scrollbars.py`.

### Design polish acceptance

For every feature:

- [ ] Hover states present on every clickable element (button, link, sidebar item, list row).
- [ ] Focus rings visible and accessible (mint-teal accent ring, not just a default browser dotted outline).
- [ ] Transitions feel snappy not laggy. Most under 220ms. Easing matches the locked default `cubic-bezier(0.16, 1, 0.3, 1)`.
- [ ] Empty states designed, not blank. Glyph + headline + action hint.
- [ ] Loading states use skeleton placeholders for >300ms loads. No generic spinners except for known long operations (update apply, terminal command running).
- [ ] Time formatting uses the shared `formatTime` helper (relative recent + absolute old + ISO tooltip).
- [ ] Number formatting uses the shared `formatNumber` helper (locale separators, units suffixed where space-tight).
- [ ] Pluralization correct ("1 node" vs "2 nodes").
- [ ] Status pills carry both color and icon (colorblind-safe).
- [ ] `prefers-reduced-motion` flips animations to instant state changes.

### WCAG AA contrast audit

For every page:

- [ ] axe-core in Playwright reports zero violations.
- [ ] Body text contrast >= 4.5:1.
- [ ] Large text (>= 18pt or 14pt bold) and UI component contrast >= 3:1.
- [ ] All icon-only buttons have screen-reader labels.
- [ ] All form fields have associated labels.

### DevTools console clean

- [ ] After any feature walkthrough, browser console shows zero errors and zero warnings (network, JavaScript, CSP, deprecation).

### Hard-refresh resilience

For every page:

- [ ] Ctrl+Shift+R (or Cmd+Shift+R on macOS) reloads the page without breaking.
- [ ] State that should persist (logged-in session, sidebar collapsed/expanded preference) survives.
- [ ] State that should not persist (terminal scrollback, transient form input) is cleared.

### Browser matrix spot-check

Pick one feature per browser and verify the sidebar drawer plus that feature works:

- [ ] Chrome (latest).
- [ ] Firefox (latest).
- [ ] Safari (latest macOS).
- [ ] iOS Safari (iPhone 14 Pro viewport).
- [ ] Android Chrome (Galaxy S24 viewport).

### Design audit (Week 4)

Single deliverable: a screen recording of an admin walking through the entire dashboard end-to-end on `.141` at desktop width, then on a phone, with no narration.

- [ ] Recording captured at desktop width.
- [ ] Recording captured at phone width.
- [ ] Reviewed end-to-end. Anything that makes us cringe gets a fix-before-tag entry.
- [ ] Recording uploaded as a release asset on the v0.7.4 GitHub release.

## Per-feature files

- [foundation.md](foundation.md) — sidebar navigation refactor, IA refactor, map zero-scrollbar
- [auth.md](auth.md) — password change, viewer role, sign-out-everywhere, configurable lockout
- [terminal.md](terminal.md) — PTY session, command guide drawer, irreversibles confirmation
- [updates.md](updates.md) — update apply, branch picker, watchdog rollback
- [configuration.md](configuration.md) — Identity, Radio, Channels, Transmit, MQTT, GPS
- [dangerous.md](dangerous.md) — restart, clear DB, wipe phantoms, force NodeInfo, restart concentrator
- [cherry-picks.md](cherry-picks.md) — MQTT hierarchical paths, MeshCore Channel Config, PR #51 map fix
- [polish.md](polish.md) — real radar blips on auth pages, smart upgrade indicator
- [relay.md](relay.md) — native onboard SX1302 relay (identity-preserving)
- [spectral_scan.md](spectral_scan.md) — SX1302 spectral scan noise floor

## Pre-release gate

Before tagging v0.7.4:

- [ ] Sign-off matrix above shows green in every cell that has a checkbox.
- [ ] Every per-feature file shows fully-green acceptance for `.141` and `.15`.
- [ ] `.49` fresh-SD install green for foundation + auth + fresh-install acceptance steps.
- [ ] Design audit recording captured and reviewed.
- [ ] WCAG AA contrast audit clean.
- [ ] CHANGELOG entry written, calls out IA refactor + navigation change + design polish pass.
- [ ] Version bumped in `src/version.py` and `firmware_version` in `config/default.yaml`.

Anything red here blocks the release.
