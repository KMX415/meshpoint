<p align="center">
  <img src="MP_logo.png" width="280" alt="Meshpoint Logo">
</p>

<h1 align="center">Meshpoint</h1>

<p align="center"><strong>Open-source LoRa packet intelligence for Meshtastic and MeshCore mesh networks.</strong><br>Supports US915, EU868, ANZ915, IN865, KR920, and SG923 frequency regions.</p>

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-green.svg)](https://www.python.org/)
[![Platform: Raspberry Pi](https://img.shields.io/badge/platform-Raspberry%20Pi%204-red.svg)](https://www.raspberrypi.com/)
[![Discord](https://img.shields.io/badge/Discord-Join-5865F2?logo=discord&logoColor=white)](https://discord.gg/Cfuc6Cp4wM)

![Meshradar Dashboard](dashboard.png)

![Meshpoint Terminal](docs/meshpoint-terminal-banner.png)

---

## What Is This?

A Raspberry Pi-based LoRa listener that captures traffic from **Meshtastic** and **MeshCore** mesh networks simultaneously. The SX1302/SX1303 concentrator listens on **8 LoRa channels** across all spreading factors at once, while an optional MeshCore USB companion monitors MeshCore traffic on its own frequency.

Packets are captured, decrypted, stored locally, and shown on a real-time dashboard. Optionally, everything syncs upstream to [Meshradar](https://meshradar.io) for aggregated city-wide mesh intelligence.

### Supported Regions

Select your region during setup and the concentrator auto-tunes to the correct frequency. MeshCore companion radios are configured to match automatically.

| Region | Meshtastic Frequency | MeshCore Frequency |
|--------|---------------------|-------------------|
| **US** | 906.875 MHz | 910.525 MHz |
| **EU_868** | 869.525 MHz | 869.618 MHz |
| **ANZ** | 917.375 MHz | 916.575 MHz |
| **IN** | 865.625 MHz | Custom |
| **KR** | 921.125 MHz | Custom |
| **SG_923** | 917.375 MHz | Custom |

Regions without a standard MeshCore preset prompt for custom frequency entry during setup, or use `meshpoint meshcore-radio custom` anytime.

### Standard Node vs Meshpoint

| | Standard Node | Meshpoint |
|---|---|---|
| **Channels** | 1 | 8 |
| **Demodulators** | 1 | 16 (multi-SF) |
| **Role** | Participant | Passive observer |
| **Packet visibility** | Own traffic | Everything in range |
| **Storage** | None | SQLite with retention |
| **Dashboard** | None | Real-time web UI |

---

## Hardware

> **Requirements:** Raspberry Pi 4, 64-bit Raspberry Pi OS, Python 3.13. The compiled core modules are aarch64 binaries — other platforms (Pi 3, x86, 32-bit OS) are not currently supported.

### Option A: RAK Hotspot V2 (~$60, recommended)

The easiest path. RAK/MNTD Hotspot V2 miners (model **RAK7248**) include a Pi 4, RAK2287 (SX1302), Pi HAT, metal enclosure, antenna, and power supply — everything you need. Helium's IoT network didn't pan out, so these are all over eBay for $40-70.

[Find on eBay ($30-80)](https://www.ebay.com/sch/i.html?_nkw=RAK%20Hotspot%20V2%20%2F%20MNTD&_sacat=0&_from=R40&rt=nc&_udlo=30&_udhi=80)

<img src="rak7248.png" width="360" alt="RAK7248 Hotspot V2">

Remove the 4 bottom screws to access the SD card slot. Flash a new card with Raspberry Pi OS 64-bit, run the install script, and you have a Meshpoint in a nice aluminum enclosure.

### Option B: SenseCap M1 (~$40-60)

Another Helium-era miner with identical compatibility. The SenseCap M1 includes a Pi 4, Seeed WM1303 concentrator (SX1303), carrier board, metal enclosure, and antenna. Some units ship with a 64GB SD card included.

[Find on eBay ($30-60)](https://www.ebay.com/sch/i.html?_nkw=SenseCap%20M1&_sacat=0&_from=R40&rt=nc&_udlo=30&_udhi=60)

<img src="docs/sensecap-m1.png" width="360" alt="SenseCap M1">

Remove the 2 screws on the back panel (the side without the Ethernet/antenna ports) to access the SD card — it may be held in place by kapton tape. Flash with Raspberry Pi OS 64-bit and run the install script. USB-C power connects to the carrier board, not the Pi directly.

### Option C: Build Your Own (~$85)

| Component | Price |
|-----------|-------|
| Raspberry Pi 4 (1GB+) | $35 |
| RAK2287 SX1302 + Pi HAT | ~$20* |
| 915 MHz LoRa antenna | $10 |
| MicroSD card (16GB+) | $10 |
| USB-C power supply (5V 3A) | $10 |

*\*Helium's surplus means RAK2287 concentrators and Pi HATs go for ~$20 combined on eBay.*

**Assembly:** Seat the RAK2287 on the Pi HAT, mount the HAT on the Pi GPIO header, connect the antenna. Always connect the antenna before powering on.

### Optional: MeshCore USB Companion

Add a Heltec V3/V4 or T-Beam running [MeshCore USB companion firmware](https://flasher.meshcore.co.uk/) to monitor MeshCore traffic alongside Meshtastic. Plug it into any USB port on the Pi -- the setup wizard auto-detects the device and configures its radio frequency for your region.

> **Full step-by-step guide:** See the [Onboarding Guide](docs/ONBOARDING.md) for detailed instructions covering flashing, assembly, installation, MeshCore setup, and troubleshooting for all hardware options.

---

## Install

```bash
sudo apt update && sudo apt install -y git
sudo git clone https://github.com/KMX415/meshpoint.git /opt/meshpoint
cd /opt/meshpoint && sudo bash scripts/install.sh
```

This builds the SX1302 HAL with Meshtastic patches, sets up a Python venv, and installs the systemd service.

```bash
sudo meshpoint setup    # interactive config wizard
meshpoint status        # verify everything is running
```

Open `http://<pi-ip>:8080` for the local dashboard.

---

## Architecture

```
                                ┌─────────────────────────┐
                                │    Meshradar Cloud       │
                                │    (meshradar.io)        │
                                └────────────┬────────────┘
                                             │ WebSocket
                                             │
┌──────────┐    ┌──────────┐    ┌────────────┴────────────┐
│Meshtastic│    │ SX1302/  │    │    Meshpoint (Pi 4)      │
│ packets  │───▶│ SX1303   │───▶│                          │
│ (OTA)    │    │ 8-ch RX  │    │  Capture → Decode → API  │
└──────────┘    └──────────┘    │              │           │
                                │           Dashboard     │
┌──────────┐    ┌──────────┐    │          (port 8080)    │
│ MeshCore │    │  Heltec  │    │                          │
│ packets  │───▶│  USB     │───▶│                          │
│ (OTA)    │    │companion │    │                          │
└──────────┘    └──────────┘    └─────────────────────────┘
```

**Capture** — SX1302 HAL receives Meshtastic on 8 channels across SF7-SF12. A USB MeshCore companion (optional) receives MeshCore traffic on its configured frequency.

**Decode** — Packets from both protocols decrypted and parsed. Positions, text messages, telemetry, node info, advertisements, routing data — all extracted and stored.

**Dashboard** — Local web UI with a live map, packet feed with decoded contents, traffic charts, and signal analytics.

**Upstream** — Optional WebSocket connection to Meshradar for aggregated multi-site mesh intelligence.

---

## Smart Relay (Optional)

Connect a separate SX1262 radio (T-Beam, Heltec, RAK4631) via USB and the Meshpoint can re-broadcast packets it hears:

- Deduplication via packet ID tracking
- Token-bucket rate limiting
- RSSI-based signal filtering
- TX path is independent from RX — transmission never blocks reception

---

## Configuration

All settings live in `config/default.yaml` with user overrides in `config/local.yaml`.

```yaml
radio:
  region: "US"                 # US, EU_868, ANZ, IN, KR, SG_923
  frequency_mhz: 906.875      # auto-configured from region
  spreading_factor: 11         # SF11 (LongFast)
  bandwidth_khz: 250.0

capture:
  sources:
    - concentrator
    - meshcore_usb
  meshcore_usb:
    auto_detect: true          # scans /dev/ttyUSB* and /dev/ttyACM*

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
meshpoint status         # service status + config summary
meshpoint logs           # tail the service journal
meshpoint restart        # restart the service
meshpoint meshcore-radio # configure MeshCore companion radio frequency
sudo meshpoint setup     # re-run config wizard
```

---

## Troubleshooting

**Chip version 0x00** — Concentrator not responding. Check that the concentrator module is seated, SPI is enabled (`raspi-config` → Interface Options → SPI), and try a full power cycle (unplug for 10+ seconds). Normal chip versions are `0x10` (SX1302) and `0x12` (SX1303).

**No packets** — Verify antenna is connected and frequency matches your region. Check `meshpoint logs` for `lgw_receive returned N packet(s)`.

**Upstream 401** — Bad API key. Get a free one at [meshradar.io](https://meshradar.io) and re-run `sudo meshpoint setup`.

---

## Changelog

### March 2026

#### Early March
- **Real-time packet streaming** — Cloud dashboard receives packets instantly via WebSocket. Live animated lines trace packets from source nodes to your Meshpoint on the map as they arrive.
- **Cloud map overhaul** — Marker clustering, signal heatmap layer, topology lines from neighborinfo data, and a live Recent Packets ticker panel.
- **SenseCap M1 support** — Auto-detects SenseCap M1 carrier board via I2C probe during setup. Flash an SD card and go.
- **14 Meshtastic portnums decoded** — TEXT, POSITION, NODEINFO, TELEMETRY, ROUTING, ADMIN, WAYPOINT, DETECTION_SENSOR, PAXCOUNTER, STORE_FORWARD, RANGE_TEST, TRACEROUTE, NEIGHBORINFO, MAP_REPORT — plus encrypted packet tracking.
- **Device role extraction** — Node table shows CLIENT, ROUTER, REPEATER, TRACKER, SENSOR, and other roles from NodeInfo packets.
- **Smart relay engine** — Deduplication, token-bucket rate limiting, hop/type/signal filtering, independent SX1262 TX path.

#### Mid March
- **Live dashboard UX** — Color-coded packet feed, decoded payload contents, 24h active node counts, version-based update indicator, and enlarged map view.
- **Cloud dashboard tabs** — Tabbed layout with fleet view, interactive map controls, device-scoped filters, unified packet cards with signal strength bars, and public activity stream for visitors.
- **MeshCore USB capture** — New capture source for USB-connected MeshCore companion nodes. Auto-detects the device, configures radio frequency via the setup wizard (US/EU/ANZ presets or custom), with auto-reconnect and health monitoring. Startup banner shows all active sources.
- **Custom frequency tuning** — Configurable SX1302 channel plan via local.yaml. Validated on live hardware with LongFast (SF11/BW250). Dual-protocol HAL patch for simultaneous Meshtastic and MeshCore sync words.

#### Late March — International Frequency Support
- **Multi-region concentrator support** — Added support for US, EU_868, ANZ, IN, KR, and SG_923 frequency regions. The SX1302 concentrator automatically tunes to the correct primary frequency, spreading factor, and bandwidth for each region.
- **Setup wizard region selector** — New step in the setup wizard lets you choose your frequency region. MeshCore companion radios are automatically configured to match your selected region (US, EU, ANZ presets).
- **`meshpoint meshcore-radio` CLI command** — New standalone command to switch your MeshCore companion radio frequency without re-running the full setup wizard. Supports preset regions (`meshpoint meshcore-radio EU`) or custom manual entry (`meshpoint meshcore-radio custom`). Auto-detects USB port, handles service stop/restart, and updates config if the port changes after reboot.

---

## Updating

```bash
cd /opt/meshpoint && sudo git pull origin main && sudo systemctl restart meshpoint
```

The local dashboard shows an orange update indicator when a new version is available. After updating, verify the new version in the startup banner or with `meshpoint version`.

If you're updating to a version that changes your region support, re-run `sudo meshpoint setup` to select your frequency region.

---

## Community

- **Discord:** [discord.gg/Cfuc6Cp4wM](https://discord.gg/Cfuc6Cp4wM)
- **Website:** [meshradar.io](https://meshradar.io)
- **Issues:** [GitHub Issues](https://github.com/KMX415/meshpoint/issues)

---

## Contributing

Meshpoint is still early alpha. Pull requests are welcome, but please keep changes small and reviewable.

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines, workflow, and PR expectations.

AI-assisted contributions are allowed, but contributors should review and understand all code before submitting.

---

## License

MIT — see [LICENSE](LICENSE). Compiled core modules are distributed separately under a commercial license.

---

*Built for the mesh community by [Meshradar](https://meshradar.io).*
