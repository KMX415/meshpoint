# Mesh Point

**An SX1302/SX1303 LoRa concentrator that passively captures, decrypts, and maps every Meshtastic and Meshcore packet in range.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-green.svg)](https://www.python.org/)
[![Platform: Raspberry Pi](https://img.shields.io/badge/platform-Raspberry%20Pi%204-red.svg)](https://www.raspberrypi.com/)

![Mesh Radar Dashboard](dashboard.png)

![Mesh Point Terminal](docs/meshpoint-terminal-banner.png)

---

## What Is This?

A Raspberry Pi + SX1302/SX1303 concentrator that listens on **8 LoRa channels simultaneously** and decodes everything it hears. Not a node on the mesh -- a passive listener that sees all traffic across all spreading factors at once.

It captures packets, decrypts them, stores them locally, shows them on a real-time dashboard, and optionally feeds everything upstream to [Mesh Radar](https://meshradar.io) for city-wide mesh intelligence.

### Standard Node vs Mesh Point

| | Standard Node | Mesh Point |
|---|---|---|
| **Channels** | 1 | 8 |
| **Demodulators** | 1 | 16 (multi-SF) |
| **Role** | Participant | Passive observer |
| **Packet visibility** | Own traffic | Everything in range |
| **Storage** | None | SQLite w/ retention |
| **Dashboard** | None | Real-time web UI |

---

## Hardware

> **Requirements:** Raspberry Pi 4, 64-bit Raspberry Pi OS, Python 3.13. The compiled core modules are aarch64 binaries -- other platforms (Pi 3, x86, 32-bit OS) are not currently supported.

### Option A: Buy a RAK Hotspot V2 (~$60, recommended)

The easiest path. RAK/MNTD Hotspot V2 miners (model **RAK7248**) include a Pi 4, RAK2287 (SX1302), Pi HAT, metal enclosure, antenna, and power supply -- everything you need. Helium's IoT network didn't pan out, so these are all over eBay for $40-70.

Search: [`RAK Hotspot V2 / MNTD` on eBay ($30-80)](https://www.ebay.com/sch/i.html?_nkw=RAK%20Hotspot%20V2%20%2F%20MNTD&_sacat=0&_from=R40&rt=nc&_udlo=30&_udhi=80)

<img src="rak7248.png" width="360" alt="RAK7248 Hotspot V2">

Remove the 4 bottom screws to access the SD card slot. Flash a new card with Raspberry Pi OS 64-bit, run the install script, and you have a Mesh Point in a nice aluminum enclosure.

### Option B: Buy a SenseCap M1 (~$40-60)

Another Helium-era miner with identical compatibility. The SenseCap M1 includes a Pi 4, Seeed WM1303 concentrator (SX1303), carrier board, metal enclosure, and antenna. Some units ship with a 64GB SD card included.

Search: [`SenseCap M1` on eBay ($30-60)](https://www.ebay.com/sch/i.html?_nkw=SenseCap%20M1&_sacat=0&_from=R40&rt=nc&_udlo=30&_udhi=60)

<img src="docs/sensecap-m1.png" width="360" alt="SenseCap M1 with WM1303 concentrator">

Remove the 2 screws on the back panel (the side without the Ethernet/antenna ports) to access the SD card -- it may be held in place by kapton tape. Flash with Raspberry Pi OS 64-bit and run the install script -- the setup wizard auto-detects the hardware. USB-C power connects to the carrier board, not the Pi directly.

### Option C: Build your own (~$85)

| Component | Price |
|-----------|-------|
| Raspberry Pi 4 (1GB+) | $35 |
| RAK2287 SX1302 + Pi HAT | ~$20* |
| 915 MHz LoRa antenna | $10 |
| MicroSD card (16GB+) | $10 |
| USB-C power supply (5V 3A) | $10 |

*\*Helium's surplus means RAK2287 concentrators and Pi HATs go for ~$20 combined on eBay.*

**Assembly:** Seat the RAK2287 on the Pi HAT, mount the HAT on the Pi GPIO header, connect the antenna. Always connect the antenna before powering on.

> **Full step-by-step guide:** See the [Onboarding Guide](docs/ONBOARDING.md) for detailed instructions covering flashing, assembly, installation, and troubleshooting for all hardware options.

---

## Install

```bash
sudo apt update && sudo apt install -y git
git clone https://github.com/KMX415/meshpoint.git ~/meshpoint
cd ~/meshpoint && sudo bash scripts/install.sh
```

This builds the SX1302 HAL with Meshtastic patches, sets up a Python venv, and installs the systemd service.

```bash
meshpoint setup    # interactive config wizard
meshpoint status   # verify everything is running
```

Open `http://<pi-ip>:8080` for the local dashboard.

---

## Architecture

```
                                ┌─────────────────────────┐
                                │    Mesh Radar Cloud      │
                                │    (meshradar.io)        │
                                └────────────┬────────────┘
                                             │ WebSocket
                                             │
┌──────────┐    ┌──────────┐    ┌────────────┴────────────┐
│  LoRa    │    │ SX1302/  │    │    Mesh Point (Pi 4)     │
│ Packets  │───▶│ SX1303   │───▶│                          │
│ (OTA)    │    │ 8-ch RX  │    │  Capture → Decode → API  │
└──────────┘    └──────────┘    │              │           │
                                │           Dashboard     │
                                │          (port 8080)    │
                                └─────────────────────────┘
```

**Capture** -- SX1302 HAL receives on 8 channels across SF7-SF12 simultaneously.

**Decode** -- Packets are decrypted and parsed. Positions, text messages, telemetry, node info, routing data -- all extracted and stored.

**Dashboard** -- Local web UI with a live map, packet feed with decoded contents, traffic charts, and signal analytics.

**Upstream** -- Optional WebSocket connection to Mesh Radar for aggregated multi-site mesh intelligence.

---

## Smart Relay (Optional)

Connect a separate SX1262 radio (T-Beam, Heltec, RAK4631) via USB and the Mesh Point can re-broadcast packets it hears:

- Deduplication via packet ID tracking
- Token-bucket rate limiting
- RSSI-based filtering
- TX path is independent from RX -- transmission never blocks reception

---

## Configuration

All settings live in `config/default.yaml` with user overrides in `config/local.yaml`.

```yaml
radio:
  frequency_mhz: 906.875      # US915 Meshtastic default
  spreading_factor: 11         # SF11 (LongFast)
  bandwidth_khz: 250.0

capture:
  sources:
    - concentrator

relay:
  enabled: false
  max_relay_per_minute: 20

upstream:
  enabled: true
  url: "wss://api.meshradar.io/ws"
```

---

## Local API

FastAPI server on port 8080:

| Endpoint | Description |
|----------|-------------|
| `GET /api/nodes` | All discovered nodes |
| `GET /api/nodes/map` | Nodes with GPS for map display |
| `GET /api/packets` | Recent packets (paginated) |
| `GET /api/analytics/traffic` | Traffic rates and counts |
| `GET /api/analytics/signal/rssi` | RSSI distribution |
| `GET /api/device/status` | Device health and uptime |
| `WS /ws` | Real-time packet stream |

---

## CLI

```bash
meshpoint status     # service status + config summary
meshpoint logs       # tail the service journal
meshpoint restart    # restart the service
meshpoint setup      # re-run config wizard
```

---

## Troubleshooting

**Chip version 0x00** -- Concentrator not responding. Check that the concentrator module is seated, SPI is enabled (`raspi-config` → Interface Options → SPI), and try a full power cycle (unplug for 10+ seconds). Normal chip versions are `0x10` (SX1302) and `0x12` (SX1303).

**No packets** -- Verify antenna is connected, frequency matches your region, and check `meshpoint logs` for `lgw_receive returned N packet(s)`.

**Upstream 401** -- Bad API key. Get a free one at [meshradar.io](https://meshradar.io) and re-run `meshpoint setup`.

---

## Contributing

The API server, dashboard, analytics, storage, and relay modules are fully open source. Protocol decoding and hardware abstraction are distributed as compiled modules.

Fork → branch → PR. Bug reports and feature requests welcome as issues.

---

## License

MIT -- see [LICENSE](LICENSE). Compiled core modules (`meshpoint-core`) are distributed separately under a commercial license.

---

*Built for the mesh community by [Mesh Radar](https://meshradar.io).*
