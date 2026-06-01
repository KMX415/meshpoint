# v0.7.6 mesh participant — test results

**Branch:** `feat/v0.7.6-pki`  
**HEAD:** `d4ff29b` (see commit table in [`AGENT-HANDOFF.md`](AGENT-HANDOFF.md))  
**Last updated:** 2026-05-30 (`.141` witness matrix complete; row 10 deferred)  
**Automated:** 872+ pytest passed, ruff clean on touched paths, Bandit clean on crypto modules.

## Witness matrix (hardware: RAK V2 `.141`)

| # | Scenario | Status | Notes |
|---|----------|--------|-------|
| 1 | Green lock | pass | `.141` post-`d4ff29b`: PKI green/closed lock on Meshtastic 2.5+ app after NodeInfo cycle |
| 2 | Phone → Meshpoint DM | pass | `.141`: witness DM decrypted in dashboard Messages |
| 3 | Meshpoint → phone DM | pass | `.141`: dashboard DM delivered on 2.5+ phone |
| 4 | 2.4.x Shared Key fallback | pass | `.141`: DM to Meshpoint from non-PKI peer; shared-key path works both directions |
| 5 | DM with want_ack | pass | `.141`: sender phone shows delivered after routing ACK |
| 6 | Device metrics in app | pass | `.141` post-`d4ff29b`: request reply writes new device-metrics log entries in Meshtastic app |
| 7 | Position on map | pass | `.141`: Meshpoint pin on Meshtastic app map at configured coords |
| 8 | Traceroute to Meshpoint | pass | `.141` post-`52fd70c`/`d4ff29b`: trace completes; SNR not `? dB` on direct hop |
| 9 | Channel broadcast regression | pass | `.141`: LongFast RX/decode unchanged with v0.7.6 TX stack active |
| 10 | MQTT TLS | conditional | Code shipped (`tls_enabled` + `mqtt_publisher.tls_set`); **not hardware-validated here** — defer to contributor with MQTT broker access |
| 11 | Signal quality (local_stats request) | pass | `.141` post-`d4ff29b`: app writes new Signal Quality log entries (same pattern as device metrics). Debug decode + hops away 0 confirmed. Journal retries are benign if UI updates; optional request dedup is polish only. |

## Unit coverage (local)

| Area | Tests |
|------|-------|
| Keypair load/create | `tests/test_keypair.py` |
| PKI AES-CCM round-trip | `tests/test_pki_crypto.py` |
| NodeInfo pubkey, routing ACK, traceroute, telemetry reply, PKI/channel encryption | `tests/test_meshtastic_mesh_participant.py` |
| Inbound ACK / traceroute / telemetry triggers | `tests/test_meshtastic_inbound_handler.py` |
| Relay skips unicast-to-local-node | `tests/test_native_relay.py` |

## Deploy on test Pi

```
cd /opt/meshpoint
sudo git fetch origin
sudo git checkout feat/v0.7.6-pki
sudo git pull
sudo /opt/meshpoint/venv/bin/pip install -r requirements.txt
sudo systemctl restart meshpoint
```

Ensure `transmit.enabled: true` in `local.yaml`. PKI keys appear at `data/keys.yaml` beside the SQLite DB on first boot.

## Agent handoff

**Read [`AGENT-HANDOFF.md`](AGENT-HANDOFF.md) first** for traceroute, telemetry request, PKI reply encryption, and relay fixes landed during RC hardware debug.

Hardware sign-off blocks merge to `feat/v0.7.6` / version bump.

**`.141` sign-off (2026-05-30):** rows **1–9** and **11** pass. Row **10** conditional (MQTT TLS not exercised on this bench; needs external tester with `mqtts` broker).

Optional before ship: `.49` fresh-SD parity pass; row 10 hardware validation when someone with MQTT infra can run it.
