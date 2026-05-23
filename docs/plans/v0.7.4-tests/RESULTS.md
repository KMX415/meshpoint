# v0.7.4 — Test results log

Append-only record of hardware and browser validation runs. **Ship gate:** every cell in [README.md](README.md) sign-off matrix must be `[x]` (full pass for that feature × column) before tagging `v0.7.4`. Partial passes stay here and in per-feature **Status** lines until the checklist is fully green.

## Agent handoff (read before "what's next")

**RC branch:** `feat/v0.7.4` (Pi: Settings → Updates → RC, or `git checkout feat/v0.7.4`). **Do not version-bump until the sign-off matrix is green.**

### Already on the RC (inherited from `main`, not v0.7.4-only work)

| Item | Where it landed | Do not re-queue as "next release" |
|------|-----------------|-----------------------------------|
| Phantom `STAT_NO_CRC` + `hop_limit > hop_start` | **v0.7.3** (`dcf4643` on `main`) | Validated fleet-side in v0.7.3; branch `fix/no-crc-phantom-leak` is redundant |
| MeshCore USB decode path | **`main`** (`coordinator` → `adapt_event`) | Backlog item "wire packet_router" is stale for USB |
| v0.7.2 CRC_BAD drop, relay_node UI, PR #38 freq/slot, etc. | `main` | Same |

### Built / fixed on `feat/v0.7.4` this cycle (test these under v0.7.4 docs)

| Commit area | What | .141 status |
|-------------|------|-------------|
| Dashboard shell, auth, terminal, updates UI | Sidebar IA, Settings, Configuration editors, smoke script | partial (see matrix) |
| `0fb4f4f` | MeshCore contact roster @ ~20s + full contact sync | **pass** (2026-05-20 logs: 15 peers, 11 rows updated) |
| `d934dbd` | Updates panel install branch / channel picker | partial (Apply works; use current HEAD) |
| `7fa894c` | Revert Apply stop/release-radio; fix lifespan `UnboundLocalError` | **pass** (service starts; Apply = git → install → restart) |
| `511e841`+ | MQTT `PUT /api/config/mqtt` | API smoke pass; matrix row still `[ ]` until UI walkthrough |
| Relay native, PR #54/#55, PR #53 MeshCore channels, etc. | See [cherry-picks.md](cherry-picks.md), [relay.md](relay.md) | mostly `[ ]` in matrix |

### Not v0.7.4 scope (separate bugs; do not block tag unless you choose to)

- Multi-protocol IF (`if=2 sf5`) → Meshtastic decoder with no USB companion (nopemesh finding)
- `PUT /api/config/gps` not implemented (GPS editor stub)
- Foundation §4 keyboard roving focus (blocked / not implemented)
- Watchdog auto-rollback on failed apply (deferred)

---

## How to log a run

| Field | What to write |
|-------|----------------|
| **Date** | UTC or local, ISO `YYYY-MM-DD` |
| **Unit** | `.141` (RAK V2), `.15` (SenseCap M1), `.49` (fresh SD), or `browser-only` |
| **Commit** | `git log -1 --oneline` on the Pi or `origin/feat/v0.7.4` SHA |
| **Feature** | Matches a README matrix row or `docs/plans/v0.7.4-tests/<file>.md` section |
| **Result** | `pass`, `partial`, `fail`, or `blocked` |
| **Tester** | Who ran it (human / agent session label) |
| **Notes** | What was exercised, evidence, blockers |

After a **pass** for an entire feature on a unit, tick the matching README matrix cell and set that section's **Status: Pass** in the feature file.

## Legend (sign-off matrix)

| Symbol in matrix | Meaning |
|------------------|---------|
| `[x]` | Full checklist green for that column |
| `partial` | Some steps pass; see RESULTS; **does not** satisfy ship gate |
| `[ ]` | Not started or not complete |
| `n/a` | Column does not apply |

---

## Log

| Date | Unit | Commit | Feature | Result | Tester | Notes |
|------|------|--------|---------|--------|--------|-------|
| 2026-05-19 | .141 | `e64492b` | Configuration > Transmit | partial | agent | Relay: `GET` exposes `transmit.relay`; `PUT` persists `max_relay_per_minute` to `relay:` in `local.yaml`; UI Save shows success; settings survive service restart. Not run: TX power change, relay off/on soak, duty slider walkthrough from configuration.md §4. |
| 2026-05-19 | .141 | `e64492b` | Dangerous > Restart service | pass | agent | `POST /api/dangerous/invoke` → `success: true`, message `service restart initiated` (detached systemctl). Audit `dangerous.restart_service` with `params.success: true`. UI Settings > Meshpoint: Confirm modal → inline `service restart initiated`. Fix: `e64492b` detached restart (was false failure when subprocess killed mid-wait). |
| 2026-05-19 | .141 | `e64492b` | Spectral scan §1 (packet-derived) | pass | agent | Default path: journal shows spectral scan disabled / packet-derived fallback; service stable; sidebar noise floor populates from RX (per spectral_scan.md status). §2–8 and browser §9 not run on this date. |
| 2026-05-19 | .141 | (prior) | Native relay (onboard SX1302) | pass | (prior session) | README matrix already `[x] .141`. See relay.md. |
| 2026-05-19 | .141 | `350fc76` | Foundation §1 desktop sidebar | pass | agent | Playwright 1440px @ `http://192.168.0.141:8080`. Steps 1–9, 11 green; status pill shows `v0.7.3.1`; badges 12–14 and browser-forward not run. |
| 2026-05-19 | .141 | `350fc76` | Foundation §2 tablet sidebar | pass | agent | 1023px rail ~76px; expand/collapse, click-outside, localStorage preference. Tooltips not timed. |
| 2026-05-19 | .141 | `350fc76` | Foundation §3 mobile sidebar | pass | agent | 375×812: hamburger, drawer-open, nav closes drawer, backdrop dismisses (state `expanded`). Real phone + landscape not run. |
| 2026-05-19 | .141 | `350fc76` | Foundation §4 keyboard nav | blocked | agent | `g`+`s`/`t` work; Tab/arrow roving focus not in `sidebar_controller.js`. Mark Pass only after implement or doc trim. |
| 2026-05-19 | .141 | `350fc76` | Foundation §5 IA refactor | pass | agent | Config vs Settings vs observational Radio verified; Settings subsection is Meshpoint not Dangerous. `.15` not run. |
| 2026-05-19 | browser-only | `350fc76` | Foundation §1–3 viewport sweep | partial | agent | 1440 / 1023 / 375 via Playwright on `.141` LAN; satisfies viewport sweep item in §1 acceptance except §4 blocker. |
| 2026-05-19 | .141 | `350fc76` | Foundation §6 map zero-scrollbar | pass | agent | Dashboard @ 1024/1280/1920: no `documentElement` overflow; 10× wheel zoom on map: no flash. +/- and pan not run. |
| 2026-05-19 | .141 | `350fc76` | Foundation §7 KPI strip scroll | pass | agent | `.dashboard__stats` `overflow-x:auto` + thin scrollbar; inner scroll at 1024/768; viewport never horizontal-scrolls; 1920 fits without inner scroll. |
| 2026-05-19 | .141 | `a3db4b5` | Configuration > MQTT / GPS | fail | agent | `PUT /api/config/mqtt` and `/api/config/gps` return **405** (routes not registered). `PUT /api/config/identity` returns **401** (route exists). Frontend `mqtt_card.js` / `gps_card.js` will always fail Save until backend added. MeshCore RSSI fix on this commit confirmed by user earlier. |
| 2026-05-19 | local | `a3db4b5` | pytest + smoke script | pass | agent | **672** tests pass. `scripts/smoke_v074_api.py` extended for transmit/radio/channels/nodeinfo/auth_settings/auth_lockout + MQTT/GPS probe (warns on 405). Live run needs `MESHPOINT_PASSWORD`. |
| 2026-05-19 | .141 | `511e841` | Full API smoke (`smoke_v074_api.py`) | pass | agent | Identity/transmit/radio/channels/nodeinfo/**mqtt** round-trip, auth_lockout bounds, dangerous (5), force_nodeinfo, wipe_phantoms, restart_concentrator. GPS PUT still skipped (not wired). |
| 2026-05-19 | .141 | `511e841` | Auth API (viewer E2E) | partial | agent | `POST /api/auth/setup_viewer` with `password` field → 200, viewer login OK, `dangerous.invoke` → 403, `GET /api/config` + `/api/nodes` → 200. Lockout PUT 422 for attempts=101 and cooldown=0. Browser §1 step 3 (wrong current password) redirects to `/login` (401 clears session — expected). Password change / logout_all UI not completed. |
| 2026-05-19 | .141 | `511e841` | Settings > Updates (browser) | partial | agent | Channel picker (Stable / RC v0.7.4 / Custom), local+remote 0.7.3.1, Apply + Rollback buttons visible. Apply not run (destructive). |
| 2026-05-19 | .141 | `511e841` | Web terminal (browser) | partial | agent | Terminal route via sidebar; Connect → status **CONNECTED**; xterm canvas present. `pwd`/`whoami` not typed; command guide `?` not exercised. `GET /api/terminal/commands` + `/status` → 200. |
| 2026-05-19 | .141 | `511e841` | Node online dots (browser) | fail | agent | All sampled cards `nc-online--off` despite node `c1871770` last_heard ~53m ago. Pi on `511e841` without local `node_cards.js` 2h-threshold fix; deploy pending. |
| 2026-05-19 | .141 | `67f0114` | Node online dot deploy | pass | agent | Pushed `67f0114` to `origin/feat/v0.7.4`. SSH from Cursor failed (no key). `POST /api/update/apply` channel `rc-074`: git fetch/checkout/pull to `67f0114` OK; reported `failed_step: restart service` but dashboard came back; `/js/node_cards.js` contains `ONLINE_THRESHOLD_MS`. API sim: nodes heard &lt;2h show online. |
| 2026-05-19 | .141 | `92b513b`+ | Tests 1–5 batch | partial | agent | **Terminal:** Connect → `connected`; xterm canvas does not expose `pwd`/`whoami` via DOM text; 13 commands catalog API OK. **Auth:** logout_all 204 + second session 401; lockout UI shows 5/5; identity API+UI save/revert OK. **Config:** identity PUT round-trip API; UI “Saved.” on Configuration → Identity. **Audit:** not tailed on Pi (no SSH); identity save should have emitted `config.identity` row. **Updates:** 3 channels, version check OK; apply rc-074 pulled `92b513b` CSS; dropdown fix `color-scheme: dark` on select in `/css/settings.css`. |
| 2026-05-20 | .141 | `92b513b`+local | Update apply detached restart | pass | agent | Patched `src/api/update/apply.py` on Pi via `/tmp` + `sudo cp`. `POST /api/update/apply` `rc-074` → `success: true`, `target_branch: feat/v0.7.4`. Audit: `update.apply` `result: success` (no `failed_step`). Fix still **uncommitted** on laptop; push before fleet relies on it. |
| 2026-05-20 | .141 | `92b513b`+ | Full API smoke (repeat) | pass | agent | `scripts/smoke_v074_api.py` all green: identity/transmit/radio/channels/nodeinfo/**mqtt** PUT, auth negatives, dangerous trio, relay shape. GPS PUT skipped (not wired). |
| 2026-05-20 | .141 | `92b513b`+ | Auth API logout_all | pass | agent | `POST /api/auth/logout_all` → 204; `GET /api/config` → 401; re-login → 200. Browser two-session UI not run. |
| 2026-05-20 | .141 | `92b513b`+ | Audit log (SSH) | partial | agent | `tail admin_audit.jsonl`: `update.apply` success, `auth.logout_all`, `dangerous.*`, `terminal.session_*`. Per-action audit during full feature walks not completed. |
| 2026-05-20 | .141 | `92b513b`+ | Node online on Pi | pass | agent | On-disk `ONLINE_THRESHOLD_MS` in `node_cards.js`; nodes API returns fresh `last_heard`. Dashboard green-dot re-check in browser not re-run this session. |
| 2026-05-20 | local | `d1a40d5`+ | pytest v0.7.4 routes | pass | agent | `test_update_apply` (5), auth/terminal/update routes (36), full suite green (679+). |
| 2026-05-20 | .141 | `7fa894c` | MeshCore contact startup sync | pass | human | After RC apply + restart: `0 peers` at boot, ~20s later 15 peers logged + 11 node rows enriched (`0fb4f4f`). |
| 2026-05-20 | .141 | `7fa894c` | Settings > Updates Apply | partial | human | `git fetch/checkout/reset/install` OK; SEGV during `install.sh` then systemd restart recovered (pre-`7fa894c` behavior). Dashboard back; lifespan crash from `8a9b01d` fixed by `7fa894c`. |
| 2026-05-20 | .141 | `7fa894c` | Service startup | pass | human | Post-`7fa894c` pull: no lifespan traceback; concentrator + MeshCore USB up. |
| 2026-05-18 | .141 | `feat/v0.7.4` | Auth Tier 1 A (browser) | pass | human | Settings → Auth: set new password (re-login works). Sign out everywhere clears all sessions. |
| 2026-05-18 | .141 | `feat/v0.7.4` | Configuration Tier 1 B (browser) | pass | human | Identity, Radio, Channels, MQTT, Transmit, GPS, MeshCore all exercised on `.141`. MeshCore action buttons misaligned (two separate `cfg-card__actions` rows); fix in `meshcore_card.js` + `.cfg-mc-toolbar` grid pending deploy. |

---

## Open blockers (ship)

| Feature | Unit | Blocker |
|---------|------|---------|
| Configuration > GPS | all | **Stale:** `PUT /api/config/gps` exists (`device_config_routes.py`); gpsd runtime still v0.7.5. Test static placement save in Tier 1 B. |
| Foundation §4 keyboard | all | Arrow-key roving focus not implemented; `g` chords only. Pass requires implement or trim checklist. |
| Foundation §1 badges | .141 | Steps 12–14 need live mesh / update-available state. |
| Foundation §3 | .141 | Real iOS/Android device + landscape not exercised. |
| Terminal §1 | .141 | CONNECTED; `pwd`/`whoami` in xterm + per-command audit not run. |
| Hardware parity | .15 / .49 | No full matrix rows this cycle. |
| Watchdog rollback | .141 | `updates.md` §4+ not exercised (feature deferred). |
| Ship gate | all | **No README matrix cell is full `[x]` yet**; cross-cutting design audit + axe not recorded. |

---

## 2026-05-22 — Agent major-gate automation (`.141`, `2a458e5`)

| Feature | Result | Tester | Notes |
|---------|--------|--------|-------|
| Foundation API + pytest | pass | agent | 706 passed; smoke all green (`SMOKE_SKIP_DANGEROUS=1`) |
| Auth A2–A4 | pass | agent | Wrong password 401; `testpassword` rotate + restore; dual-session `logout_all` |
| Configuration panels | pass/partial | agent | Playwright loads all cards; channels align; API round-trips in smoke |
| Updates C1 | pass | agent | `0.7.3.1` up to date on RC channel |
| Terminal D1–D2 | pass | agent | Connect `connected`; xterm headless garbled; shell OK |
| Dangerous B2 | pass | agent | `restart_service`; `Meshpoint RAK` identity persisted |
| Dashboard E1–E3 | pass/partial | agent | Map + `#packet-tbody`; MeshCore topbar name; 429 noise on rapid nav |
| MQTT journal B5 | pass | agent | Coordinator logs `MQTT disabled` (expected when off) |

Scripts: `scripts/_session_v074_runner.py`, `_session_v074_playwright.py`, `_session_v074_auth_flow.py`, `_session_v074_continue.py`. Live step table: [SESSION-LOG.md](SESSION-LOG.md).

## 2026-05-22 — SenseCap `.15` upgraded to `feat/v0.7.4`

| Field | Value |
|-------|--------|
| **Unit** | `.15` (SenseCap M1) |
| **Commit** | `2a458e5` on `feat/v0.7.4` |
| **Result** | pass |
| **Tester** | agent |
| **Notes** | `git fetch && checkout feat/v0.7.4 && pull`, `pip install -r requirements.txt`, `systemctl restart meshpoint`. Identity HTTP 200, firmware **0.7.3.1**, device `Sensecapm1-Provisiontest1`. Full `smoke_v074_api.py` **all OK** (including mqtt PUT; was 405 on pre-pull `feat/v0.7.3-auth-backend`). No concentrator regressions observed in startup logs. |

## 2026-05-22 — SenseCap `.15` pre-pull (superseded)

| Field | Value |
|-------|--------|
| **Unit** | `.15` |
| **Result** | partial |
| **Notes** | Was on `0.7.2` / `feat/v0.7.3-auth-backend` before pull; see upgraded row above. |

**.49 fresh SD:** waived for v0.7.4 (see Priority B below).

---

## Testing queue (before version bump)

**Major gate first:** [MAJOR-GATE.md](MAJOR-GATE.md) — Tier 1 on `.141` only (~90–120 min). Defer polish/axe/GPS/keyboard roving to fleet feedback unless something fails Tier 1.

Work full matrix from [README.md](README.md) when you need formal `[x]` cells. Current Pi target: **`feat/v0.7.4` @ `7a0a863+`** (kitchen-sink MQTT/upstream/device/GPS APIs + IA cleanup `7a0a863`). Pull on `.141` before Tier 1; hard-refresh browser. Prior automated pass was **`2a458e5`** / **`7fa894c`** — re-run Configuration + MeshCore UI after pull.

### Priority A — finish `.141` matrix rows still `[ ]` or `partial`

| Order | Doc file | Matrix row | Why now |
|-------|----------|------------|---------|
| 1 | [configuration.md](configuration.md) | Identity, Radio, Channels, MQTT | Largest `[ ]` block; MQTT API already smoke-pass at `511e841` |
| 2 | [configuration.md](configuration.md) | MeshCore card (Send Advert, Refresh, channel sync) | PR #53 + #54/#55 territory |
| 3 | [auth.md](auth.md) | Password change, sign-out-everywhere, lockout, viewer | Tier 1 A **pass** (human): change password + logout everywhere; optional viewer + lockout UI still `[ ]` |
| 4 | [terminal.md](terminal.md) | Web terminal | CONNECTED; need xterm commands + audit tail |
| 5 | [updates.md](updates.md) | Update apply + branch picker | Re-run Apply on `7fa894c`; confirm stream/recovery; log `install.sh` SEGV as known flake if repeats |
| 6 | [cherry-picks.md](cherry-picks.md) | MQTT paths, MeshCore map (#51), channel config (#53) | All `[ ]` on matrix |
| 7 | [dangerous.md](dangerous.md) | Dangerous actions | Restart pass; clear DB / wipe phantoms only if intentional |
| 8 | [foundation.md](foundation.md) | Sidebar (close §4 or mark blocked), map, audit | Upgrade §1 badges 12–14; §4 decision |
| 9 | [polish.md](polish.md) | Cross-cutting | Required before tag per README |
| 10 | [spectral_scan.md](spectral_scan.md) | Spectral / noise floor | §1 pass; §9 browser tooltip |

### Priority B — second unit

| Unit | Minimum bar | Status |
|------|-------------|--------|
| `.15` (SenseCap) | Pull `feat/v0.7.4` + restart + full smoke | **pass** — `2a458e5`, smoke all OK |
| `.49` (fresh SD) | — | **waived v0.7.4** — no installer/wizard changes in RC; fleet upgrades via `git pull` (validated `.141`) |

### Priority C — only after matrix green

- Version bump (`src/version.py`, `default.yaml`, README badge)
- CHANGELOG v0.7.4 section final review
- Merge `feat/v0.7.4` → `main`, Discord blurb
- **Not before C:** phantom branch merge, PKI, relay strategy, cloud private commit
