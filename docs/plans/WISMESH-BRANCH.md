# WisMesh Node platform (`feat/wismesh-hat`)

Experimental **Meshpoint Node** support for the RAK6421 WisMesh Pi HAT (meshtasticd-backed RF).
This work lives on a **long-lived branch** and may not merge to `main` for some time.
Gateway users (RAK2287 / SenseCap M1 concentrators) should stay on **`main`**.

**Last updated:** 2026-05-31 (13302 1W default preset bundled)

## Architecture

```
[SX1262 HAT] <--SPI--> meshtasticd (Portduino, owns RF)
                              |
                         TCP :4403 (Phone API, single client)
                              |
              meshtasticd_bridge_worker (subprocess)
                              |
                    meshtastic-python LockedTCPInterface
                              |
              MeshtasticdBridgeSource (parent process)
                              |
                   decode / store / dashboard / upstream
```

**Why a worker subprocess:** meshtasticd exposes a **single-client** Phone API with a global read cursor. Running meshtastic-python inside uvicorn caused stream stalls (TCP `Recv-Q` growth, live OTA silence while meshtasticd still forwarded to phone). The worker owns one TCP session for the process lifetime; the parent only reads `RawCapture` objects from a queue and sends TX commands over IPC.

**Key modules:**

| File | Role |
|------|------|
| `src/capture/meshtasticd_bridge_worker.py` | Subprocess: TCP connect, pubsub receive, TX commands |
| `src/capture/meshtasticd_bridge_source.py` | Spawns worker, async packet iterator, TX API |
| `src/capture/meshtasticd_stream_client.py` | `LockedTCPInterface`: serializes **writes** only (read lock deadlocks connect) |
| `src/capture/meshtasticd_bridge_ipc.py` | Command/response protocol |
| `src/capture/meshtastic_packet_adapter.py` | meshtastic-python dict → `RawCapture` / API decode path |
| `src/api/message_routing.py` | DM identity: meshtasticd node id vs `transmit.node_id` |
| `src/transmit/meshtasticd_tx_client.py` | TX via bridge commands (not in-process interface) |
| `scripts/meshpoint-node.service` | `After=meshtasticd.service`, no concentrator reset |

**Node platform rules:**

- **meshtasticd owns RF identity.** NodeInfo broadcaster is skipped (`server.py`); do not `setOwner` from Meshpoint on boot.
- **Do not run** `meshtastic --host localhost:4403` while Meshpoint is running (steals the single client slot).
- **Restart order:** `meshtasticd` first, then `meshpoint` (clears stale TCP state).

## Install (6421 + WisBlock module)

```bash
cd /opt/meshpoint
sudo git fetch origin
sudo git checkout feat/wismesh-hat
sudo git pull origin feat/wismesh-hat
sudo ./scripts/install.sh --platform node
sudo meshpoint setup
sudo systemctl restart meshtasticd meshpoint
```

`install.sh --platform node` will:

- Skip the SX1302 HAL build
- Install and configure **meshtasticd** (Debian 12/13 OBS repo)
- Copy the **RAK13302 1W** LoRa preset (bundled in `config/meshtasticd/`; falls back if meshtasticd package lacks it)
- Install `meshpoint-node.service` (starts **after** meshtasticd)

The setup wizard writes `device.platform: node` and `capture.sources: [meshtasticd]`.

## Verify

```bash
systemctl status meshtasticd meshpoint
ss -tn state established '( sport = :4403 or dport = :4403 )'
journalctl -u meshpoint -n 50 --no-pager | grep -E 'bridge connected|>> PKT|DM identity'
```

Healthy signs:

- `meshtasticd bridge connected to 127.0.0.1:4403 (worker pid=...)`
- `Meshtastic DM identity: ...` listing meshtasticd's live node id
- TCP `Recv-Q` stays **0** under load
- OTA `>> PKT` lines continue past 2+ minutes (not just at boot)

Optional CLI probe (stop Meshpoint first):

```bash
sudo systemctl stop meshpoint
/opt/meshpoint/venv/bin/meshtastic --host localhost:4403 --info
sudo systemctl start meshpoint
```

## Direct messages (phone → Meshpoint)

Meshtastic DMs target **meshtasticd's node id** (derived from the HAT MAC), not necessarily `transmit.node_id` in `local.yaml`.

Meshpoint accepts DMs for **both** ids when they differ. Startup log example:

```
WARNING server: meshtasticd node id 9ea7e9d9 differs from transmit.node_id 7e3fa19c; routing DMs to meshtasticd identity
INFO    server: Meshtastic DM identity: 7e3fa19c, 9ea7e9d9
```

If DMs decode in logs but do not appear on the Messages tab, check that warning was absent before the DM routing fix. Old rows saved as `direction=overheard` are hidden unless `GET /api/messages/conversations?include_overheard=true`.

**Recommendation:** On Node platforms, remove a stale pinned `transmit.node_id` from `local.yaml` unless you intentionally need it for upstream identity. Let meshtasticd own the RF node id.

## Packet log: hops and RSSI

`>> PKT` lines now include hop metadata after SNR:

```
>> PKT  meshtastic  a0dd8936 -> ffffffff  TEXT  rssi -117.0 ... snr -7.2 hl=7/7 hops=0 relay=0x36 direct  "Yes"
```

| Field | Meaning |
|-------|---------|
| `hl=7/7` | Remaining hops / hop start |
| `hops=0` | Hops consumed (`hop_start - hop_limit`) |
| `relay=0x36` | Last relay byte from Meshtastic header |
| `direct` | Heard directly (0 hops consumed) |
| `relayed` | At least one relay hop |

**RSSI on Node:** Values come from meshtasticd's SX1262 driver unchanged. Meshpoint does not attenuate them. `--` on `9ea7e9d9` telemetry is normal (locally generated, no OTA RX). Weak RSSI at short range usually indicates the **other node's TX/antenna**, not the WisMesh receiver. Compare direct copies (`hops=0`) only; the wider mesh also delivers relayed copies at -120 dBm that are not shown in `>> PKT`.

## Migrate between platforms

See [`docs/MIGRATE-GATEWAY-TO-NODE.md`](../MIGRATE-GATEWAY-TO-NODE.md) and `meshpoint migrate-platform --to node|gateway`.

## Switch back to Gateway (concentrator)

```bash
cd /opt/meshpoint
sudo git checkout main
sudo git pull origin main
sudo meshpoint migrate-platform --to gateway --force
sudo ./scripts/install.sh --platform gateway
sudo systemctl restart meshpoint
```

Preserve `config/local.yaml` if you want the same `device_id` and API key.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Logs stop after ~2 min, meshtasticd still RX | Stale TCP / in-process reader | Use current branch (worker bridge); restart `meshtasticd` then `meshpoint` |
| `bridge connected` never appears | Read-lock deadlock (fixed) or meshtasticd down | `systemctl restart meshtasticd meshpoint`; check port 4403 |
| DM in logs, not on dashboard | DM routed to wrong node id | Pull latest; check `Meshtastic DM identity` log line |
| `meshtastic --host` while Meshpoint runs | Second client corrupts stream | Stop Meshpoint before CLI probe |
| meshtasticd crash: blank MAC | Missing MAC source | `General.MACAddressSource: eth0` in `/etc/meshtasticd/config.yaml` |
| meshtasticd crash: no preset | Missing HAT preset | Re-run `sudo ./scripts/install_meshtasticd.sh` or copy bundled `config/meshtasticd/lora-RAK6421-13302-slot1.yaml` |
| TX power stuck at ~22 dBm on RAK13302 | Wrong preset (13300) or PA power jumper | Confirm preset name in `meshtastic --host localhost:4403 --info`; use 13302 yaml + 5V PA jumper |
| Dashboard Apply fails at `install.sh` | Interrupted dpkg or git synced but install did not finish | `sudo dpkg --configure -a`, then Apply again. Current branch heals dpkg and skips dist-upgrade on upgrade |

## Tests

From repo root:

```bash
python -m pytest tests/test_meshtasticd_bridge.py tests/test_meshtasticd_bridge_ipc.py \
  tests/test_meshtasticd_stream_client.py tests/test_meshtasticd_daemon.py \
  tests/test_message_routing.py tests/test_log_format_rssi.py -q
```

## Related docs

- [`wisemesh-node-meshtasticd.md`](wisemesh-node-meshtasticd.md): meshtasticd IPC spike notes
- [`MIGRATE-GATEWAY-TO-NODE.md`](../MIGRATE-GATEWAY-TO-NODE.md): migration runbook
