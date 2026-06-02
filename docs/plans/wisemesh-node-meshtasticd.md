# WisMesh Node: meshtasticd IPC spike

**Host:** `192.168.0.194` (`meshpoint-1`)  
**OS:** Debian 13 (trixie)  
**HAT:** RAK6421 (`6421 Pi Hat`, vendor `RAK`)  
**meshtasticd:** 2.7.15  
**Branch:** `feat/wismesh-hat`  
**Date:** 2026-05-22

## Install (Debian 13)

Pi OS on this unit reports **Debian 13 (trixie)**. Use the **Debian_13** OBS repo:

```bash
echo 'deb http://download.opensuse.org/repositories/network:/Meshtastic:/beta/Debian_13/ /' | sudo tee /etc/apt/sources.list.d/network:Meshtastic:beta.list
curl -fsSL https://download.opensuse.org/repositories/network:Meshtastic:beta/Debian_13/Release.key | gpg --dearmor | sudo tee /etc/apt/trusted.gpg.d/network_Meshtastic_beta.gpg > /dev/null
sudo apt update
sudo apt install meshtasticd
```

### RAK6421 LoRa preset

`scripts/install_meshtasticd.sh` (via `install.sh --platform node`) installs the **RAK13302 1W** preset by default:

- Bundled at `config/meshtasticd/lora-RAK6421-13302-slot1.yaml` (meshtasticd 2.7.x packages often ship only the 13300 preset in `available.d/`)
- Copied to `/etc/meshtasticd/config.d/` with `Enable_Pins`, `TX_GAIN_LORA`, and `CS: 8` for the Pi SPI overlay

**RAK13300 (standard power):** set `meshtasticd.preset: lora-RAK6421-13300-slot1.yaml` in `local.yaml` and re-run `sudo ./scripts/install_meshtasticd.sh`, or `MESHTASTICD_PRESET=lora-RAK6421-13300-slot1.yaml sudo ./scripts/install.sh --platform node`.

**13302 hardware power:** the RAK13302 module has a 3-pin jumper for the 5V PA rail. External 5V or battery power may be required for full 1W output; software preset alone does not enable the PA if power is wrong.

Manual copy (only if not using Meshpoint installer):

```bash
sudo mkdir -p /etc/meshtasticd/config.d
sudo cp /opt/meshpoint/config/meshtasticd/lora-RAK6421-13302-slot1.yaml /etc/meshtasticd/config.d/
```

### MAC address (required on fresh install)

meshtasticd **will not start** without a node MAC. Put this in `/etc/meshtasticd/config.yaml`:

```yaml
General:
  MACAddressSource: eth0
```

Use `wlan0` if Ethernet is down. meshtasticd derives the Meshtastic node ID from this MAC.

```bash
sudo systemctl enable --now meshtasticd
```

**Failure modes seen on spike:**

| Log line | Fix |
|----------|-----|
| `Unable to find config for 6421 Pi Hat` | Re-run `sudo ./scripts/install_meshtasticd.sh` or copy bundled preset from `config/meshtasticd/` |
| `Blank MAC Address not allowed` | Add `General.MACAddressSource` to `config.yaml` |

## IPC: Meshtastic Python CLI → TCP `4403`

meshtasticd listens on **`0.0.0.0:4403`**. Use the **Meshpoint venv** CLI (already in `requirements.txt`):

```bash
/opt/meshpoint/venv/bin/meshtastic --host localhost:4403 --info
/opt/meshpoint/venv/bin/meshtastic --host localhost:4403 --export-config
```

There is no `/usr/bin/meshtastic` system binary on this Pi; only `/usr/bin/meshtasticd`.

### `--info` snapshot (2026-05-22)

```
Connected to radio
Metadata: hwModel=PORTDUINO, firmwareVersion=2.7.15, role=CLIENT
Preferences.lora: txPower=30, modemPreset=LONG_FAST, txEnabled=true, region=UNSET
Active preset file: lora-RAK6421-13302-slot1.yaml
```

### Fields for Meshpoint display (High power badge)

| Signal | Source | Spike result |
|--------|--------|--------------|
| Module SKU | Preset filename in `/etc/meshtasticd/config.d/` | `lora-RAK6421-13302-slot1.yaml` (default; bundled in Meshpoint repo) |
| TX power | `Preferences.lora.txPower` from `--info` | **30** dBm reported |
| `hw_model` | `Metadata.hwModel` | **PORTDUINO** (does not distinguish RAK13300 vs RAK13302) |

No dedicated `high_power` API field. Badge logic: `13302` in preset name and/or `txPower > 20` as display-only hints.

## Meshpoint Phase 0 validation (same Pi)

With `feat/wismesh-hat` checked out:

```
Platform:        Node (meshtasticd)
Concentrator:    SPI present but no SX1302/SX1303 response
WisMesh HAT:     RAK6421 detected
```

libloragw installed from prior Gateway experiments does **not** trigger false Gateway when chip probe returns none.

## Phase 2 bridge (shipped 2026-05-31)

Production bridge on `feat/wismesh-hat`. See [WISMESH-BRANCH.md](./WISMESH-BRANCH.md) for install and troubleshooting.

| Concern | Implementation |
|---------|----------------|
| **Capture** | `meshtasticd_bridge_worker` subprocess owns one `TCPInterface` on `:4403`; parent reads `RawCapture` from a queue |
| **Why subprocess** | meshtasticd Phone API is single-client; in-process TCP inside uvicorn caused Recv-Q stalls and live OTA silence |
| **TX** | `MeshtasticdTxClient` sends commands to worker over IPC (no second TCP client) |
| **Stream safety** | `LockedTCPInterface` serializes writes only; read-lock caused connect deadlock |
| **NodeInfo** | Skipped on `device.platform: node` (meshtasticd owns identity) |
| **DM routing** | Accept DMs for meshtasticd live node id and optional `transmit.node_id` (`message_routing.py`) |
| **systemd** | `meshpoint-node.service` `After=meshtasticd.service` |
| **Stall recovery** | Worker reconnects TCP after 90s with no packets; reader thread watchdog |

**Spike lesson retained:** never run `meshtastic --host localhost:4403` while Meshpoint is running.

## Pi checkout

See [WISMESH-BRANCH.md](./WISMESH-BRANCH.md).
