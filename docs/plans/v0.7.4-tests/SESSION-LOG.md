# v0.7.4 major gate — live session log

**Method:** One step at a time. Agent records result here + one row in [RESULTS.md](RESULTS.md).  
**Unit:** `.141` (RAK V2) · **Branch:** `feat/v0.7.4` · **Target SHA:** `2a458e5`+

**Legend:** `—` pending · `PASS` · `PARTIAL` · `FAIL` · `SKIP` · `n/a`

| ID | Step | Who | Result | Notes |
|----|------|-----|--------|-------|
| 00 | Pi on `feat/v0.7.4` at `2a458e5`+ (pull + `git log -1`) | agent | PASS | SSH `git log -1` → `2a458e5` |
| 01 | Laptop: `python -m pytest tests/ -q` | agent | PASS | 706 passed, 3 skipped |
| 02 | `.141` `/api/health` reachable | agent | PASS | identity curl HTTP 200 |
| 03 | `.141` full `smoke_v074_api.py` | agent | PASS | `SMOKE_SKIP_DANGEROUS=1`; all API checks green |
| A1 | Login dashboard loads | agent | PASS | Playwright |
| A2 | Settings → Auth: wrong current password → inline error | agent | PASS (API) | 401 `invalid_current_password`; UI form partial (429 noise) |
| A3 | Settings → Auth: change password → re-login works | agent | PASS | `testpassword` round-trip + restore via `_session_v074_auth_flow.py` |
| A4 | Sign out everywhere (two sessions) | agent | PASS | Dual cookie jars; `logout_all` → both 401 |
| B1 | Configuration → Identity: save name + coords | agent | PARTIAL | Panel loads; save via smoke API only |
| B2 | Settings → Meshpoint → Restart service; Identity persists | agent | PASS | `restart_service` invoked; identity `Meshpoint RAK` unchanged |
| B3 | Configuration → Radio: preset save + Send Now | agent | PARTIAL | Panel loads; preset/send via smoke API |
| B4 | Configuration → Channels: columns align + Save | agent | PASS | Playwright delta=0; channels PUT via smoke |
| B5 | Configuration → MQTT: enable + Save; journal prefix line | agent | PASS | smoke mqtt PUT OK; journal shows `MQTT disabled` banner line (device has MQTT off) |
| B6 | Configuration → Transmit: save relay field | agent | PASS | Panel loads + smoke relay PUT |
| B7 | GPS | — | n/a | no PUT route |
| C1 | Updates: Check for updates (behind + timestamp) | agent | PASS | `0.7.3.1` local/remote, up to date |
| C2 | Updates: Apply RC (non-destructive if already current OK) | human | — | skipped (already current) |
| C3 | Updates: Rollback after successful apply | human | — | |
| D1 | Terminal: Connect | agent | PASS | `data-state=connected` |
| D2 | Terminal: `pwd` + `whoami` | agent | PASS | Connect + WS OK; headless xterm garbled; SSH confirms `/home/pi` + `pi` |
| E1 | Sidebar: every nav item loads, console clean | agent | PARTIAL | 12 routes OK; 401/429 console noise from rapid nav |
| E2 | Dashboard map + packet feed | agent | PASS | `#map` + Leaflet + `#packet-tbody` |
| E3 | MeshCore contacts ~30s after boot | agent | PARTIAL | Topbar MeshCore name populated |

**`.15` (2026-05-22):** **PASS** — pulled `feat/v0.7.4` @ `2a458e5`, restart OK, full smoke green (incl. mqtt). **`.49`:** waived for v0.7.4.

**Current step:** Matrix walkthrough / ship checklist in [README.md](README.md) (most major gate rows green on `.141`)

**Automation (2026-05-20):** `_session_v074_runner.py`, `_session_v074_playwright.py`, `_session_v074_auth_flow.py`, `_session_v074_continue.py`. Env: `MESHPOINT_PASSWORD`, `MESHPOINT_PI_PASSWORD`; optional `MESHPOINT_TEST_PASSWORD` (default `testpassword`).

**Session started:** 2026-05-20
