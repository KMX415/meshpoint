# v0.7.6 mesh participant — test results

**Branch:** `feat/v0.7.6`  
**HEAD:** `eb1e4d8` (deployed on `.141` 2026-06-05)  
**Last updated:** 2026-06-05 (witness sign-off on `.141`)  
**Automated (local, 2026-06-04):** 906 pytest passed, 3 skipped.

**Ship gate:** **GREEN** for version bump on `.141` @ `eb1e4d8`. Rows 0–3, 5–9, 11 signed off. Row 4 optional (not re-run). Row 10 conditional/deferred.

---

## Pre-bump re-test (`.141` @ `eb1e4d8`)

PKI mesh-participant rows **1–9** and **11** passed on `.141` at earlier HEAD `d4ff29b` / sign-off record `68946df`. Sprint polish landed **after** that sign-off (apply path, broadcast sender fix, startup crash fix, map filters, MeshCore UX copy). Re-run the queue below before bumping `src/version.py`.

| # | Scenario | Status | Notes |
|---|----------|--------|-------|
| 0 | Boot smoke | pass | **2026-06-05** — deploy smoke + dashboard/Messages used for rows 2/3/9 |
| 1 | Green lock | pass | **2026-06-05** — PKI closed lock on phone |
| 2 | Phone → Meshpoint DM | pass | **2026-06-05** |
| 3 | Meshpoint → phone DM | pass | **2026-06-05** |
| 4 | 2.4.x Shared Key fallback | skip | Optional; not re-run this cycle (passed @ `d4ff29b` May 30) |
| 5 | DM with want_ack | pass | **2026-06-05** |
| 6 | Device metrics in app | pass | **2026-06-05** |
| 7 | Position on map | pass | **2026-06-05** |
| 8 | Traceroute to Meshpoint | pass | **2026-06-05** |
| 9 | Channel broadcast regression | pass | **2026-06-05** — sender name correct, not "Broadcast" |
| 10 | MQTT TLS | conditional | Code shipped; needs external `mqtts` tester (non-blocking) |
| 11 | Signal quality (local_stats) | pass | **2026-06-05** — app Signal Quality log entries |

### Session log (2026-06-05)

| Check | Result |
|-------|--------|
| SSH deploy `feat/v0.7.6` @ `eb1e4d8` | **pass** — git pull, pip, restart OK |
| `systemctl is-active meshpoint` | **active** |
| Concentrator / RX | **pass** — reset logged, 7 `packet_router` lines in 5m window |
| `GET /api/identity` (LAN) | 200 — `Meshpoint-KS-RAKV2`, firmware **0.7.5.1**, `setup_required: false` |
| `GET /api/health` | 404 (endpoint absent on this build; smoke script false negative) |
| Witness rows 0–3, 5–9, 11 | **pass** — user sign-off 2026-06-05 on `.141` @ `eb1e4d8` |

### Session log (2026-06-04)

| Check | Result |
|-------|--------|
| SSH `pi@192.168.0.141` | blocked (env var not visible to agent shell) |
| `GET /api/identity` | 200 — pre-deploy, still on older tree |
| Deploy to `feat/v0.7.6` | not run |

### Testing queue (order)

1. ~~Deploy `.141` to `feat/v0.7.6` @ `eb1e4d8`~~ **done 2026-06-05.**
2. ~~Rows 0, 1, 2, 3, 5, 6, 7, 8, 9, 11~~ **pass 2026-06-05.**
3. Row 4 — skipped (optional; prior pass archived).
4. Row 10 — conditional; non-blocking for ship.
5. ~~**Next:** version bump + `channels.py` RC row~~ **done 2026-06-05.** Merge `feat/v0.7.6` → `main` and push (human).
6. **Optional:** dashboard extras (map filter pills, Settings → Updates Apply); `.49` fresh-SD parity.

---

## Prior witness (archived — `feat/v0.7.6-pki` @ `d4ff29b`, 2026-05-30)

| # | Scenario | Status | Notes |
|---|----------|--------|-------|
| 1 | Green lock | pass | `.141` post-`d4ff29b` |
| 2 | Phone → Meshpoint DM | pass | |
| 3 | Meshpoint → phone DM | pass | |
| 4 | 2.4.x Shared Key fallback | pass | |
| 5 | DM with want_ack | pass | |
| 6 | Device metrics in app | pass | |
| 7 | Position on map | pass | |
| 8 | Traceroute to Meshpoint | pass | |
| 9 | Channel broadcast regression | pass | |
| 10 | MQTT TLS | conditional | Not exercised on `.141` |
| 11 | Signal quality (local_stats) | pass | |

Commits after this archive: `68946df` sign-off record through `c5db5bd` (see `git log 68946df..HEAD`).

---

## Unit coverage (local)

| Area | Tests |
|------|-------|
| Keypair load/create | `tests/test_keypair.py` |
| PKI AES-CCM round-trip | `tests/test_pki_crypto.py` |
| NodeInfo pubkey, routing ACK, traceroute, telemetry reply, PKI/channel encryption | `tests/test_meshtastic_mesh_participant.py` |
| Inbound ACK / traceroute / telemetry triggers | `tests/test_meshtastic_inbound_handler.py` |
| Relay skips unicast-to-local-node | `tests/test_native_relay.py` |

---

## Deploy on test Pi

```
cd /opt/meshpoint
sudo git fetch origin
sudo git checkout feat/v0.7.6
sudo git pull origin feat/v0.7.6
sudo /opt/meshpoint/venv/bin/pip install -r requirements.txt
sudo systemctl restart meshpoint
```

Or: **Settings → Updates → Release candidate (v0.7.6)** → Apply (after dashboard is on a build that offers `rc-076`).

Ensure `transmit.enabled: true` in `local.yaml`. PKI keys at `data/keys.yaml` on first boot (existing installs keep keys).

---

## Agent handoff

**Read [`AGENT-HANDOFF.md`](AGENT-HANDOFF.md)** for traceroute, telemetry request, PKI reply encryption, and relay rules.

**After matrix green:** bump `src/version.py`, `config/default.yaml` `firmware_version`, README badge, `docs/CHANGELOG.md` v0.7.6 section, update `channels.py` RC row to next sprint on `main`, merge `feat/v0.7.6` → `main`.

**Optional before ship:** `.49` fresh-SD parity; row 10 MQTT TLS when a contributor has `mqtts` infra.
