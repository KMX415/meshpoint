# v0.7.6 mesh participant — test results

**Branch:** `feat/v0.7.6-pki`  
**Last updated:** 2026-06-01  
**Automated:** 872 pytest passed (3 skipped), ruff clean on touched paths, Bandit clean on crypto modules.

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
| 8 | Traceroute to Meshpoint | pending | Expect single-hop path |
| 9 | Channel broadcast regression | pending | LongFast RX unchanged |
| 10 | MQTT TLS | pending | Enable `mqtt.tls_enabled` + port 8883 |

## Unit coverage (local)

| Area | Tests |
|------|-------|
| Keypair load/create | `tests/test_keypair.py` |
| PKI AES-CCM round-trip | `tests/test_pki_crypto.py` |
| NodeInfo pubkey, routing ACK, PKI DM | `tests/test_meshtastic_mesh_participant.py` |
| Inbound ACK trigger | `tests/test_meshtastic_inbound_handler.py` |

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

Hardware sign-off blocks merge to `feat/v0.7.6` / version bump. Walk matrix top to bottom on `.141`, mark `[x]` here with timestamp + observer.
