# v0.7.6 mesh participant — test results

**Branch:** `feat/v0.7.6`  
**HEAD:** `51a5102` (feature freeze for pre-bump validation)  
**Last updated:** 2026-06-04 (LAN probe; deploy blocked on SSH auth)  
**Automated (local, 2026-06-04):** 906 pytest passed, 3 skipped.

**Ship gate:** Re-confirm witness matrix on `.141` at this SHA, then version bump + merge to `main`. Row 10 (MQTT TLS) remains conditional/deferred.

---

## Pre-bump re-test (`.141` @ `c5db5bd`)

PKI mesh-participant rows **1–9** and **11** passed on `.141` at earlier HEAD `d4ff29b` / sign-off record `68946df`. Sprint polish landed **after** that sign-off (apply path, broadcast sender fix, startup crash fix, map filters, MeshCore UX copy). Re-run the queue below before bumping `src/version.py`.

| # | Scenario | Status | Notes |
|---|----------|--------|-------|
| 0 | Boot smoke | partial | **2026-06-04 LAN:** `.141` reachable; `GET /api/identity` 200, `Meshpoint-KS-RAKV2`, **v0.7.5.1**, Online; `/login` loads. **Not yet on `feat/v0.7.6`** (SSH auth failed: set `MESHPOINT_PI_PASSWORD` to deploy). |
| 1 | Green lock | pending | Re-spot-check PKI closed lock after NodeInfo cycle |
| 2 | Phone → Meshpoint DM | pending | |
| 3 | Meshpoint → phone DM | pending | |
| 4 | 2.4.x Shared Key fallback | pending | Optional if no 2.4 witness handy |
| 5 | DM with want_ack | pending | |
| 6 | Device metrics in app | pending | |
| 7 | Position on map | pending | |
| 8 | Traceroute to Meshpoint | pending | SNR not `? dB` on direct hop |
| 9 | Channel broadcast regression | pending | **Priority:** `0c4a598` sender-name fix; public TEXT shows node name not "Broadcast" |
| 10 | MQTT TLS | conditional | Code shipped; needs external `mqtts` tester (non-blocking) |
| 11 | Signal quality (local_stats) | pending | App writes new Signal Quality log entries |

### Session log (2026-06-04)

| Check | Result |
|-------|--------|
| SSH `pi@192.168.0.141` | **blocked** — `MESHPOINT_PI_PASSWORD` unset; `id_ed25519` not authorized |
| `GET /api/identity` | 200 — device `Meshpoint-KS-RAKV2`, firmware **0.7.5.1**, `setup_required: false`, Online |
| Playwright `/login` | Auth shell loads; identity strip shows v0.7.5.1 Online |
| Deploy to `feat/v0.7.6` | **not run** — needs SSH |

**Unblock:** In Cursor terminal: `$env:MESHPOINT_PI_PASSWORD = '<pi-password>'` then ask agent to retry deploy.

### Testing queue (order)

1. **Deploy** `.141` to `feat/v0.7.6` @ `51a5102` (block below). Confirm `transmit.enabled: true`.
2. **Row 0** — clean boot, dashboard loads, Messages tab opens (validates `1fb3f34`).
3. **Row 9** — hear a public LongFast TEXT from another node; sender name correct in Messages + packet feed.
4. **Rows 1, 5, 6, 7, 8, 11** — PKI spot-check pass (same procedure as May 30 run; see [`AGENT-HANDOFF.md`](AGENT-HANDOFF.md)).
5. **Rows 2–3** — bidirectional DM with 2.5+ phone.
6. **Dashboard extras** (non-matrix, quick): map Direct/Relayed filter pills (`31a9214`); Settings → Updates Apply on RC branch (`b2470b2`) if you use the picker.
7. Mark each row `pass` with date when done. **All rows 0–9 and 11 `[x]`** (or documented conditional on 10) → ready for version bump.

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
