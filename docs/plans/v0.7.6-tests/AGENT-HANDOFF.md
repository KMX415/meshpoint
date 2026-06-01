# v0.7.6 mesh participant — agent handoff

**Branch:** `feat/v0.7.6-pki`  
**Last updated:** 2026-06-01  
**Purpose:** Session log for agents working the v0.7.6 RC. Read this before touching inbound TX, PKI replies, traceroute, or telemetry request handling.

**Canonical plan:** `docs/plans/v0.7.6-pki-release.md`  
**Witness matrix:** `docs/plans/v0.7.6-tests/RESULTS.md`

---

## Branch HEAD (post hardware-debug)

| SHA | Summary |
|-----|---------|
| `2437662` | Telemetry delivery: skip relay for unicast-to-us, pipeline order, `local_stats` fields (`time`, `noise_floor`) |
| `52fd70c` | Telemetry request replies + reply encryption matches request channel/PKI |
| `877d5b1` | Traceroute `RouteDiscovery`: preserve inbound route/SNR, `route_back`/`snr_back`, no target duplication |
| `a5ad9be` | Traceroute + routing ACK PKI path, `request_id` on replies |
| `228ffdf` | Display prefs: approximate location labels follow mi/km setting |

Earlier RC commits (identity, DMs, broadcasters): `99911f3`, `9e86edb`, `45d9d85`, …

---

## Design rule: reply encryption must match the request

**Do not** call `lookup_public_key()` and force PKI on every unicast reply.

| Inbound `channel_hash` | Reply encryption |
|------------------------|------------------|
| `0x00` | PKI (AES-CCM) when we have recipient pubkey and local keypair |
| `0x08` (or any non-zero channel hash) | Channel AES-CTR with key resolved from hash |

Implementation: `TxService._recipient_pubkey_for_reply()` in `src/transmit/tx_service.py`.

**Symptom when wrong:** reply TX succeeds (`TX traceroute reply OK`) but phone shows `? dB`, duplicate nodes, or ignores response. Meshpoint may hear its own reply as `ENCRYPTED ch=0x00` loopback while the request arrived on `ch=0x08`.

---

## Traceroute (matrix row 8)

### What was broken

1. **No reply** — inbound `TRACEROUTE` handler existed but replies used wrong crypto or missing `request_id`.
2. **Reply TX OK, bad app display** — rebuilt route from scratch, duplicated Meshpoint node, sent one SNR for multi-hop path → Meshtastic app shows `? dB` on forward hops.

### Fixes (`a5ad9be`, `877d5b1`)

- `build_traceroute_reply()` + `send_traceroute_reply()` with `request_id` = inbound packet id.
- Preserve inbound `route` / `snr_towards` from decoded payload; append **only** final-hop SNR (×4 int, firmware style).
- Populate `route_back` / `snr_back` (requester on return path).
- Do **not** append target node to `route` (was creating phantom duplicate).

### Log fingerprints (pass)

```
Inbound traceroute from 7d8b98a9 (id=... ch=0x08)
TX traceroute reply OK to 7d8b98a9 (reply id=..., inbound route=N snr=M)
```

### Hardware note (.141, 2026-06-01)

User confirmed traceroute works after `877d5b1`. PKI-shaped loopback of own reply (`ENCRYPTED ch=0x00`) was a separate encryption-matching bug; fixed by `_recipient_pubkey_for_reply` for channel-based requests.

---

## Signal quality / telemetry request (new matrix row 11)

Meshtastic app **Signal quality** (and CLI `--request-telemetry local_stats`) sends a **unicast TELEMETRY** probe with an empty or `local_stats` variant payload. The Meshpoint must reply with matching variant, `request_id`, and encryption.

### What was broken

1. **No handler** — `MeshtasticInboundHandler` only handled `TRACEROUTE` and `TEXT`/`want_ack`. Probes decoded but no TX.
2. **Relay blocked delivery** — `RelayManager` relayed `7d8b98a9 -> c0ffee42` telemetry requests (~641ms airtime) **before** reply handler ran, on a half-duplex concentrator.
3. **Incomplete protobuf** — reply missing `Telemetry.time` and `LocalStats.noise_floor` that firmware always sets (`DeviceTelemetry.cpp`).

### Fixes (`52fd70c`, `2437662`)

| Piece | Change |
|-------|--------|
| `MeshtasticInboundHandler` | `PacketType.TELEMETRY` unicast to our node → `send_telemetry_reply()` |
| `build_telemetry_reply()` | Unicast, `request_id`, `device_metrics` or `local_stats` variant |
| `send_telemetry_reply()` | Metrics from shared `_telemetry_metrics_providers()` |
| `_decode_telemetry()` | Sets `telemetry_variant` (`local_stats` vs `device_metrics`) from request payload |
| `RelayManager` | `set_local_node_id()` + skip relay when `destination_id == our node` (`dest_local`) |
| `PipelineCoordinator` | `_notify_callbacks()` **before** `_relay.process_packet()` so inbound replies are not delayed behind relay |
| `local_stats` reply | `time`, `noise_floor` (from `NoiseFloorTracker`), `num_tx_relay`, packet counts |

### Log fingerprints

**Fail (old):**

```
RELAY [meshtastic] 7d8b98a9 -> c0ffee42 (type=telemetry, ...)
TX telemetry reply OK ...
```

(three retries from phone, app shows nothing)

**Pass (expected after `2437662`):**

```
Inbound telemetry request from 7d8b98a9 (id=... variant=local_stats ch=0x00)
Telemetry reply TX OK to 7d8b98a9 (reply id=..., variant=local_stats, pki=True)
```

No `RELAY ... -> c0ffee42` line for the same packet.

**Note:** Probes from Meshtastic 2.5+ phone to a PKI-capable Meshpoint often arrive as `ch=0x00` (PKI). Reply must use PKI, not channel AES.

---

## Relay interaction (do not regress)

Native onboard relay (`_wire_native_relay` in `src/api/server.py`) shares the SX1302 TX path with DMs, traceroute replies, and telemetry replies.

**Never relay:**

- Unicast packets whose `destination_id` equals our Meshtastic node id (`dest_local`).

**Why:** Relaying a packet addressed to us wastes duty cycle and was observed to prevent telemetry replies from reaching the requester.

Tests: `tests/test_native_relay.py::TestRelayManagerAsyncDispatch::test_skips_relay_for_unicast_to_local_node`

---

## Inbound handler coverage (`MeshtasticInboundHandler`)

| Inbound type | Condition | Action |
|--------------|-----------|--------|
| `TRACEROUTE` | dest = us, decrypted | `send_traceroute_reply()` |
| `TELEMETRY` | dest = us, decrypted | `send_telemetry_reply()` |
| `TEXT` | dest = us, decrypted, `want_ack` | `send_routing_ack()` |

File: `src/transmit/meshtastic_inbound_handler.py`

Wired from `src/api/server.py::_setup_inbound_responder()` with telemetry metric providers + `relay.set_local_node_id()`.

---

## Key files (edit map)

| Area | Files |
|------|-------|
| Inbound orchestration | `meshtastic_inbound_handler.py`, `server.py::_setup_inbound_responder` |
| Reply TX | `tx_service.py` (`send_*_reply`, `_recipient_pubkey_for_reply`, `_build_traceroute_reply_data`) |
| Packet build | `meshtastic_builder.py` (`build_traceroute_reply`, `build_telemetry_reply`, `build_routing_ack`) |
| Decode | `portnum_handlers.py` (`telemetry_variant`), `meshtastic_decoder.py` (PKI path) |
| Relay filter | `relay_manager.py`, `coordinator.py` (pipeline order) |
| Metrics for replies | `server.py::_telemetry_metrics_providers()` |
| Tests | `test_meshtastic_mesh_participant.py`, `test_meshtastic_inbound_handler.py`, `test_native_relay.py` |

---

## Unit tests added/extended (local green)

- Traceroute SNR / `route_back` preservation
- PKI traceroute round-trip
- Telemetry reply `request_id` + `local_stats` decode
- Channel reply stays on `ch=0x08` even when pubkey registered
- Inbound handler telemetry branch
- Relay `dest_local` rejection

Run: `python -m pytest tests/test_meshtastic_mesh_participant.py tests/test_meshtastic_inbound_handler.py tests/test_native_relay.py -q`

---

## Witness matrix status (2026-06-01)

Hardware sign-off still **blocks merge**. User hardware sessions on `.141`:

| Row | Scenario | Agent status |
|-----|----------|--------------|
| 8 | Traceroute | User reported working post-`877d5b1`; re-test SNR display after encryption fix |
| 11 | Signal quality / local_stats request | Fix landed `2437662`; **awaiting user re-test** |
| 1–7, 9–10 | Other matrix rows | Still `pending` in `RESULTS.md` |

After each pass, mark `[x]` in `RESULTS.md` with date + observer.

---

## Open / do not confuse

| Item | Status |
|------|--------|
| `fix/no-crc-phantom-leak` | Shipped v0.7.3 on `main`; not v0.7.6 work |
| MeshCore USB `adapt_event` | On `main`; do not re-wire for v0.7.6 |
| MQTT broker TLS | Planned v0.7.6 scope per release plan; separate from telemetry reply work |
| SX1302 SPI bus locking | Deferred per `active-work.mdc`; not a v0.7.6 ship blocker |
| Multi-protocol IF → Meshtastic decoder | Separate bug (nopemesh `if=2 sf5`); not fixed in this RC |

---

## Deploy loop (.141)

```
cd /opt/meshpoint
sudo git fetch origin
sudo git checkout feat/v0.7.6-pki
sudo git pull
sudo systemctl restart meshpoint
```

Requires `transmit.enabled: true`. PKI keys: `data/keys.yaml` (0600).

---

## If signal quality still fails after `2437662`

1. Confirm no `RELAY ... -> <our_node>` on the same timestamp as the probe.
2. Confirm `Telemetry reply TX OK ... pki=True` when probe shows `ch=0x00`.
3. If TX OK but app empty: capture whether phone expects `device_metrics` instead of `local_stats` (check `telemetry_variant` in log).
4. Verify phone has our `public_key` (green lock) and we have requester's pubkey in SQLite (`nodes.public_key`).
5. Check for `PKI DM ... decrypt failed` lines around the same window.
