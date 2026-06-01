# v0.7.6 mesh participant — test results

**Branch:** `feat/v0.7.6-pki`  
**HEAD:** `2437662` (see commit table in [`AGENT-HANDOFF.md`](AGENT-HANDOFF.md))  
**Last updated:** 2026-06-01  
**Automated:** 872+ pytest passed, ruff clean on touched paths, Bandit clean on crypto modules.

## Witness matrix (hardware: RAK V2 `.141`)

| # | Scenario | Status | Notes |
|---|----------|--------|-------|
| 1 | Green lock | pending | Requires NodeInfo cycle on `.141` with Meshtastic 2.5+ app |
| 2 | Phone → Meshpoint DM | pending | |
| 3 | Meshpoint → phone DM | pending | |
| 4 | 2.4.x Shared Key fallback | pending | |
| 5 | DM with want_ack | pending | Check sender app leaves "Sent" |
| 6 | Device metrics in app | pending | Telemetry tab after broadcast interval |
| 7 | Position on map | pending | Requires lat/lon in config |
| 8 | Traceroute to Meshpoint | partial | User `.141`: path completes post-`877d5b1`; re-verify SNR display after encryption-matching fix (`52fd70c`) |
| 9 | Channel broadcast regression | pending | LongFast RX unchanged |
| 10 | MQTT TLS | pending | Enable `mqtt.tls_enabled` + port 8883 |
| 11 | Signal quality (local_stats request) | partial | Fix `2437662` (no self-dest relay + `Telemetry.time`/`noise_floor`); **awaiting re-test** after pull |

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

Hardware sign-off blocks merge to `feat/v0.7.6` / version bump. Walk matrix top to bottom on `.141`, mark `[x]` here with timestamp + observer.
